"""Benchmark harness: equivalence, budgets, bottleneck ranking, finite reports.

Deterministic fields (checksums, feature counts, budget verdicts, status) are
stable across runs. Telemetry fields vary and are stored separately.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from .adapters import probe_all
from .budgets import ResourceBudgets, compare_budget
from .schema import EVIDENCE_CLASS, SCHEMA_VERSION, TargetStatus
from .telemetry import json_safe, measure
from .workloads import TARGETS, TargetSpec

STATUS_OK = TargetStatus.OK.value
STATUS_CHECKSUM_MISMATCH = TargetStatus.CHECKSUM_MISMATCH.value
STATUS_MALFORMED_RECORD = TargetStatus.MALFORMED_RECORD.value
STATUS_ERROR = TargetStatus.ERROR.value
STATUS_BUDGET_OVERRUN = TargetStatus.BUDGET_OVERRUN.value


def _ratio(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    r = candidate / baseline
    return r if r == r and r not in (float("inf"), float("-inf")) else None


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


def _telemetry_view(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "runtime_best_s": m.get("runtime_best_s"),
        "runtime_mean_s": m.get("runtime_mean_s"),
        "tracemalloc_peak_bytes": m.get("tracemalloc_peak_bytes"),
        "rss_after_bytes": m.get("rss_after_bytes"),
        "disk_bytes": m.get("disk_bytes"),
        "input_size": m.get("input_size"),
        "worker_count": m.get("worker_count"),
    }


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
                "confidence": None,
                "measurement_quality": None,
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

    opt: List[Dict[str, Any]] = []
    if tm_ratio is not None and tm_ratio > 1.15:
        recommendations.append("candidate tracemalloc peak exceeds baseline; review live path allocation")
        opt.append(
            {
                "target": spec.name,
                "kind": "memory",
                "metric": "tracemalloc_peak_bytes",
                "ratio": tm_ratio,
                "supported_by": "measured_tracemalloc_ratio",
                "recommendation": _memory_hint(spec.name),
            }
        )
    if rt_ratio is not None and rt_ratio > 1.25:
        recommendations.append("candidate runtime exceeds baseline (advisory, host-dependent)")
        opt.append(
            {
                "target": spec.name,
                "kind": "runtime_advisory",
                "metric": "runtime_best_s",
                "ratio": rt_ratio,
                "supported_by": "measured_runtime_ratio",
                "recommendation": _runtime_hint(spec.name),
            }
        )
    if candidate.get("disk_bytes") is not None and (baseline.get("disk_bytes") is None or (
        disk_ratio is not None and disk_ratio > 1.15
    )):
        if spec.name == "bounded_cache_planning" and candidate.get("disk_bytes"):
            opt.append(
                {
                    "target": spec.name,
                    "kind": "disk",
                    "metric": "disk_bytes",
                    "ratio": disk_ratio,
                    "supported_by": "measured_disk_bytes",
                    "recommendation": (
                        "BoundedChunkCache.register_manifest_item rewrites manifest.json "
                        "on every item; a batched persist would cut planning I/O. Do not "
                        "change production from this report — re-measure after a dedicated patch."
                    ),
                }
            )

    confidence = _confidence(baseline, candidate, repetitions)
    if confidence["level"] == "low":
        recommendations.append("low measurement confidence; increase repetitions")

    return json_safe(
        {
            "target": spec.name,
            "path_family": spec.path_family,
            "status": status,
            "production_module": candidate.get("production_module") or baseline.get("production_module"),
            "production_available": candidate.get("production_available"),
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
            },
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
                ],
                "telemetry_fields": [
                    "runtime_best_s",
                    "runtime_mean_s",
                    "tracemalloc_peak_bytes",
                    "rss_after_bytes",
                    "disk_bytes",
                ],
                "missing_metrics_are_null": True,
            },
            "recommendations": recommendations,
            "optimization_candidates": opt,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
        }
    )


def _memory_hint(name: str) -> str:
    hints = {
        "bounded_cache_planning": (
            "Live cache planning retains the full manifest dict in memory; streaming "
            "eviction planning could lower the working set. Measure again after any patch."
        ),
        "artifact_manifest_scanning": (
            "extract_run keeps the full artifact list and parsed JSON metadata; a "
            "streaming checksum pass would lower peak if scans grow. Measure again after any patch."
        ),
        "duplicate_detection": (
            "Duplicate detection currently materializes path lists per digest; a "
            "seen/dup set would match the contract with a smaller working set."
        ),
        "evidence_graph_projection": (
            "recommended_merge_order builds adjacency sets for the full node list; "
            "filtering ineligible nodes first would shrink the graph."
        ),
        "release_evidence_evaluation": (
            "Materializing full release reports is more expensive than collecting "
            "decision enums; keep the bounded candidate path."
        ),
        "manifest_planning": (
            "build_manifest already hashes an explicit path list; avoid replacing it "
            "with a directory walk."
        ),
        "checkpoint_recovery_planning": (
            "Configuration hashing is already a compact canonical JSON pass; no "
            "memory change is justified without a larger measured ratio."
        ),
        "simulation_runner_overhead": (
            "process_runner child spawn dominates this target; keep max_workers=1 "
            "and sample_rss=False for planning-only children."
        ),
    }
    return hints.get(name, "Review the live path allocation after a dedicated measurement.")


def _runtime_hint(name: str) -> str:
    hints = {
        "bounded_cache_planning": (
            "Per-item atomic manifest writes dominate planning time. Batching "
            "register_manifest_item persistence is the highest-value candidate if "
            "this ratio stays above 1.25 on repeated hosts."
        ),
        "artifact_manifest_scanning": (
            "Pass previous_manifest so extract_run can reuse checksums when size "
            "and mtime_ns match. Callers that omit it pay a full rehash."
        ),
        "simulation_runner_overhead": (
            "Child-process isolation is the cost of honest RSS/timeout attribution. "
            "Do not inline production simulations into the parent to save spawn time."
        ),
        "manifest_planning": (
            "Hashing artifact bytes is the necessary correctness work; parallelism "
            "is not recommended (worker count must stay bounded at 1)."
        ),
    }
    return hints.get(
        name,
        "Runtime is advisory and host-dependent; do not change production on a single-host ratio.",
    )


def rank_bottlenecks(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank targets by measured candidate cost. Missing metrics are skipped, never zeroed."""
    rows: List[Dict[str, Any]] = []
    for rec in results:
        tel = (rec.get("telemetry") or {}).get("candidate") or {}
        runtime = tel.get("runtime_best_s")
        memory = tel.get("tracemalloc_peak_bytes")
        disk = tel.get("disk_bytes")
        score_parts = [v for v in (runtime, None if memory is None else memory / 1e9, None if disk is None else disk / 1e9) if v is not None]
        rows.append(
            {
                "target": rec.get("target"),
                "status": rec.get("status"),
                "runtime_best_s": runtime,
                "tracemalloc_peak_bytes": memory,
                "rss_after_bytes": tel.get("rss_after_bytes"),
                "disk_bytes": disk,
                "runtime_ratio_advisory": (rec.get("telemetry") or {}).get(
                    "runtime_ratio_candidate_over_baseline_advisory"
                ),
                "tracemalloc_ratio": (rec.get("telemetry") or {}).get(
                    "tracemalloc_peak_ratio_candidate_over_baseline"
                ),
                "score_proxy": max(score_parts) if score_parts else None,
            }
        )
    rows.sort(key=lambda r: (r["score_proxy"] is None, -(r["score_proxy"] or 0.0), r["target"] or ""))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def collect_optimization_candidates(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only recommendations backed by a measured ratio or disk footprint."""
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
    all_equivalent = all(matches) if matches and all(m is not None for m in matches) else None
    if matches and any(m is None for m in matches):
        known = [m for m in matches if m is not None]
        all_equivalent = all(known) if known else None
    budget_verdicts = [
        (r.get("deterministic") or {}).get("budget", {}) or {}
        for r in results
    ]
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
            "production_probe": probe_all(),
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
                "runtime and RSS are hardware-dependent (advisory); tracemalloc peak and "
                "disk usage are the comparable signals.",
                "Deterministic fields are reproducible across runs; telemetry fields vary.",
                "Missing metrics are null, never zero.",
                "Optimization candidates are emitted only when a measured ratio or disk "
                "footprint supports them. No production code is modified by this harness.",
            ],
        }
    )
