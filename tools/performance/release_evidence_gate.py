"""Release-readiness evaluator for normalized performance evidence.

Consumes **already-normalized** benchmark records (PR #258 schema ``1.0`` or
compatible dicts) and returns an explicit release-evidence decision. This module
does **not** run benchmarks, does **not** import or modify
``evidence_normalizer``, ``performance_policy``, ``process_runner``, streaming,
or orchestration code.

Performance evidence only — never scientific evidence. Timeouts are never PASS.
Missing RSS / tracemalloc stay ``null`` (never fabricated ``0``). Cross-host
runtime is advisory. Tracemalloc is never treated as process RSS.
"""
from __future__ import annotations

import json
import math
import platform
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

__all__ = [
    "GATE_SCHEMA_VERSION",
    "COMPATIBLE_NORMALIZATION_SCHEMAS",
    "ReleaseDecision",
    "ReleaseEvidenceReport",
    "GateThresholds",
    "json_safe",
    "dumps",
    "evaluate_release_evidence",
    "render_markdown",
    "load_pair",
]

GATE_SCHEMA_VERSION = "1.0"
COMPATIBLE_NORMALIZATION_SCHEMAS = frozenset({"1.0"})


class ReleaseDecision(str, Enum):
    """Explicit release-evidence outcomes (timeout never maps to ready)."""

    EVIDENCE_READY = "EVIDENCE_READY"
    EVIDENCE_INCONCLUSIVE = "EVIDENCE_INCONCLUSIVE"
    CORRECTNESS_FAILURE = "CORRECTNESS_FAILURE"
    TIMEOUT_FAILURE = "TIMEOUT_FAILURE"
    INFRASTRUCTURE_BLOCKED = "INFRASTRUCTURE_BLOCKED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    MISSING_METRIC = "MISSING_METRIC"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"


@dataclass(frozen=True)
class GateThresholds:
    """Configurable tolerances for release-evidence evaluation."""

    min_repetitions: int = 3
    max_runtime_rel_spread: float = 0.50
    max_runtime_regression_ratio: float = 1.25
    max_tracemalloc_regression_ratio: float = 1.10
    max_child_rss_regression_ratio: float = 1.25
    checksum_rel_tol: float = 1e-9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_repetitions": int(self.min_repetitions),
            "max_runtime_rel_spread": float(self.max_runtime_rel_spread),
            "max_runtime_regression_ratio": float(self.max_runtime_regression_ratio),
            "max_tracemalloc_regression_ratio": float(self.max_tracemalloc_regression_ratio),
            "max_child_rss_regression_ratio": float(self.max_child_rss_regression_ratio),
            "checksum_rel_tol": float(self.checksum_rel_tol),
        }


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


# --------------------------------------------------------------------------- #
# Field access (normalized schema; never fabricate memory metrics)
# --------------------------------------------------------------------------- #


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _as_int(value: Any) -> Optional[int]:
    f = _as_float(value)
    return int(f) if f is not None else None


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _memory_bytes(value: Any) -> Optional[int]:
    """Return a positive memory measurement, else ``None`` (never fabricate 0)."""
    n = _as_int(value)
    if n is None or n <= 0:
        return None
    return n


def _bool(value: Any, default: bool = False) -> bool:
    return bool(value) if isinstance(value, bool) else default


def _record_view(record: Dict[str, Any]) -> Dict[str, Any]:
    """Accept a normalized record or a thin wrapper ``{"record": {...}}``."""
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")
    if "benchmark_id" in record or "checksum" in record or "input_shape" in record:
        return record
    inner = record.get("record")
    if isinstance(inner, dict):
        return inner
    return record


def _checksum_equal(a: Any, b: Any, rel_tol: float) -> Optional[bool]:
    if a is None or b is None:
        return None
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    fa, fb = _as_float(a), _as_float(b)
    if fa is None or fb is None:
        return None
    scale = max(1.0, abs(fa), abs(fb))
    return abs(fa - fb) <= rel_tol * scale


def _shapes_equal(a: Any, b: Any) -> Optional[bool]:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    keys = sorted(set(a) | set(b))
    if not keys:
        return None
    for key in keys:
        if a.get(key) != b.get(key):
            return False
    return True


def _ratio(cand: Optional[float], base: Optional[float]) -> Optional[float]:
    if cand is None or base is None or base <= 0:
        return None
    r = cand / base
    return r if math.isfinite(r) else None


def _runtime_spread(record: Dict[str, Any]) -> Optional[float]:
    """Relative spread ``(mean-best)/best`` when both wall stats exist."""
    best = _as_float(record.get("wall_best_s") or record.get("runtime_best_s"))
    mean = _as_float(record.get("wall_mean_s") or record.get("runtime_mean_s"))
    # Fall back: if only runtime_s + runtime_spread provided.
    explicit = _as_float(record.get("runtime_rel_spread"))
    if explicit is not None:
        return explicit if explicit >= 0 else None
    if best is None or mean is None or best <= 0:
        return None
    return max(0.0, (mean - best) / best)


def _optional_dep_blocked(record: Dict[str, Any]) -> bool:
    state = _as_str(record.get("optional_dependency_state"))
    if state and state.lower() in {"missing", "unavailable", "blocked"}:
        return True
    outcome = str(record.get("raw_outcome") or record.get("outcome") or record.get("status") or "").lower()
    return outcome in {
        "optional_dependency_missing",
        "infrastructure_blocked",
        "infrastructure_failure",
    }


def _is_child_crash(record: Dict[str, Any]) -> bool:
    outcome = str(record.get("raw_outcome") or record.get("outcome") or record.get("status") or "").lower()
    if outcome in {"child_crash", "child-crash"}:
        return True
    exit_code = _as_int(record.get("process_exit_status") or record.get("exit_code"))
    if exit_code is not None and (exit_code < 0 or exit_code >= 128) and not _bool(record.get("timeout_status")):
        # Signal-style exits often indicate crash; timeout uses 124 conventionally.
        if exit_code == 124:
            return False
        return True
    return False


def _is_timeout(record: Dict[str, Any]) -> bool:
    if _bool(record.get("timeout_status")):
        return True
    outcome = str(record.get("raw_outcome") or record.get("outcome") or record.get("status") or "").lower()
    return outcome in {"timeout", "timeout_failure"}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


@dataclass
class ReleaseEvidenceReport:
    """Finite, deterministic release-evidence evaluation report."""

    schema_version: str
    decision: ReleaseDecision
    evidence_class: str
    synthetic: bool
    comparable: bool
    reason_codes: List[str]
    reasons: List[str]
    recommendations: List[str]
    authoritative_metrics: Dict[str, Any]
    advisory_metrics: Dict[str, Any]
    comparable_fields: Dict[str, Any]
    baseline_checksum: Optional[Union[float, str]]
    candidate_checksum: Optional[Union[float, str]]
    thresholds: Dict[str, Any]
    environment: Dict[str, Any]
    test_metadata: Dict[str, Any]
    baseline: Dict[str, Any]
    candidate: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        return json_safe(payload)


def _env_metadata() -> Dict[str, Any]:
    return {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "system": platform.system(),
        "machine": platform.machine(),
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "compatible_normalization_schemas": sorted(COMPATIBLE_NORMALIZATION_SCHEMAS),
    }


def _schema_ok(record: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    version = _as_str(record.get("schema_version"))
    if version is None:
        # Compatible bare normalized dicts without schema_version are accepted
        # when core fields are present (PR #258 consumers may strip wrappers).
        if any(k in record for k in ("benchmark_id", "checksum", "input_shape")):
            return True, None
        return False, "missing_schema_and_core_fields"
    if version not in COMPATIBLE_NORMALIZATION_SCHEMAS:
        return False, f"unsupported_normalization_schema:{version}"
    return True, None


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #


def evaluate_release_evidence(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    thresholds: GateThresholds = GateThresholds(),
    *,
    test_metadata: Optional[Dict[str, Any]] = None,
) -> ReleaseEvidenceReport:
    """Evaluate whether a baseline/candidate pair is release-ready evidence.

    Precedence:
    ``TIMEOUT_FAILURE`` → ``INFRASTRUCTURE_BLOCKED`` (incl. optional-dep /
    child crash) → ``NOT_COMPARABLE`` → ``CORRECTNESS_FAILURE`` →
    ``MISSING_METRIC`` → ``EVIDENCE_INCONCLUSIVE`` → ``REGRESSION_DETECTED`` →
    ``EVIDENCE_READY``.
    """
    base = _record_view(baseline)
    cand = _record_view(candidate)
    reasons: List[str] = []
    reason_codes: List[str] = []
    recommendations: List[str] = [
        "Synthetic fixtures are performance evidence only — never scientific evidence.",
        "Do not equate tracemalloc peaks with process RSS.",
        "Re-measure baseline and candidate on the same host for authoritative runtime/RSS.",
    ]

    def _finish(
        decision: ReleaseDecision,
        *,
        comparable: bool,
        authoritative: Dict[str, Any],
        advisory: Dict[str, Any],
        comparable_fields: Dict[str, Any],
    ) -> ReleaseEvidenceReport:
        return ReleaseEvidenceReport(
            schema_version=GATE_SCHEMA_VERSION,
            decision=decision,
            evidence_class="performance_only",
            synthetic=True,
            comparable=comparable,
            reason_codes=list(reason_codes),
            reasons=list(reasons),
            recommendations=list(recommendations),
            authoritative_metrics=json_safe(authoritative),
            advisory_metrics=json_safe(advisory),
            comparable_fields=json_safe(comparable_fields),
            baseline_checksum=base.get("checksum"),
            candidate_checksum=cand.get("checksum"),
            thresholds=thresholds.to_dict(),
            environment=_env_metadata(),
            test_metadata=json_safe(test_metadata or {}),
            baseline=json_safe(base),
            candidate=json_safe(cand),
        )

    # Schema compatibility
    for label, rec in (("baseline", base), ("candidate", cand)):
        ok, code = _schema_ok(rec)
        if not ok:
            reason_codes.append(code or "schema_invalid")
            reasons.append(f"{label} normalization schema not compatible")
            return _finish(
                ReleaseDecision.NOT_COMPARABLE,
                comparable=False,
                authoritative={},
                advisory={},
                comparable_fields={"schema_ok": False},
            )

    # Timeouts — never ready / never pass.
    if _is_timeout(base) or _is_timeout(cand):
        reason_codes.append("timeout")
        reasons.append("one or both records timed out; timeout is never PASS or EVIDENCE_READY")
        return _finish(
            ReleaseDecision.TIMEOUT_FAILURE,
            comparable=False,
            authoritative={"timeout_status": True},
            advisory={},
            comparable_fields={"timeout": True},
        )

    # Child crash / optional dependency / infrastructure.
    if _is_child_crash(base) or _is_child_crash(cand):
        reason_codes.append("child_crash")
        reasons.append("one or both records indicate child_crash")
        return _finish(
            ReleaseDecision.INFRASTRUCTURE_BLOCKED,
            comparable=False,
            authoritative={"child_crash": True},
            advisory={},
            comparable_fields={"child_crash": True},
        )

    if _optional_dep_blocked(base) or _optional_dep_blocked(cand):
        reason_codes.append("optional_dependency_missing")
        reasons.append(
            "optional dependency missing/unavailable — not a successful execution"
        )
        return _finish(
            ReleaseDecision.INFRASTRUCTURE_BLOCKED,
            comparable=False,
            authoritative={"optional_dependency_state": "missing"},
            advisory={},
            comparable_fields={"optional_dependency_blocked": True},
        )

    # Shape / backend / host / commit commensurability.
    shape_match = _shapes_equal(base.get("input_shape"), cand.get("input_shape"))
    backend_a = _as_str(base.get("backend"))
    backend_b = _as_str(cand.get("backend"))
    backend_match = None if backend_a is None or backend_b is None else (backend_a == backend_b)
    host_a = _as_str(base.get("host"))
    host_b = _as_str(cand.get("host"))
    host_match = None if host_a is None or host_b is None else (host_a == host_b)
    chunk_a = _as_int(base.get("chunk_size"))
    chunk_b = _as_int(cand.get("chunk_size"))
    chunk_match = None if chunk_a is None or chunk_b is None else (chunk_a == chunk_b)

    comparable_fields = {
        "shape_match": shape_match,
        "backend_match": backend_match,
        "host_match": host_match,
        "chunk_size_match": chunk_match,
        "baseline_source_commit": _as_str(base.get("source_commit")),
        "candidate_source_commit": _as_str(cand.get("source_commit")),
    }

    if shape_match is not True:
        reason_codes.append("shape_mismatch")
        reasons.append("input_shape/dtype mismatch or missing")
        return _finish(
            ReleaseDecision.NOT_COMPARABLE,
            comparable=False,
            authoritative={},
            advisory={},
            comparable_fields=comparable_fields,
        )

    if backend_match is False:
        reason_codes.append("backend_mismatch")
        reasons.append(f"backend mismatch: {backend_a!r} vs {backend_b!r}")
        return _finish(
            ReleaseDecision.NOT_COMPARABLE,
            comparable=False,
            authoritative={},
            advisory={},
            comparable_fields=comparable_fields,
        )

    # Checksum correctness gate.
    checksum_match = _checksum_equal(
        base.get("checksum"), cand.get("checksum"), thresholds.checksum_rel_tol
    )
    comparable_fields["checksum_match"] = checksum_match
    if checksum_match is False:
        reason_codes.append("checksum_mismatch")
        reasons.append("checksum mismatch; correctness gates release evidence")
        return _finish(
            ReleaseDecision.CORRECTNESS_FAILURE,
            comparable=False,
            authoritative={"checksum_match": False},
            advisory={},
            comparable_fields=comparable_fields,
        )
    if checksum_match is None:
        reason_codes.append("checksum_missing")
        reasons.append("checksum missing on baseline and/or candidate")
        return _finish(
            ReleaseDecision.EVIDENCE_INCONCLUSIVE,
            comparable=False,
            authoritative={},
            advisory={"checksum_match": None},
            comparable_fields=comparable_fields,
        )

    # Repetitions / runtime spread quality.
    reps_a = _as_int(base.get("repetitions"))
    reps_b = _as_int(cand.get("repetitions"))
    reps_ok = (
        reps_a is not None
        and reps_b is not None
        and reps_a >= thresholds.min_repetitions
        and reps_b >= thresholds.min_repetitions
    )
    spread_a = _runtime_spread(base)
    spread_b = _runtime_spread(cand)
    spread_high = (
        (spread_a is not None and spread_a > thresholds.max_runtime_rel_spread)
        or (spread_b is not None and spread_b > thresholds.max_runtime_rel_spread)
    )

    # Memory metrics — null if missing, never zero-filled.
    tm_a = _memory_bytes(base.get("tracemalloc_peak_bytes"))
    tm_b = _memory_bytes(cand.get("tracemalloc_peak_bytes"))
    rss_a = _memory_bytes(base.get("child_rss_bytes"))
    rss_b = _memory_bytes(cand.get("child_rss_bytes"))
    parent_a = _memory_bytes(base.get("parent_sampled_rss_bytes"))
    parent_b = _memory_bytes(cand.get("parent_sampled_rss_bytes"))
    rt_a = _as_float(base.get("runtime_s"))
    rt_b = _as_float(cand.get("runtime_s"))

    tm_ratio = _ratio(None if tm_b is None else float(tm_b), None if tm_a is None else float(tm_a))
    rss_ratio = _ratio(None if rss_b is None else float(rss_b), None if rss_a is None else float(rss_a))
    parent_ratio = _ratio(
        None if parent_b is None else float(parent_b),
        None if parent_a is None else float(parent_a),
    )
    rt_ratio = _ratio(rt_b, rt_a)

    same_host = host_match is True
    # Authoritative: tracemalloc always (Python-domain); child RSS + runtime only same-host.
    authoritative: Dict[str, Any] = {
        "tracemalloc_peak_bytes": {"baseline": tm_a, "candidate": tm_b, "ratio": tm_ratio},
        "checksum_match": True,
    }
    if same_host:
        authoritative["child_rss_bytes"] = {
            "baseline": rss_a,
            "candidate": rss_b,
            "ratio": rss_ratio,
        }
        authoritative["runtime_s"] = {
            "baseline": rt_a,
            "candidate": rt_b,
            "ratio": rt_ratio,
        }

    advisory: Dict[str, Any] = {
        "parent_sampled_rss_bytes": {
            "baseline": parent_a,
            "candidate": parent_b,
            "ratio": parent_ratio,
            "note": "best-effort parent sample; not the chunk working set",
        },
        "tracemalloc_is_not_process_rss": True,
    }
    if not same_host:
        advisory["runtime_s"] = {
            "baseline": rt_a,
            "candidate": rt_b,
            "ratio": rt_ratio,
            "note": "cross-host or unknown-host runtime is advisory only",
        }
        advisory["child_rss_bytes"] = {
            "baseline": rss_a,
            "candidate": rss_b,
            "ratio": rss_ratio,
            "note": "cross-host RSS is advisory only",
        }
        reason_codes.append("cross_host_advisory")
        reasons.append("cross-host runtime/RSS treated as advisory, not authoritative")

    # Missing authoritative memory signal.
    if tm_ratio is None and (not same_host or rss_ratio is None):
        reason_codes.append("missing_metric")
        reasons.append(
            "tracemalloc and/or same-host child RSS unavailable (null, never zero)"
        )
        return _finish(
            ReleaseDecision.MISSING_METRIC,
            comparable=False,
            authoritative=authoritative,
            advisory=advisory,
            comparable_fields=comparable_fields,
        )

    if not reps_ok:
        reason_codes.append("insufficient_repetitions")
        reasons.append(
            f"repetitions below minimum ({thresholds.min_repetitions}): "
            f"baseline={reps_a}, candidate={reps_b}"
        )
        return _finish(
            ReleaseDecision.EVIDENCE_INCONCLUSIVE,
            comparable=True,
            authoritative=authoritative,
            advisory={**advisory, "repetitions": {"baseline": reps_a, "candidate": reps_b}},
            comparable_fields=comparable_fields,
        )

    if spread_high:
        reason_codes.append("high_runtime_spread")
        reasons.append(
            f"runtime relative spread exceeds {thresholds.max_runtime_rel_spread}: "
            f"baseline={spread_a}, candidate={spread_b}"
        )
        return _finish(
            ReleaseDecision.EVIDENCE_INCONCLUSIVE,
            comparable=True,
            authoritative=authoritative,
            advisory={
                **advisory,
                "runtime_rel_spread": {"baseline": spread_a, "candidate": spread_b},
            },
            comparable_fields=comparable_fields,
        )

    # Regression on authoritative metrics only.
    regression = False
    if tm_ratio is not None and tm_ratio > thresholds.max_tracemalloc_regression_ratio:
        regression = True
        reason_codes.append("tracemalloc_regression")
        reasons.append(
            f"tracemalloc ratio {tm_ratio:.4f} > {thresholds.max_tracemalloc_regression_ratio}"
        )
    if same_host:
        if rss_ratio is not None and rss_ratio > thresholds.max_child_rss_regression_ratio:
            regression = True
            reason_codes.append("child_rss_regression")
            reasons.append(
                f"child RSS ratio {rss_ratio:.4f} > {thresholds.max_child_rss_regression_ratio}"
            )
        if rt_ratio is not None and rt_ratio > thresholds.max_runtime_regression_ratio:
            regression = True
            reason_codes.append("runtime_regression")
            reasons.append(
                f"runtime ratio {rt_ratio:.4f} > {thresholds.max_runtime_regression_ratio}"
            )
    elif rt_ratio is not None and rt_ratio > thresholds.max_runtime_regression_ratio:
        reason_codes.append("advisory_runtime_elevated")
        reasons.append(
            f"advisory runtime ratio {rt_ratio:.4f} exceeds threshold (not authoritative)"
        )

    if regression:
        return _finish(
            ReleaseDecision.REGRESSION_DETECTED,
            comparable=True,
            authoritative=authoritative,
            advisory=advisory,
            comparable_fields=comparable_fields,
        )

    reason_codes.append("evidence_ready")
    reasons.append(
        "checksums match; shapes/backends comparable; no authoritative regression; "
        "measurement quality acceptable"
    )
    return _finish(
        ReleaseDecision.EVIDENCE_READY,
        comparable=True,
        authoritative=authoritative,
        advisory=advisory,
        comparable_fields=comparable_fields,
    )


def render_markdown(report: ReleaseEvidenceReport) -> str:
    """Deterministic Markdown summary of a release-evidence report."""
    d = report.to_dict()
    lines = [
        "# Performance Release Evidence Gate",
        "",
        f"- decision: `{d['decision']}`",
        f"- evidence_class: `{d['evidence_class']}`",
        f"- synthetic: `{d['synthetic']}`",
        f"- comparable: `{d['comparable']}`",
        f"- baseline_checksum: `{d['baseline_checksum']}`",
        f"- candidate_checksum: `{d['candidate_checksum']}`",
        "",
        "## Reason codes",
        "",
    ]
    for code in d["reason_codes"]:
        lines.append(f"- `{code}`")
    lines.extend(["", "## Reasons", ""])
    for reason in d["reasons"]:
        lines.append(f"- {reason}")
    lines.extend(["", "## Authoritative metrics", ""])
    for key in sorted(d["authoritative_metrics"].keys()):
        lines.append(f"- `{key}`: `{d['authoritative_metrics'][key]}`")
    lines.extend(["", "## Advisory metrics", ""])
    for key in sorted(d["advisory_metrics"].keys()):
        lines.append(f"- `{key}`: `{d['advisory_metrics'][key]}`")
    lines.extend(["", "## Recommendations", ""])
    for rec in d["recommendations"]:
        lines.append(f"- {rec}")
    lines.extend(["", "## Environment", ""])
    for key in sorted(d["environment"].keys()):
        lines.append(f"- `{key}`: `{d['environment'][key]}`")
    lines.append("")
    return "\n".join(lines)


def load_pair(path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load ``{baseline, candidate}`` or a two-item ``results`` list from JSON."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "baseline" in payload and "candidate" in payload:
        return payload["baseline"], payload["candidate"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        results = payload["results"]
        if len(results) >= 2:
            return results[0], results[1]
    if isinstance(payload, list) and len(payload) >= 2:
        return payload[0], payload[1]
    raise ValueError("input must contain baseline+candidate or >=2 results")
