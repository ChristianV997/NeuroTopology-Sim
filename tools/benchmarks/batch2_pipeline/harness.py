"""Benchmark harness: equivalence, budgets, counter deltas, bottleneck ranking."""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from .budgets import ResourceBudgets, compare_budget
from .schema import COUNTER_KEYS, EVIDENCE_CLASS, SCHEMA_VERSION, TargetStatus
from .telemetry import json_safe, measure
from .workloads import TARGETS, TargetSpec

STATUS_OK = TargetStatus.OK.value
STATUS_CHECKSUM_MISMATCH = TargetStatus.CHECKSUM_MISMATCH.value
STATUS_MALFORMED_RECORD = TargetStatus.MALFORMED_RECORD.value
STATUS_ERROR = TargetStatus.ERROR.value
STATUS_BUDGET_OVERRUN = TargetStatus.BUDGET_OVERRUN.value

TOOLING_AVAILABILITY = {
    "ecc:benchmark": "UNAVAILABLE",
    "ecc:benchmark-methodology": "UNAVAILABLE",
    "ecc:benchmark-optimization-loop": "UNAVAILABLE",
    "ecc:data-throughput-accelerator": "UNAVAILABLE",
    "ecc:python-testing": "UNAVAILABLE",
    "ecc:security-scan": "UNAVAILABLE",
    "ecc:delivery-gate": "UNAVAILABLE",
    "gstack/investigate": "UNAVAILABLE",
    "gstack/plan-eng-review": "UNAVAILABLE",
    "gstack/review": "UNAVAILABLE",
    "coderos-operator": "UNAVAILABLE",
    "openai-developers:agents": "UNAVAILABLE",
    "REA": "REA_UNAVAILABLE",
}


def _ratio(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    r = candidate / baseline
    return r if r == r and r not in (float("inf"), float("-inf")) else None


def _counter_view(m: Dict[str, Any]) -> Dict[str, Any]:
    return {key: m.get(key) for key in COUNTER_KEYS} | {
        "process_work_s": m.get("process_work_s"),
        "checkpoint_s": m.get("checkpoint_s"),
    }


def _telemetry_view(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "runtime_best_s": m.get("runtime_best_s"),
        "runtime_mean_s": m.get("runtime_mean_s"),
        "tracemalloc_peak_bytes": m.get("tracemalloc_peak_bytes"),
        "rss_after_bytes": m.get("rss_after_bytes"),
        "disk_bytes": m.get("disk_bytes"),
        "input_size": m.get("input_size"),
        "worker_count": m.get("worker_count"),
        "counters": _counter_view(m),
    }


def _confidence(baseline: Dict[str, Any], candidate: Dict[str, Any], repetitions: int) -> Dict[str, Any]:
    spreads = []
    for m in (baseline, candidate):
        best, mean = m.get("runtime_best_s"), m.get("runtime_mean_s")
        if best and mean and best > 0:
            spreads.append(max(0.0, (mean - best) / best))
    noisy = any(s > 0.5 for s in spreads)
    low_reps = repetitions < 3
    rss_known = baseline.get("rss_after_bytes") is not None
    if low_reps or noisy:
        level = "low"
    elif not rss_known:
        level = "medium"
    else:
        level = "high"
    return {
        "level": level,
        "repetitions": repetitions,
        "runtime_rel_spread": max(spreads) if spreads else None,
        "rss_available": rss_known,
        "runtime_and_rss_are_advisory": True,
    }


def _counter_deltas(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    deltas: Dict[str, Any] = {}
    for key in COUNTER_KEYS:
        b, c = baseline.get(key), candidate.get(key)
        if b is None or c is None:
            deltas[key] = None
        else:
            deltas[key] = int(c) - int(b)
    for key in ("process_work_s", "checkpoint_s"):
        b, c = baseline.get(key), candidate.get(key)
        if b is None or c is None:
            deltas[key] = None
        else:
            deltas[key] = float(c) - float(b)
    return deltas


def run_target(
    spec: TargetSpec,
    budgets: ResourceBudgets,
    *,
    seed: int = 0,
    size: Optional[int] = None,
    repetitions: int = 3,
) -> Dict[str, Any]:
    """Run one target's baseline + candidate and return a finite record."""
    size = spec.default_size if size is None else size
    recommendations: List[str] = []
    try:
        fixture = spec.make_fixture(seed, size)
        baseline = measure(lambda: spec.baseline(fixture), repetitions=repetitions)
        candidate = measure(lambda: spec.candidate(fixture), repetitions=repetitions)
    except Exception as exc:
        return json_safe(
            {
                "target": spec.name,
                "path_family": spec.path_family,
                "status": STATUS_ERROR,
                "error": str(exc),
                "deterministic": {
                    "checksum_baseline": None,
                    "checksum_candidate": None,
                    "checksum_match": None,
                    "feature_count": None,
                    "budget": None,
                    "input_size": None,
                },
                "telemetry": None,
                "counter_deltas": None,
                "confidence": None,
                "recommendations": ["target raised an exception; investigate fixture/workload"],
                "optimization_candidates": [],
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
            }
        )

    if not baseline.get("ok") or not candidate.get("ok"):
        status = STATUS_MALFORMED_RECORD
        checksum_match = None
        recommendations.append("workload returned a malformed record (missing 'checksum')")
    else:
        checksum_match = baseline["checksum"] == candidate["checksum"]
        status = STATUS_OK if checksum_match else STATUS_CHECKSUM_MISMATCH
        if not checksum_match:
            recommendations.append("correctness regression: candidate checksum != baseline")

    budget = compare_budget(candidate, budgets)
    if budget["within_budget"] is False:
        over = [k for k, v in budget["checks"].items() if v is False]
        recommendations.append(
            f"candidate exceeds budget ({', '.join(over)}); reduce size or raise the budget"
        )
        if status == STATUS_OK:
            status = STATUS_BUDGET_OVERRUN

    tm_ratio = _ratio(candidate.get("tracemalloc_peak_bytes"), baseline.get("tracemalloc_peak_bytes"))
    rt_ratio = _ratio(candidate.get("runtime_best_s"), baseline.get("runtime_best_s"))
    disk_ratio = _ratio(candidate.get("disk_bytes"), baseline.get("disk_bytes"))
    deltas = _counter_deltas(baseline, candidate)
    opt: List[Dict[str, Any]] = []

    if (baseline.get("read_counts") or 0) > (candidate.get("read_counts") or 0):
        opt.append(
            {
                "target": spec.name,
                "kind": "read_amplification",
                "metric": "read_counts",
                "baseline": baseline.get("read_counts"),
                "candidate": candidate.get("read_counts"),
                "supported_by": "measured_counter_delta",
                "recommendation": (
                    "Repeated full-recording reads dominate this target. Prefer a single "
                    "materialization or window cache. Do not change production from this report."
                ),
            }
        )
        recommendations.append("baseline re-reads the full recording more often than candidate")
    if (baseline.get("preprocess_calls") or 0) > (candidate.get("preprocess_calls") or 0):
        opt.append(
            {
                "target": spec.name,
                "kind": "preprocess_amplification",
                "metric": "preprocess_calls",
                "baseline": baseline.get("preprocess_calls"),
                "candidate": candidate.get("preprocess_calls"),
                "supported_by": "measured_counter_delta",
                "recommendation": (
                    "Full-recording preprocessing per window is an all-day bottleneck. "
                    "Preprocess once and slice windows. Measure again after a dedicated patch."
                ),
            }
        )
        recommendations.append("baseline preprocess calls exceed candidate")
    if (baseline.get("fsync_calls") or 0) > (candidate.get("fsync_calls") or 0):
        opt.append(
            {
                "target": spec.name,
                "kind": "checkpoint_overhead",
                "metric": "fsync_calls",
                "baseline": baseline.get("fsync_calls"),
                "candidate": candidate.get("fsync_calls"),
                "baseline_checkpoint_s": baseline.get("checkpoint_s"),
                "candidate_checkpoint_s": candidate.get("checkpoint_s"),
                "supported_by": "measured_fsync_and_checkpoint_split",
                "recommendation": (
                    "Checkpoint/fsync overhead is separable from process work. Batch "
                    "atomic checkpoints instead of fsync-per-item."
                ),
            }
        )
    if (baseline.get("manifest_writes") or 0) > (candidate.get("manifest_writes") or 0):
        opt.append(
            {
                "target": spec.name,
                "kind": "manifest_amplification",
                "metric": "manifest_writes",
                "baseline": baseline.get("manifest_writes"),
                "candidate": candidate.get("manifest_writes"),
                "supported_by": "measured_counter_delta",
                "recommendation": "Batch manifest persistence; avoid rewrite-per-item.",
            }
        )
    if (
        disk_ratio is not None
        and disk_ratio > 1.15
        and candidate.get("disk_bytes") is not None
        and baseline.get("disk_bytes") is not None
        and baseline["disk_bytes"] < candidate["disk_bytes"]
    ):
        # Prefer noting when baseline wastes more disk (ratio inverted for waste).
        pass
    if (
        baseline.get("disk_bytes") is not None
        and candidate.get("disk_bytes") is not None
        and baseline["disk_bytes"] > candidate["disk_bytes"]
    ):
        opt.append(
            {
                "target": spec.name,
                "kind": "disk",
                "metric": "disk_bytes",
                "baseline": baseline.get("disk_bytes"),
                "candidate": candidate.get("disk_bytes"),
                "ratio_candidate_over_baseline": disk_ratio,
                "supported_by": "measured_disk_bytes",
                "recommendation": (
                    "Leftover .part staging doubles disk under the naive subject loop. "
                    "Atomic replace without orphaned parts reduces footprint."
                ),
            }
        )
    if (
        tm_ratio is not None
        and tm_ratio > 1.15
        and candidate.get("tracemalloc_peak_bytes") is not None
        and candidate["tracemalloc_peak_bytes"] >= 64_000
    ):
        recommendations.append("candidate tracemalloc peak exceeds baseline; review allocations")
        opt.append(
            {
                "target": spec.name,
                "kind": "memory",
                "metric": "tracemalloc_peak_bytes",
                "ratio": tm_ratio,
                "supported_by": "measured_tracemalloc_ratio",
                "recommendation": "Review candidate allocations; do not patch production from a single host sample.",
            }
        )
    if (
        rt_ratio is not None
        and rt_ratio > 1.25
        and candidate.get("runtime_best_s") is not None
        and candidate["runtime_best_s"] >= 0.002
    ):
        recommendations.append("candidate runtime exceeds baseline (advisory, host-dependent)")

    confidence = _confidence(baseline, candidate, repetitions)
    if confidence["level"] == "low":
        recommendations.append("low measurement confidence; increase repetitions")

    # Speedup claim only when measured against reproducible baseline and ratio < 1.
    measured_speedup = None
    if rt_ratio is not None and rt_ratio < 1.0:
        measured_speedup = {
            "runtime_ratio_candidate_over_baseline": rt_ratio,
            "claim": "measured_against_reproducible_baseline",
            "scientific_claim": False,
        }

    return json_safe(
        {
            "target": spec.name,
            "path_family": spec.path_family,
            "status": status,
            "production_module": candidate.get("production_module") or baseline.get("production_module"),
            "production_available": False,
            "deterministic": {
                "checksum_baseline": baseline.get("checksum"),
                "checksum_candidate": candidate.get("checksum"),
                "checksum_match": checksum_match,
                "feature_count": candidate.get("feature_count"),
                "budget": budget,
                "input_size": candidate.get("input_size") or baseline.get("input_size"),
            },
            "telemetry": {
                "baseline": _telemetry_view(baseline),
                "candidate": _telemetry_view(candidate),
                "tracemalloc_peak_ratio_candidate_over_baseline": tm_ratio,
                "runtime_ratio_candidate_over_baseline_advisory": rt_ratio,
                "disk_ratio_candidate_over_baseline": disk_ratio,
                "worker_count": candidate.get("worker_count") or 1,
                "measured_speedup": measured_speedup,
            },
            "counter_deltas": deltas,
            "confidence": confidence,
            "measurement_quality": {
                "deterministic_fields": [
                    "checksum_baseline",
                    "checksum_candidate",
                    "checksum_match",
                    "feature_count",
                    "budget",
                    "status",
                    "input_size",
                    "read_counts",
                    "preprocess_calls",
                    "cache_hits",
                    "manifest_writes",
                    "fsync_calls",
                    "worker_count",
                ],
                "telemetry_fields": [
                    "runtime_best_s",
                    "runtime_mean_s",
                    "tracemalloc_peak_bytes",
                    "rss_after_bytes",
                    "disk_bytes",
                    "process_work_s",
                    "checkpoint_s",
                ],
                "missing_metrics_are_null": True,
            },
            "recommendations": recommendations,
            "optimization_candidates": opt,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
        }
    )


def rank_bottlenecks(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank by baseline waste signals (reads/preprocess/fsync), never zero-filling nulls."""
    rows: List[Dict[str, Any]] = []
    for rec in results:
        base = ((rec.get("telemetry") or {}).get("baseline") or {}).get("counters") or {}
        tel = (rec.get("telemetry") or {}).get("baseline") or {}
        runtime = tel.get("runtime_best_s")
        memory = tel.get("tracemalloc_peak_bytes")
        reads = base.get("read_counts")
        preprocess = base.get("preprocess_calls")
        fsyncs = base.get("fsync_calls")
        score_parts = [
            v
            for v in (
                None if reads is None else float(reads),
                None if preprocess is None else float(preprocess),
                None if fsyncs is None else float(fsyncs),
                runtime,
                None if memory is None else memory / 1e9,
            )
            if v is not None
        ]
        rows.append(
            {
                "target": rec.get("target"),
                "status": rec.get("status"),
                "baseline_read_counts": reads,
                "baseline_preprocess_calls": preprocess,
                "baseline_fsync_calls": fsyncs,
                "baseline_runtime_best_s": runtime,
                "baseline_tracemalloc_peak_bytes": memory,
                "runtime_ratio_advisory": (rec.get("telemetry") or {}).get(
                    "runtime_ratio_candidate_over_baseline_advisory"
                ),
                "score_proxy": max(score_parts) if score_parts else None,
            }
        )
    rows.sort(key=lambda r: (r["score_proxy"] is None, -(r["score_proxy"] or 0.0), r["target"] or ""))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def collect_optimization_candidates(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in results:
        for cand in rec.get("optimization_candidates") or []:
            out.append(cand)
    return out


def run_all(
    budgets: Optional[ResourceBudgets] = None,
    *,
    seed: int = 0,
    size: Optional[int] = None,
    repetitions: int = 3,
    targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run all (or selected) targets sequentially (bounded, no concurrency)."""
    budgets = budgets or ResourceBudgets()
    names = sorted(TARGETS.keys()) if targets is None else [t for t in targets if t in TARGETS]
    results = [
        run_target(TARGETS[name], budgets, seed=seed, size=size, repetitions=repetitions)
        for name in names
    ]
    summary: Dict[str, int] = {}
    for rec in results:
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
    matches = [r["deterministic"]["checksum_match"] for r in results]
    known = [m for m in matches if m is not None]
    all_equivalent = all(known) if known else None
    budget_verdicts = [(r.get("deterministic") or {}).get("budget", {}) or {} for r in results]
    evaluated = [v.get("within_budget") for v in budget_verdicts if v.get("within_budget") is not None]
    all_within_budget = all(evaluated) if evaluated else None
    ranking = rank_bottlenecks(results)
    opt = collect_optimization_candidates(results)
    return json_safe(
        {
            "schema": SCHEMA_VERSION,
            "schema_version": SCHEMA_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "config": {
                "seed": seed,
                "size": size,
                "repetitions": repetitions,
                "targets": names,
                "max_workers": 1,
            },
            "budgets": budgets.to_dict(),
            "telemetry_environment": {
                "platform": sys.platform,
                "python_version": sys.version.split()[0],
            },
            "tooling_availability": dict(TOOLING_AVAILABILITY),
            "production_probe": {
                "network_used": False,
                "remote_data_accessed": False,
                "production_code_modified": False,
                "production_modules_imported": False,
            },
            "num_targets": len(results),
            "summary": summary,
            "all_equivalent": all_equivalent,
            "all_within_budget": all_within_budget,
            "bottleneck_ranking": ranking,
            "optimization_candidates": opt,
            "results": results,
            "notes": [
                "Synthetic performance evidence only; no scientific claims, no real data, "
                "no OpenNeuro/AWS/DANDI access, no Awareness Studio import.",
                "runtime and RSS are hardware-dependent (advisory); counters, tracemalloc, "
                "and disk usage are the comparable signals.",
                "Checkpoint/fsync time is reported separately from process_work_s.",
                "Deterministic fields are reproducible across runs; telemetry fields vary.",
                "Missing metrics are null, never zero.",
                "No speedup is claimed unless measured against a reproducible baseline.",
                "Optimization candidates do not modify production code.",
                "Required ecc/gstack/REA/coderos tooling was UNAVAILABLE in this environment; "
                "methodology follows the in-repo pipeline_efficiency pattern.",
            ],
        }
    )
