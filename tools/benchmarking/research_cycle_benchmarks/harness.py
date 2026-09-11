"""Benchmark harness: run targets, verify equivalence, compare budgets, report.

Produces a versioned, finite report. Deterministic fields (checksums, feature
counts, budget verdicts, status) are stable across runs; telemetry fields
(runtimes, tracemalloc peak, RSS) are explicitly separated because they vary.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from .budgets import ResourceBudgets, compare_budget
from .telemetry import json_safe, measure
from .workloads import TARGETS, TargetSpec

SCHEMA_VERSION = "research_cycle_benchmarks/v1"

# Status values (deterministic classification of a target run).
STATUS_OK = "ok"
STATUS_CHECKSUM_MISMATCH = "checksum_mismatch"
STATUS_MALFORMED_RECORD = "malformed_record"
STATUS_ERROR = "error"


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


def run_target(spec: TargetSpec, budgets: ResourceBudgets, *,
               seed: int = 0, size: Optional[int] = None, repetitions: int = 3) -> Dict[str, Any]:
    """Run one target's baseline + candidate and return a finite record."""
    size = spec.default_size if size is None else size
    recommendations: List[str] = []
    try:
        fixture = spec.make_fixture(seed, size)
        baseline = measure(lambda: spec.baseline(fixture), repetitions=repetitions)
        candidate = measure(lambda: spec.candidate(fixture), repetitions=repetitions)
    except Exception as exc:  # never let one target crash the campaign
        return json_safe({
            "target": spec.name, "status": STATUS_ERROR, "error": str(exc),
            "deterministic": {"checksum_baseline": None, "checksum_candidate": None,
                              "checksum_match": None, "feature_count": None,
                              "budget": None},
            "telemetry": None, "confidence": None, "measurement_quality": None,
            "recommendations": ["target raised an exception; investigate fixture/workload"],
            "evidence_class": "performance_only", "synthetic": True,
        })

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
        recommendations.append(f"candidate exceeds budget ({', '.join(over)}); "
                               "reduce size or raise the budget")

    tm_ratio = _ratio(candidate.get("tracemalloc_peak_bytes"),
                       baseline.get("tracemalloc_peak_bytes"))
    rt_ratio = _ratio(candidate.get("runtime_best_s"), baseline.get("runtime_best_s"))
    if tm_ratio is not None and tm_ratio > 1.0:
        recommendations.append("candidate tracemalloc peak exceeds baseline; review bounded path")

    confidence = _confidence(baseline, candidate, repetitions)
    if confidence["level"] == "low":
        recommendations.append("low measurement confidence; increase repetitions")

    def _telemetry_view(m: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "runtime_best_s": m.get("runtime_best_s"),
            "runtime_mean_s": m.get("runtime_mean_s"),
            "tracemalloc_peak_bytes": m.get("tracemalloc_peak_bytes"),
            "rss_after_bytes": m.get("rss_after_bytes"),
            "disk_bytes": m.get("disk_bytes"),
        }

    return json_safe({
        "target": spec.name,
        "status": status,
        "deterministic": {
            "checksum_baseline": baseline.get("checksum"),
            "checksum_candidate": candidate.get("checksum"),
            "checksum_match": checksum_match,
            "feature_count": candidate.get("feature_count"),
            "budget": budget,
        },
        "telemetry": {
            "baseline": _telemetry_view(baseline),
            "candidate": _telemetry_view(candidate),
            "tracemalloc_peak_ratio_candidate_over_baseline": tm_ratio,
            "runtime_ratio_candidate_over_baseline_advisory": rt_ratio,
        },
        "confidence": confidence,
        "measurement_quality": {
            "deterministic_fields": ["checksum_baseline", "checksum_candidate",
                                     "checksum_match", "feature_count", "budget", "status"],
            "telemetry_fields": ["runtime_best_s", "runtime_mean_s",
                                 "tracemalloc_peak_bytes", "rss_after_bytes"],
        },
        "recommendations": recommendations,
        "evidence_class": "performance_only",
        "synthetic": True,
    })


def run_all(budgets: Optional[ResourceBudgets] = None, *, seed: int = 0,
            size: Optional[int] = None, repetitions: int = 3,
            targets: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run all (or selected) targets sequentially (bounded, no concurrency)."""
    budgets = budgets or ResourceBudgets()
    names = sorted(TARGETS.keys()) if targets is None else [t for t in targets if t in TARGETS]
    results = [run_target(TARGETS[name], budgets, seed=seed, size=size, repetitions=repetitions)
               for name in names]

    summary: Dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    all_equivalent = all(r["deterministic"]["checksum_match"] for r in results) if results else None
    budget_verdicts = [r["deterministic"]["budget"]["within_budget"] for r in results]
    evaluated = [v for v in budget_verdicts if v is not None]
    all_within_budget = all(evaluated) if evaluated else None

    return json_safe({
        "schema": SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "performance_only",
        "synthetic": True,
        "config": {"seed": seed, "size": size, "repetitions": repetitions,
                   "targets": names, "max_workers": 1},
        "budgets": budgets.to_dict(),
        "telemetry_environment": {"platform": sys.platform,
                                  "python_version": sys.version.split()[0]},
        "num_targets": len(results),
        "summary": summary,
        "all_equivalent": all_equivalent,
        "all_within_budget": all_within_budget,
        "results": results,
        "notes": [
            "Synthetic performance evidence only; no scientific claims, no real data, "
            "no simulations, no external APIs.",
            "runtime and RSS are hardware-dependent (advisory); tracemalloc peak and "
            "disk usage are the comparable signals.",
            "Deterministic fields are reproducible across runs; telemetry fields vary.",
        ],
    })
