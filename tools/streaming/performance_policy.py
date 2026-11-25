"""Additive performance-regression policy evaluator for benchmark JSON records.

This module does **not** run benchmarks and does **not** import or modify any
streaming/kernel code. It consumes already-produced benchmark *records* (plain
dicts, e.g. the JSON emitted by the process-memory telemetry in PR #215) and
decides, under configurable tolerances, whether a candidate is a valid,
correct, non-regressed comparison against a baseline.

Core principles (see ``docs/performance_budget_policy.md``):

* **Correctness gates performance.** A performance verdict is only meaningful
  once numerical equivalence (checksum) is established. Correctness failures and
  performance regressions are reported as *separate* outcomes.
* **Comparisons must be commensurable.** Mismatched input shapes (and, by
  default, mismatched backends) make a comparison invalid rather than a
  regression. Missing metrics are ``None`` -- never silently ``0``.
* **Wall-clock is machine-dependent.** Runtime and RSS ratios are advisory when
  the two records come from different hardware; only same-hardware runtime/RSS
  regressions (and tracemalloc, which tracks Python allocation) drive a
  regression verdict. A comparison never fails *solely* because absolute wall
  time differs across machines.
* **Finite JSON.** :func:`json_safe` replaces NaN/Inf with ``None`` so output is
  always valid JSON.
* **Synthetic benchmarks are performance evidence only** -- every report is
  labeled as such and echoes the records' synthetic flag.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

__all__ = [
    "PolicyThresholds",
    "Verdict",
    "Confidence",
    "PolicyReport",
    "json_safe",
    "compare_records",
    "evaluate_against_budget",
]


# --------------------------------------------------------------------------- #
# JSON safety
# --------------------------------------------------------------------------- #
def json_safe(value: Any) -> Any:
    """Recursively convert to a JSON-safe structure (NaN/Inf -> None)."""
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
    """Serialize to JSON with no NaN/Infinity tokens."""
    import json

    return json.dumps(json_safe(obj), indent=indent, allow_nan=False)


# --------------------------------------------------------------------------- #
# Policy configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PolicyThresholds:
    """Configurable tolerances -- no fragile hardcoded thresholds elsewhere.

    Ratios are ``candidate / baseline``; a value ``> max_*_regression_ratio``
    flags a regression on that metric.
    """
    checksum_rel_tol: float = 1e-9
    max_runtime_regression_ratio: float = 1.25
    max_peak_rss_regression_ratio: float = 1.25
    max_tracemalloc_regression_ratio: float = 1.10
    min_repetitions: int = 3
    #: Relative spread ``(mean-best)/best`` above which timing is "noisy".
    max_runtime_rel_spread: float = 0.50
    require_same_backend: bool = True
    require_same_hardware: bool = False


class Verdict(str, Enum):
    INVALID_COMPARISON = "invalid_comparison"      # not commensurable
    CORRECTNESS_FAILURE = "correctness_failure"    # checksums disagree
    INCONCLUSIVE = "inconclusive"                  # required data missing
    REGRESSION = "regression"                      # authoritative metric regressed
    PASS = "pass"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------------------- #
# Record access helpers (tolerant of missing fields; never fabricate)
# --------------------------------------------------------------------------- #
def _get_int(record: Dict[str, Any], key: str) -> Optional[int]:
    value = record.get(key)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value is not None else None


def _get_float(record: Dict[str, Any], key: str) -> Optional[float]:
    value = record.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _hardware_of(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract hardware metadata if present, else derive a platform hint."""
    hw = record.get("hardware")
    if isinstance(hw, dict) and hw:
        return {str(k): hw[k] for k in sorted(hw)}
    providers = record.get("providers")
    if isinstance(providers, dict) and providers.get("platform"):
        return {"platform": providers["platform"]}
    return None


def _is_synthetic(record: Dict[str, Any]) -> bool:
    if isinstance(record.get("synthetic"), bool):
        return record["synthetic"]
    label = str(record.get("label", "")).lower()
    return "synth" in label or bool(record.get("fixture"))


def _ratio(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    r = candidate / baseline
    return r if math.isfinite(r) else None


def _rel_spread(record: Dict[str, Any]) -> Optional[float]:
    best = _get_float(record, "wall_best_s")
    mean = _get_float(record, "wall_mean_s")
    if best is None or mean is None or best <= 0:
        return None
    return max(0.0, (mean - best) / best)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@dataclass
class PolicyReport:
    verdict: Verdict
    valid_comparison: bool
    invalid_reasons: List[str]
    correctness_ok: Optional[bool]
    checksum_rel_err: Optional[float]
    runtime_ratio: Optional[float]
    runtime_regression: Optional[bool]
    peak_rss_ratio: Optional[float]
    peak_rss_regression: Optional[bool]
    tracemalloc_ratio: Optional[float]
    tracemalloc_regression: Optional[bool]
    backend: Dict[str, Any]
    hardware: Dict[str, Any]
    input_shape: Dict[str, Any]
    chunk_size: Dict[str, Any]
    repetitions: Dict[str, Any]
    confidence: Confidence
    measurement_quality: Dict[str, Any]
    evidence_class: str
    synthetic: bool
    thresholds: Dict[str, Any]
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


_PROCESS_ISOLATION_RECOMMENDATION = (
    "Measure RSS in isolated processes per configuration: peak RSS is a "
    "process-lifetime high-water mark on POSIX and includes interpreter and "
    "imported-library memory, so in-process comparisons conflate workloads."
)


def compare_records(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    thresholds: PolicyThresholds = PolicyThresholds(),
) -> PolicyReport:
    """Compare two benchmark records under ``thresholds`` and return a report."""
    invalid_reasons: List[str] = []
    recommendations: List[str] = [_PROCESS_ISOLATION_RECOMMENDATION]

    base_dims = baseline.get("input_dims")
    cand_dims = candidate.get("input_dims")
    input_shape = {"baseline": base_dims, "candidate": cand_dims,
                   "match": base_dims == cand_dims and base_dims is not None}

    base_backend = baseline.get("backend")
    cand_backend = candidate.get("backend")
    backend = {"baseline": base_backend, "candidate": cand_backend,
               "match": base_backend == cand_backend}

    base_hw = _hardware_of(baseline)
    cand_hw = _hardware_of(candidate)
    hw_match = (base_hw is not None and cand_hw is not None and base_hw == cand_hw)
    hardware = {"baseline": base_hw, "candidate": cand_hw, "match": hw_match,
                "known": base_hw is not None and cand_hw is not None}

    chunk_size = {"baseline": _get_int(baseline, "chunk_size"),
                  "candidate": _get_int(candidate, "chunk_size")}
    base_reps = _get_int(baseline, "repetitions")
    cand_reps = _get_int(candidate, "repetitions")
    repetitions = {"baseline": base_reps, "candidate": cand_reps}

    # ---- Structural validity ------------------------------------------------
    if not input_shape["match"]:
        invalid_reasons.append("input_shape_mismatch")           # rule 1
    if thresholds.require_same_backend and not backend["match"]:
        invalid_reasons.append("backend_mismatch")               # rule 9
    if thresholds.require_same_hardware and not hw_match:
        invalid_reasons.append("hardware_mismatch")
    valid_comparison = not invalid_reasons

    # ---- Ratios (computed even if advisory; missing -> None, never 0) -------
    runtime_ratio = _ratio(_get_float(candidate, "wall_best_s"),
                           _get_float(baseline, "wall_best_s"))
    peak_rss_ratio = _ratio(_get_float(candidate, "peak_rss_bytes"),
                            _get_float(baseline, "peak_rss_bytes"))   # rule 2
    tracemalloc_ratio = _ratio(_get_float(candidate, "tracemalloc_peak_bytes"),
                               _get_float(baseline, "tracemalloc_peak_bytes"))

    runtime_regression = (None if runtime_ratio is None
                          else runtime_ratio > thresholds.max_runtime_regression_ratio)
    peak_rss_regression = (None if peak_rss_ratio is None
                           else peak_rss_ratio > thresholds.max_peak_rss_regression_ratio)
    tracemalloc_regression = (None if tracemalloc_ratio is None
                              else tracemalloc_ratio > thresholds.max_tracemalloc_regression_ratio)

    # ---- Correctness (numerical equivalence gates performance) -------------
    base_chk = _get_float(baseline, "checksum")
    cand_chk = _get_float(candidate, "checksum")
    if base_chk is None or cand_chk is None:
        correctness_ok: Optional[bool] = None
        checksum_rel_err: Optional[float] = None
    else:
        denom = max(abs(base_chk), abs(cand_chk), 1e-300)
        checksum_rel_err = abs(base_chk - cand_chk) / denom
        correctness_ok = checksum_rel_err <= thresholds.checksum_rel_tol

    # ---- Confidence / measurement quality ----------------------------------
    base_spread = _rel_spread(baseline)
    cand_spread = _rel_spread(candidate)
    low_reps = (base_reps is not None and base_reps < thresholds.min_repetitions) or \
               (cand_reps is not None and cand_reps < thresholds.min_repetitions) or \
               base_reps is None or cand_reps is None
    noisy = (base_spread is not None and base_spread > thresholds.max_runtime_rel_spread) or \
            (cand_spread is not None and cand_spread > thresholds.max_runtime_rel_spread)
    if low_reps or noisy:
        confidence = Confidence.LOW
    elif not hw_match:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.HIGH
    measurement_quality = {
        "baseline_rel_spread": base_spread,
        "candidate_rel_spread": cand_spread,
        "low_repetitions": bool(low_reps),
        "noisy_runtime": bool(noisy),
        "hardware_comparable": bool(hw_match),
        "runtime_rss_authoritative": bool(hw_match),
    }
    if not hw_match:
        recommendations.append(
            "Hardware metadata differs or is unknown: treat runtime and peak-RSS "
            "ratios as advisory; rely on tracemalloc (Python-allocation) ratio and "
            "numerical checksums for cross-machine comparisons."
        )
    if low_reps:
        recommendations.append(
            f"Increase repetitions to >= {thresholds.min_repetitions} for a stable timing estimate."
        )

    # ---- Verdict (precedence) ----------------------------------------------
    # Only same-hardware runtime/peak-RSS regressions are authoritative; the
    # tracemalloc regression is authoritative regardless of hardware.
    authoritative_regressions = [tracemalloc_regression]
    if hw_match:
        authoritative_regressions.extend([runtime_regression, peak_rss_regression])
    any_regression = any(flag is True for flag in authoritative_regressions)

    if not valid_comparison:
        verdict = Verdict.INVALID_COMPARISON
    elif correctness_ok is False:
        verdict = Verdict.CORRECTNESS_FAILURE                     # rule 5
    elif correctness_ok is None:
        verdict = Verdict.INCONCLUSIVE                            # rule 4: need equivalence
    elif any_regression:
        verdict = Verdict.REGRESSION
    else:
        verdict = Verdict.PASS

    synthetic = _is_synthetic(baseline) and _is_synthetic(candidate)

    return PolicyReport(
        verdict=verdict,
        valid_comparison=valid_comparison,
        invalid_reasons=invalid_reasons,
        correctness_ok=correctness_ok,
        checksum_rel_err=checksum_rel_err,
        runtime_ratio=runtime_ratio,
        runtime_regression=runtime_regression,
        peak_rss_ratio=peak_rss_ratio,
        peak_rss_regression=peak_rss_regression,
        tracemalloc_ratio=tracemalloc_ratio,
        tracemalloc_regression=tracemalloc_regression,
        backend=backend,
        hardware=hardware,
        input_shape=input_shape,
        chunk_size=chunk_size,
        repetitions=repetitions,
        confidence=confidence,
        measurement_quality=measurement_quality,
        evidence_class="performance_only",                       # rule 6
        synthetic=synthetic,
        thresholds=asdict(thresholds),
        recommendations=recommendations,
    )


def evaluate_against_budget(
    record: Dict[str, Any],
    *,
    peak_rss_budget_bytes: Optional[int] = None,
    tracemalloc_budget_bytes: Optional[int] = None,
    runtime_budget_s: Optional[float] = None,
    thresholds: PolicyThresholds = PolicyThresholds(),
) -> Dict[str, Any]:
    """Check a single record against optional absolute budgets.

    Missing metrics yield ``None`` (unknown), never a pass-by-omission. Runtime
    and RSS budgets are inherently hardware-dependent; the report flags this.
    """
    def _check(value: Optional[float], budget: Optional[float]) -> Optional[bool]:
        if budget is None:
            return None
        if value is None:
            return None                      # unknown, not a pass (rule 2)
        return value <= budget

    peak_rss = _get_float(record, "peak_rss_bytes")
    tracemalloc_peak = _get_float(record, "tracemalloc_peak_bytes")
    runtime = _get_float(record, "wall_best_s")

    checks = {
        "peak_rss_within_budget": _check(peak_rss, peak_rss_budget_bytes),
        "tracemalloc_within_budget": _check(tracemalloc_peak, tracemalloc_budget_bytes),
        "runtime_within_budget": _check(runtime, runtime_budget_s),
    }
    evaluated = [v for v in checks.values() if v is not None]
    within_budget = all(evaluated) if evaluated else None

    return json_safe({
        "within_budget": within_budget,
        "checks": checks,
        "measured": {
            "peak_rss_bytes": peak_rss,
            "tracemalloc_peak_bytes": tracemalloc_peak,
            "wall_best_s": runtime,
        },
        "budgets": {
            "peak_rss_bytes": peak_rss_budget_bytes,
            "tracemalloc_peak_bytes": tracemalloc_budget_bytes,
            "wall_best_s": runtime_budget_s,
        },
        "backend": record.get("backend"),
        "input_shape": record.get("input_dims"),
        "hardware": _hardware_of(record),
        "evidence_class": "performance_only",
        "synthetic": _is_synthetic(record),
        "notes": [
            "Absolute runtime and peak-RSS budgets are hardware- and allocator-"
            "dependent; calibrate per machine.",
            _PROCESS_ISOLATION_RECOMMENDATION,
        ],
    })
