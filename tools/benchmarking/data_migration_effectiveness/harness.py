"""Harness: separate correctness (checksum) from performance telemetry."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from tools.benchmarking.data_migration_effectiveness.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.data_migration_effectiveness.fixtures import make_fixture
from tools.benchmarking.data_migration_effectiveness.schema import (
    EVIDENCE_CLASS,
    OPT_DISK_ABS_BYTES,
    OPT_DISK_RATIO,
    OPT_RT_ABS_S,
    OPT_RT_RATIO,
    OPT_TM_ABS_BYTES,
    OPT_TM_RATIO,
    SCHEMA_VERSION,
    TargetStatus,
)
from tools.benchmarking.data_migration_effectiveness.telemetry import json_safe, measure
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS, production_available


def _ratio(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    r = candidate / baseline
    if r != r or r in (float("inf"), float("-inf")):
        return None
    return r


def _telemetry_view(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "runtime_best_s": m.get("runtime_best_s"),
        "runtime_mean_s": m.get("runtime_mean_s"),
        "planning_latency_s": m.get("planning_latency_s"),
        "tracemalloc_peak_bytes": m.get("tracemalloc_peak_bytes"),
        "rss_after_bytes": m.get("rss_after_bytes"),
        "disk_bytes": m.get("disk_bytes"),
        "cache_occupancy_bytes": m.get("cache_occupancy_bytes"),
        "evicted_bytes": m.get("evicted_bytes"),
        "retry_attempts": m.get("retry_attempts"),
    }


def run_target(
    spec_name: str,
    budgets: ResourceBudgets,
    *,
    seed: int = 0,
    size: Optional[int] = None,
    repetitions: int = 1,
) -> Dict[str, Any]:
    spec = TARGETS[spec_name]
    size = spec.default_size if size is None else size
    fixture = make_fixture(seed, size)
    try:
        baseline = measure(lambda: spec.baseline(fixture), repetitions=repetitions)
        candidate = measure(lambda: spec.candidate(fixture), repetitions=repetitions)
    except Exception as exc:
        return json_safe(
            {
                "target": spec.name,
                "path_family": spec.path_family,
                "status": TargetStatus.ERROR.value,
                "error": str(exc),
                "deterministic": {
                    "checksum_baseline": None,
                    "checksum_candidate": None,
                    "checksum_match": None,
                },
                "telemetry": None,
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
            }
        )

    checksum_match = (
        baseline.get("ok") and candidate.get("ok") and baseline.get("checksum") == candidate.get("checksum")
    )
    if not baseline.get("ok") or not candidate.get("ok"):
        status = TargetStatus.MALFORMED_RECORD.value
    elif not checksum_match:
        status = TargetStatus.CHECKSUM_MISMATCH.value
    elif candidate.get("status") == "timeout" or baseline.get("status") == "timeout":
        status = TargetStatus.TIMEOUT.value
    elif candidate.get("status") == "rejected":
        status = TargetStatus.REJECTED.value
    else:
        status = TargetStatus.OK.value

    budget = compare_budget(candidate, budgets)
    if budget["within_budget"] is False:
        status = TargetStatus.BUDGET_OVERRUN.value

    tm_ratio = _ratio(candidate.get("tracemalloc_peak_bytes"), baseline.get("tracemalloc_peak_bytes"))
    rt_ratio = _ratio(candidate.get("runtime_best_s"), baseline.get("runtime_best_s"))
    disk_ratio = _ratio(candidate.get("disk_bytes"), baseline.get("disk_bytes"))
    tm_abs = candidate.get("tracemalloc_peak_bytes")
    rt_abs = candidate.get("runtime_best_s")
    disk_abs = candidate.get("disk_bytes")

    # Policy-reject baseline is a no-op stub; do not treat extra fetch work as a patch hint.
    emit_opt = spec.path_family != "policy_vs_bounded_cache"
    opt: List[Dict[str, Any]] = []
    if (
        emit_opt
        and tm_ratio is not None
        and tm_ratio > OPT_TM_RATIO
        and tm_abs is not None
        and tm_abs >= OPT_TM_ABS_BYTES
    ):
        opt.append(
            {
                "target": spec.name,
                "kind": "memory",
                "metric": "tracemalloc_peak_bytes",
                "ratio": tm_ratio,
                "supported_by": "measured_tracemalloc_ratio",
                "recommendation": (
                    f"{spec.name}: candidate tracemalloc/baseline={tm_ratio:.3f}; "
                    "measured allocation hint only — not a production patch."
                ),
            }
        )
    if (
        emit_opt
        and rt_ratio is not None
        and rt_ratio > OPT_RT_RATIO
        and rt_abs is not None
        and rt_abs >= OPT_RT_ABS_S
    ):
        opt.append(
            {
                "target": spec.name,
                "kind": "runtime",
                "metric": "runtime_best_s",
                "ratio": rt_ratio,
                "supported_by": "advisory_runtime_ratio",
                "recommendation": (
                    f"{spec.name}: advisory runtime ratio={rt_ratio:.3f}; "
                    "re-measure on the same host before acting."
                ),
            }
        )
    if (
        emit_opt
        and disk_ratio is not None
        and disk_ratio > OPT_DISK_RATIO
        and disk_abs is not None
        and disk_abs >= OPT_DISK_ABS_BYTES
    ):
        opt.append(
            {
                "target": spec.name,
                "kind": "disk",
                "metric": "disk_bytes",
                "ratio": disk_ratio,
                "supported_by": "measured_disk_ratio",
                "recommendation": (
                    f"{spec.name}: candidate disk/baseline={disk_ratio:.3f}; "
                    "measured footprint hint only."
                ),
            }
        )

    return json_safe(
        {
            "target": spec.name,
            "path_family": spec.path_family,
            "status": status,
            "deterministic": {
                "checksum_baseline": baseline.get("checksum"),
                "checksum_candidate": candidate.get("checksum"),
                "checksum_match": checksum_match,
                "feature_count": candidate.get("feature_count"),
                "correctness_baseline": baseline.get("correctness"),
                "correctness_candidate": candidate.get("correctness"),
                "budget": budget,
                "rejected_full_object": candidate.get("rejected_full_object")
                or baseline.get("rejected_full_object"),
            },
            "telemetry": {
                "baseline": _telemetry_view(baseline),
                "candidate": _telemetry_view(candidate),
                "worker_count": 1,
                "tracemalloc_peak_ratio_candidate_over_baseline": tm_ratio,
                "runtime_ratio_candidate_over_baseline_advisory": rt_ratio,
                "disk_ratio_candidate_over_baseline": disk_ratio,
            },
            "measurement_quality": {
                "missing_metrics_are_null": True,
                "runtime_and_rss_are_advisory": True,
                "tracemalloc_and_disk_authoritative": True,
                "correctness_separated_from_performance": True,
            },
            "optimization_candidates": opt,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "scientific_improvement_claimed": False,
        }
    )


def run_all(
    *,
    seed: int = 0,
    size: int = 64,
    repetitions: int = 1,
    budgets: Optional[ResourceBudgets] = None,
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    budgets = budgets or ResourceBudgets()
    names = list(targets) if targets is not None else sorted(TARGETS.keys())
    results = [
        run_target(name, budgets, seed=seed, size=size, repetitions=repetitions) for name in names if name in TARGETS
    ]
    statuses = {}
    for row in results:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    all_match = all((r.get("deterministic") or {}).get("checksum_match") for r in results)
    opt: List[str] = []
    for row in results:
        opt.extend(row.get("optimization_candidates") or [])
    regressions = [
        r["target"]
        for r in results
        if r.get("status") in {TargetStatus.CHECKSUM_MISMATCH.value, TargetStatus.ERROR.value}
    ]
    return json_safe(
        {
            "schema": SCHEMA_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "scientific_improvement_claimed": False,
            "network_accessed": False,
            "full_dataset_download": False,
            "config": {
                "seed": seed,
                "size": size,
                "repetitions": repetitions,
                "targets": names,
                "max_workers": 1,
            },
            "production_available": production_available(),
            "summary": statuses,
            "all_checksums_match": all_match,
            "regressions": regressions,
            "optimization_candidates": opt,
            "results": results,
            "limitations": [
                "Synthetic local fixtures only; not empirical neuroscience.",
                "Does not claim scientific improvement of bounded access.",
                "Missing metrics remain null, never fabricated zero.",
                "Runtime and RSS are advisory; tracemalloc and disk are authoritative when present.",
                "No OpenNeuro, AWS, DANDI, or other remote service was contacted.",
            ],
        }
    )
