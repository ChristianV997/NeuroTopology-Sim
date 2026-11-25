"""Pure evidence-normalization layer for heterogeneous benchmark reports.

Consumes already-produced reports from process-isolated runners, matrix
orchestration, memory telemetry, or plain dicts and returns comparable
:class:`NormalizedEvidence` records plus optional pair-wise
:class:`EvidenceDecision` outcomes.

This module does **not** run benchmarks, does **not** import or modify
``tools/streaming/**``, ``tools/benchmark_orchestration/**``, checkpoint/replay,
or performance-policy implementations. It is a pure adapter over report dicts.

Rules (see ``docs/performance/benchmark_evidence.md``):

* Missing RSS / tracemalloc → ``null``, never fabricated ``0``.
* Cross-host runtime comparisons are advisory.
* Checksums must match before performance comparisons are accepted.
* Timeout is never pass.
* Synthetic benchmarks are ``performance_only`` evidence — never scientific.
* Source commits are retained when present; missing commit blocks comparison.
* Input shapes and dtypes must match for comparison.
* JSON is finite and deterministic.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

__all__ = [
    "NORMALIZATION_SCHEMA_VERSION",
    "Decision",
    "NormalizedEvidence",
    "EvidenceDecision",
    "json_safe",
    "dumps",
    "normalize_record",
    "normalize_reports",
    "compare_evidence",
    "commensurability",
    "load_reports",
]

NORMALIZATION_SCHEMA_VERSION = "1.0"

# --------------------------------------------------------------------------- #
# Decision taxonomy
# --------------------------------------------------------------------------- #


class Decision(str, Enum):
    """Comparable-evidence decisions (timeouts never map to PASS)."""

    COMPARABLE = "comparable"
    NOT_COMPARABLE = "not_comparable"
    CORRECTNESS_FAILURE = "correctness_failure"
    TIMEOUT = "timeout"
    CHILD_CRASH = "child_crash"
    MISSING_METRIC = "missing_metric"
    INFRASTRUCTURE_BLOCKED = "infrastructure_blocked"
    PASS = "pass"
    REGRESSION = "regression"
    INCONCLUSIVE = "inconclusive"


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #


def json_safe(value: Any) -> Any:
    """Recursively convert to JSON-safe form (NaN/Inf → None)."""
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
    """Serialize with ``allow_nan=False`` after sanitizing non-finite floats."""
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


# --------------------------------------------------------------------------- #
# Field extraction (tolerant aliases; never fabricate metrics)
# --------------------------------------------------------------------------- #


def _first(record: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if "." in key:
            cur: Any = record
            ok = True
            for part in key.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    ok = False
                    break
                cur = cur[part]
            if ok:
                return cur
        elif key in record:
            return record[key]
    return None


def _as_optional_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return int(value)
    return None


def _as_optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _memory_bytes(value: Any) -> Optional[int]:
    """Return a memory metric or ``None``.

    Missing values stay ``None`` (never coerced to ``0``). Explicit zero is also
    treated as unavailable — a true zero-byte RSS/tracemalloc peak is not a
    meaningful measurement and must not masquerade as evidence.
    """
    n = _as_optional_int(value)
    if n is None or n <= 0:
        return None
    return n


def _input_shape(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    shape = _first(record, ("input_shape", "input_dims", "shape", "config.input_shape"))
    if isinstance(shape, dict) and shape:
        out: Dict[str, Any] = {}
        for key in ("channels", "samples", "n_channels", "n_samples", "dtype", "dtype_itemsize"):
            if key in shape and shape[key] is not None:
                out[key] = shape[key]
        # Normalize alias keys.
        if "n_channels" in out and "channels" not in out:
            out["channels"] = out.pop("n_channels")
        if "n_samples" in out and "samples" not in out:
            out["samples"] = out.pop("n_samples")
        return out or None
    channels = _as_optional_int(_first(record, ("channels", "n_channels", "config.channels")))
    samples = _as_optional_int(_first(record, ("samples", "n_samples", "config.samples")))
    dtype = _as_optional_str(_first(record, ("dtype", "config.dtype")))
    if channels is None and samples is None and dtype is None:
        return None
    out = {}
    if channels is not None:
        out["channels"] = channels
    if samples is not None:
        out["samples"] = samples
    if dtype is not None:
        out["dtype"] = dtype
    return out


def _boolish(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def _timeout_status(record: Dict[str, Any]) -> bool:
    if _boolish(record.get("timed_out")) is True:
        return True
    outcome = str(
        _first(record, ("outcome", "status", "raw_outcome", "decision")) or ""
    ).lower()
    return outcome in {"timeout", "TIMEOUT".lower()}


def _is_child_crash(record: Dict[str, Any]) -> bool:
    outcome = str(_first(record, ("outcome", "status")) or "").lower()
    return outcome in {"child_crash", "child-crash"}


def _is_infra_blocked(record: Dict[str, Any]) -> bool:
    outcome = str(_first(record, ("outcome", "status")) or "").lower()
    return outcome in {
        "infrastructure_blocked",
        "infrastructure_failure",
        "infrastructure-blocked",
        "infrastructure-failure",
    }


def _optional_dep_state(record: Dict[str, Any]) -> Optional[str]:
    explicit = _as_optional_str(
        _first(record, ("optional_dependency_state", "optional_deps_state"))
    )
    if explicit:
        return explicit
    outcome = str(_first(record, ("outcome", "status")) or "").lower()
    if outcome in {"optional_dependency_missing", "optional-dependency-missing"}:
        return "missing"
    missing = record.get("missing_metrics")
    if isinstance(missing, list) and any("optional" in str(m).lower() for m in missing):
        return "missing"
    return None


def _correctness_status(record: Dict[str, Any]) -> Optional[str]:
    ok = _boolish(_first(record, ("correctness_ok", "correctness")))
    if ok is True:
        return "ok"
    if ok is False:
        return "fail"
    outcome = str(_first(record, ("outcome", "status")) or "").lower()
    if outcome in {"correctness_failure", "CORRECTNESS_FAILURE".lower()}:
        return "fail"
    if outcome in {"pass", "PASS".lower()}:
        return "ok"
    return "unknown"


def _checksum(record: Dict[str, Any]) -> Optional[Union[float, str]]:
    value = _first(record, ("checksum", "aggregate_checksum", "aggregate_state_checksum"))
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _as_optional_float(value)


def _host_platform(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    host = _as_optional_str(_first(record, ("host", "hostname", "hardware.host", "hardware.hostname")))
    plat = _as_optional_str(
        _first(record, ("platform", "hardware.platform", "providers.platform", "os"))
    )
    hardware = record.get("hardware")
    if isinstance(hardware, dict):
        if host is None:
            host = _as_optional_str(hardware.get("host") or hardware.get("hostname"))
        if plat is None:
            plat = _as_optional_str(hardware.get("platform") or hardware.get("system"))
    return host, plat


def _is_synthetic(record: Dict[str, Any]) -> bool:
    if isinstance(record.get("synthetic"), bool):
        return record["synthetic"]
    label = str(_first(record, ("label", "provenance_label", "benchmark_id", "case_id")) or "").lower()
    if "synth" in label or "fixture" in label or "smoke" in label:
        return True
    # Default: performance scaffolding is synthetic unless explicitly marked false.
    if record.get("evidence_class") == "performance_only":
        return True
    return True


# --------------------------------------------------------------------------- #
# Normalized record
# --------------------------------------------------------------------------- #


@dataclass
class NormalizedEvidence:
    """One comparable, finite evidence record."""

    schema_version: str
    benchmark_id: str
    source_commit: Optional[str]
    branch: Optional[str]
    host: Optional[str]
    platform: Optional[str]
    python_version: Optional[str]
    backend: Optional[str]
    input_shape: Optional[Dict[str, Any]]
    chunk_size: Optional[int]
    repetitions: Optional[int]
    checksum: Optional[Union[float, str]]
    correctness_status: Optional[str]
    runtime_s: Optional[float]
    tracemalloc_peak_bytes: Optional[int]
    child_rss_bytes: Optional[int]
    parent_sampled_rss_bytes: Optional[int]
    timeout_status: bool
    process_exit_status: Optional[int]
    optional_dependency_state: Optional[str]
    evidence_class: str = "performance_only"
    synthetic: bool = True
    raw_outcome: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))

    def fingerprint(self) -> str:
        """Deterministic content hash (excludes notes ordering noise via sorted JSON)."""
        payload = self.to_dict()
        payload.pop("notes", None)
        return hashlib.sha256(dumps(payload, indent=None).encode("utf-8")).hexdigest()


@dataclass
class EvidenceDecision:
    """Pair-wise decision over two normalized records."""

    decision: Decision
    comparable: bool
    reasons: List[str]
    baseline: Dict[str, Any]
    candidate: Dict[str, Any]
    checksum_match: Optional[bool]
    host_match: Optional[bool]
    shape_match: Optional[bool]
    runtime_ratio: Optional[float]
    runtime_advisory: bool
    tracemalloc_ratio: Optional[float]
    child_rss_ratio: Optional[float]
    evidence_class: str
    synthetic: bool
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "decision": self.decision.value,
                "comparable": self.comparable,
                "reasons": list(self.reasons),
                "baseline": self.baseline,
                "candidate": self.candidate,
                "checksum_match": self.checksum_match,
                "host_match": self.host_match,
                "shape_match": self.shape_match,
                "runtime_ratio": self.runtime_ratio,
                "runtime_advisory": self.runtime_advisory,
                "tracemalloc_ratio": self.tracemalloc_ratio,
                "child_rss_ratio": self.child_rss_ratio,
                "evidence_class": self.evidence_class,
                "synthetic": self.synthetic,
                "recommendations": list(self.recommendations),
            }
        )


# --------------------------------------------------------------------------- #
# Normalize
# --------------------------------------------------------------------------- #


def normalize_record(record: Dict[str, Any]) -> NormalizedEvidence:
    """Normalize one raw report dict into :class:`NormalizedEvidence`."""
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")

    # Unwrap nested telemetry if present (process-runner ChildResult).
    telem = record.get("telemetry")
    flat = dict(record)
    if isinstance(telem, dict):
        for k, v in telem.items():
            flat.setdefault(k, v)
    cfg = record.get("config")
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            flat.setdefault(k, v)

    benchmark_id = _as_optional_str(
        _first(flat, ("benchmark_id", "case_id", "id", "label", "config.id"))
    )
    if not benchmark_id:
        benchmark_id = "unknown"

    host, plat = _host_platform(flat)
    child_rss = _memory_bytes(
        _first(flat, ("child_rss_bytes", "peak_rss_bytes", "rss_peak_bytes", "peak_rss"))
    )
    parent_rss = _memory_bytes(
        _first(
            flat,
            (
                "parent_sampled_rss_bytes",
                "parent_sampled_peak_rss_bytes",
                "parent_rss_bytes",
            ),
        )
    )
    tracemalloc = _memory_bytes(
        _first(flat, ("tracemalloc_peak_bytes", "tracemalloc_peak", "peak_bytes"))
    )

    runtime = _as_optional_float(
        _first(flat, ("runtime_s", "elapsed_s", "wall_best_s", "wall_mean_s", "duration_s"))
    )
    chunk = _as_optional_int(_first(flat, ("chunk_size", "config.chunk_size")))
    reps = _as_optional_int(_first(flat, ("repetitions", "repeats", "config.repetitions")))
    backend = _as_optional_str(_first(flat, ("backend", "config.backend")))
    py_ver = _as_optional_str(
        _first(flat, ("python_version", "python", "interpreter_version"))
    )
    source_commit = _as_optional_str(
        _first(flat, ("source_commit", "commit", "git_commit", "sha", "git_sha"))
    )
    branch = _as_optional_str(_first(flat, ("branch", "git_branch", "ref")))
    exit_status = _as_optional_int(
        _first(flat, ("process_exit_status", "exit_code", "returncode"))
    )
    raw_outcome = _as_optional_str(_first(flat, ("outcome", "status", "raw_outcome")))

    notes: List[str] = []
    if child_rss is None and _first(flat, ("child_rss_bytes", "peak_rss_bytes")) is None:
        notes.append("child_rss_bytes unavailable (null, not zero)")
    if tracemalloc is None and _first(flat, ("tracemalloc_peak_bytes",)) is None:
        notes.append("tracemalloc_peak_bytes unavailable (null, not zero)")

    return NormalizedEvidence(
        schema_version=NORMALIZATION_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        source_commit=source_commit,
        branch=branch,
        host=host,
        platform=plat,
        python_version=py_ver,
        backend=backend,
        input_shape=_input_shape(flat),
        chunk_size=chunk,
        repetitions=reps,
        checksum=_checksum(flat),
        correctness_status=_correctness_status(flat),
        runtime_s=runtime,
        tracemalloc_peak_bytes=tracemalloc,
        child_rss_bytes=child_rss,
        parent_sampled_rss_bytes=parent_rss,
        timeout_status=_timeout_status(flat),
        process_exit_status=exit_status,
        optional_dependency_state=_optional_dep_state(flat),
        evidence_class="performance_only",
        synthetic=_is_synthetic(flat),
        raw_outcome=raw_outcome,
        notes=notes,
    )


def _extract_record_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        raise TypeError("input must be a list or object of reports")
    for key in ("results", "records", "reports", "benchmarks", "children"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    # Single record object.
    if any(k in payload for k in ("benchmark_id", "case_id", "outcome", "status", "checksum")):
        return [payload]
    raise ValueError("could not locate report list in input payload")


def load_reports(path: str) -> Any:
    """Load a JSON file (list, results wrapper, or baseline/candidate pair)."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_reports(payload: Any) -> List[NormalizedEvidence]:
    """Normalize every record found in ``payload`` (deterministic order preserved)."""
    records = _extract_record_list(payload)
    return [normalize_record(r) for r in records]


# --------------------------------------------------------------------------- #
# Compare
# --------------------------------------------------------------------------- #


def _shapes_equal(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Optional[bool]:
    if a is None or b is None:
        return None
    keys = sorted(set(a) | set(b))
    for key in keys:
        if a.get(key) != b.get(key):
            return False
    return True


def _checksums_equal(a: Optional[Union[float, str]], b: Optional[Union[float, str]]) -> Optional[bool]:
    if a is None or b is None:
        return None
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    if abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(a)), abs(float(b))):
        return True
    return False


def _ratio(cand: Optional[float], base: Optional[float]) -> Optional[float]:
    if cand is None or base is None or base <= 0:
        return None
    r = cand / base
    return r if math.isfinite(r) else None


def compare_evidence(
    baseline: Union[Dict[str, Any], NormalizedEvidence],
    candidate: Union[Dict[str, Any], NormalizedEvidence],
    *,
    max_runtime_regression_ratio: float = 1.25,
    max_tracemalloc_regression_ratio: float = 1.10,
    max_child_rss_regression_ratio: float = 1.25,
) -> EvidenceDecision:
    """Compare two (raw or normalized) records and return an :class:`EvidenceDecision`.

    Precedence: timeout → child_crash → infrastructure_blocked → not_comparable
    (missing commit / shape) → correctness_failure → missing_metric →
    inconclusive → regression → pass. Cross-host runtime is advisory only.
    """
    base = baseline if isinstance(baseline, NormalizedEvidence) else normalize_record(baseline)
    cand = candidate if isinstance(candidate, NormalizedEvidence) else normalize_record(candidate)

    reasons: List[str] = []
    recommendations = [
        "Synthetic fixtures are performance evidence only — never scientific evidence.",
        "Retain source commits on both records before accepting performance comparisons.",
    ]

    # Terminal operational outcomes first — never remapped to PASS.
    if base.timeout_status or cand.timeout_status:
        return EvidenceDecision(
            decision=Decision.TIMEOUT,
            comparable=False,
            reasons=["one or both records timed out; timeout is never pass"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=_checksums_equal(base.checksum, cand.checksum),
            host_match=(None if base.host is None or cand.host is None else base.host == cand.host),
            shape_match=_shapes_equal(base.input_shape, cand.input_shape),
            runtime_ratio=_ratio(cand.runtime_s, base.runtime_s),
            runtime_advisory=True,
            tracemalloc_ratio=_ratio(
                None if cand.tracemalloc_peak_bytes is None else float(cand.tracemalloc_peak_bytes),
                None if base.tracemalloc_peak_bytes is None else float(base.tracemalloc_peak_bytes),
            ),
            child_rss_ratio=_ratio(
                None if cand.child_rss_bytes is None else float(cand.child_rss_bytes),
                None if base.child_rss_bytes is None else float(base.child_rss_bytes),
            ),
            evidence_class="performance_only",
            synthetic=bool(base.synthetic and cand.synthetic),
            recommendations=recommendations,
        )

    if _is_child_crash({"outcome": base.raw_outcome}) or _is_child_crash({"outcome": cand.raw_outcome}):
        return EvidenceDecision(
            decision=Decision.CHILD_CRASH,
            comparable=False,
            reasons=["one or both records classified as child_crash"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=None,
            host_match=None,
            shape_match=_shapes_equal(base.input_shape, cand.input_shape),
            runtime_ratio=None,
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    if _is_infra_blocked({"outcome": base.raw_outcome}) or _is_infra_blocked({"outcome": cand.raw_outcome}):
        return EvidenceDecision(
            decision=Decision.INFRASTRUCTURE_BLOCKED,
            comparable=False,
            reasons=["one or both records infrastructure_blocked/failure"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=None,
            host_match=None,
            shape_match=_shapes_equal(base.input_shape, cand.input_shape),
            runtime_ratio=None,
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    if base.source_commit is None or cand.source_commit is None:
        return EvidenceDecision(
            decision=Decision.NOT_COMPARABLE,
            comparable=False,
            reasons=["missing source_commit on baseline and/or candidate"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=None,
            host_match=None,
            shape_match=_shapes_equal(base.input_shape, cand.input_shape),
            runtime_ratio=None,
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    shape_match = _shapes_equal(base.input_shape, cand.input_shape)
    if shape_match is not True:
        reasons.append("input_shape/dtype mismatch or missing")
        return EvidenceDecision(
            decision=Decision.NOT_COMPARABLE,
            comparable=False,
            reasons=reasons,
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=_checksums_equal(base.checksum, cand.checksum),
            host_match=(None if base.host is None or cand.host is None else base.host == cand.host),
            shape_match=shape_match,
            runtime_ratio=None,
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    # Optional dtype already covered by shape dict equality.
    checksum_match = _checksums_equal(base.checksum, cand.checksum)
    if checksum_match is False:
        return EvidenceDecision(
            decision=Decision.CORRECTNESS_FAILURE,
            comparable=False,
            reasons=["checksum mismatch; correctness gates performance"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=False,
            host_match=(None if base.host is None or cand.host is None else base.host == cand.host),
            shape_match=True,
            runtime_ratio=None,
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )
    if checksum_match is None:
        return EvidenceDecision(
            decision=Decision.INCONCLUSIVE,
            comparable=False,
            reasons=["checksum missing on baseline and/or candidate"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=None,
            host_match=(None if base.host is None or cand.host is None else base.host == cand.host),
            shape_match=True,
            runtime_ratio=_ratio(cand.runtime_s, base.runtime_s),
            runtime_advisory=True,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    host_match = None if base.host is None or cand.host is None else (base.host == cand.host)
    runtime_advisory = host_match is not True
    if runtime_advisory:
        reasons.append("cross-host or unknown-host runtime comparison is advisory")
        recommendations.append(
            "Re-run baseline and candidate on the same host for authoritative runtime/RSS."
        )

    tm_ratio = _ratio(
        None if cand.tracemalloc_peak_bytes is None else float(cand.tracemalloc_peak_bytes),
        None if base.tracemalloc_peak_bytes is None else float(base.tracemalloc_peak_bytes),
    )
    rss_ratio = _ratio(
        None if cand.child_rss_bytes is None else float(cand.child_rss_bytes),
        None if base.child_rss_bytes is None else float(base.child_rss_bytes),
    )
    rt_ratio = _ratio(cand.runtime_s, base.runtime_s)

    # Missing memory metrics → missing_metric when both sides lack them for all memory signals
    # and no authoritative metric remains; tracemalloc is the preferred cross-host signal.
    if tm_ratio is None and rss_ratio is None and (runtime_advisory or rt_ratio is None):
        return EvidenceDecision(
            decision=Decision.MISSING_METRIC,
            comparable=False,
            reasons=["tracemalloc and child RSS unavailable (null); cannot judge performance"],
            baseline=base.to_dict(),
            candidate=cand.to_dict(),
            checksum_match=True,
            host_match=host_match,
            shape_match=True,
            runtime_ratio=rt_ratio,
            runtime_advisory=runtime_advisory,
            tracemalloc_ratio=None,
            child_rss_ratio=None,
            evidence_class="performance_only",
            synthetic=True,
            recommendations=recommendations,
        )

    # Authoritative regressions: tracemalloc always; RSS/runtime only when same host.
    regression = False
    if tm_ratio is not None and tm_ratio > max_tracemalloc_regression_ratio:
        regression = True
        reasons.append(
            f"tracemalloc ratio {tm_ratio:.4f} > {max_tracemalloc_regression_ratio}"
        )
    if host_match is True:
        if rss_ratio is not None and rss_ratio > max_child_rss_regression_ratio:
            regression = True
            reasons.append(
                f"child RSS ratio {rss_ratio:.4f} > {max_child_rss_regression_ratio}"
            )
        if rt_ratio is not None and rt_ratio > max_runtime_regression_ratio:
            regression = True
            reasons.append(
                f"runtime ratio {rt_ratio:.4f} > {max_runtime_regression_ratio}"
            )
    elif rt_ratio is not None and rt_ratio > max_runtime_regression_ratio:
        reasons.append(
            f"advisory runtime ratio {rt_ratio:.4f} exceeds threshold (not authoritative)"
        )

    if regression:
        decision = Decision.REGRESSION
        comparable = True
    elif tm_ratio is None and host_match is not True:
        # Checksums match but only advisory runtime — inconclusive performance.
        decision = Decision.INCONCLUSIVE
        comparable = True
        reasons.append("no authoritative memory metric for cross-host comparison")
    else:
        decision = Decision.PASS
        comparable = True
        reasons.append("checksums match; no authoritative regression detected")

    # Surface explicit comparable marker when shapes/checksums align and not blocked.
    if decision in {Decision.PASS, Decision.REGRESSION, Decision.INCONCLUSIVE} and comparable:
        # Keep decision as-is; COMPARABLE is available for callers that only ask
        # about commensurability via decision==COMPARABLE when no verdict yet.
        pass

    return EvidenceDecision(
        decision=decision,
        comparable=comparable,
        reasons=reasons,
        baseline=base.to_dict(),
        candidate=cand.to_dict(),
        checksum_match=True,
        host_match=host_match,
        shape_match=True,
        runtime_ratio=rt_ratio,
        runtime_advisory=runtime_advisory,
        tracemalloc_ratio=tm_ratio,
        child_rss_ratio=rss_ratio,
        evidence_class="performance_only",
        synthetic=True,
        recommendations=recommendations,
    )


def commensurability(baseline: NormalizedEvidence, candidate: NormalizedEvidence) -> Decision:
    """Return ``comparable`` or ``not_comparable`` without performance verdicts."""
    if baseline.source_commit is None or candidate.source_commit is None:
        return Decision.NOT_COMPARABLE
    if _shapes_equal(baseline.input_shape, candidate.input_shape) is not True:
        return Decision.NOT_COMPARABLE
    if baseline.timeout_status or candidate.timeout_status:
        return Decision.NOT_COMPARABLE
    return Decision.COMPARABLE
