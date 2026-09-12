"""Compare current-main with migration PR worktrees via isolated children."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.pipeline_efficiency.telemetry import execute_child, json_safe
from tools.benchmarking.migration_wave.probes import run_measured
from tools.benchmarking.migration_wave.schema import (
    EVIDENCE_CLASS,
    OPT_DISK_ABS_BYTES,
    OPT_DISK_RATIO,
    OPT_RT_ABS_S,
    OPT_RT_RATIO,
    OPT_TM_ABS_BYTES,
    OPT_TM_RATIO,
    SCHEMA_VERSION,
    TARGET_NAMES,
    TargetStatus,
)
from tools.benchmarking.migration_wave.variants import VARIANT_SPECS, inventory_variants, resolve_variant_root


def _ratio(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    value = candidate / baseline
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _hints(target: str, kind: str) -> str:
    mapping = {
        ("planning_latency", "runtime"): "Native planning APIs differ; re-measure the same surface before patching cache.plan I/O.",
        ("bounded_transfer_planning", "runtime"): "Per-item manifest registration dominates multi-item plans; batch persist is a later dedicated PR.",
        ("cache_occupancy", "memory"): "Live occupancy retains the full manifest; a streaming occupancy census would lower peak if catalogs grow.",
        ("eviction_latency", "runtime"): "evict() rewrites manifest.json; a dirty-set persist is the measured I/O candidate.",
        ("retry_overhead", "runtime"): "Retry backoff is synthetic; do not reduce max_retries from this host timing.",
        ("manifest_recovery", "runtime"): "fsync/atomic recovery is durability; do not revert it from a microbenchmark.",
        ("checksum_verification", "runtime"): "Fail-closed checksum rejection is correctness work, not a speedup target.",
    }
    return mapping.get((target, kind), "Re-measure on a dedicated patch; this harness does not modify production.")


def run_in_process(target: str, *, seed: int, size: int, repetitions: int) -> Dict[str, Any]:
    return run_measured(target, seed=seed, size=size, repetitions=repetitions)


def run_variant_child(
    *,
    harness_root: Path,
    variant: str,
    variant_root: Path,
    target: str,
    seed: int,
    size: int,
    repetitions: int,
    timeout_s: float,
) -> Dict[str, Any]:
    script = harness_root / "scripts" / "benchmark_migration_wave.py"
    argv = [
        sys.executable,
        str(script),
        "child",
        "--variant-root",
        str(variant_root),
        "--target",
        target,
        "--seed",
        str(seed),
        "--size",
        str(size),
        "--repetitions",
        str(repetitions),
    ]
    child = execute_child(argv, timeout_s=timeout_s)
    if child.timed_out:
        return {
            "ok": False,
            "status": TargetStatus.TIMEOUT.value,
            "checksum": None,
            "error": "timeout",
            "child": child.to_dict(),
        }
    if child.exit_code != 0:
        return {
            "ok": False,
            "status": TargetStatus.CHILD_CRASH.value,
            "checksum": None,
            "error": child.stderr[-500:] if child.stderr else f"exit={child.exit_code}",
            "child": child.to_dict(),
        }
    try:
        payload = json.loads(child.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return {
            "ok": False,
            "status": TargetStatus.MALFORMED_RECORD.value,
            "checksum": None,
            "error": f"malformed child json: {exc}",
            "child": child.to_dict(),
        }
    payload.setdefault("status", payload.get("payload", {}).get("status") if isinstance(payload.get("payload"), dict) else None)
    return payload


def _row_from_measured(
    variant: str,
    target: str,
    measured: Dict[str, Any],
    budgets: ResourceBudgets,
) -> Dict[str, Any]:
    payload = measured.get("payload") if isinstance(measured.get("payload"), dict) else measured
    status = measured.get("status") or payload.get("status") or TargetStatus.OK.value
    if measured.get("ok") is False and measured.get("reason") == "malformed_result":
        status = TargetStatus.MALFORMED_RECORD.value
    if payload.get("production_available") is False:
        status = TargetStatus.PRODUCTION_UNAVAILABLE.value
    budget = compare_budget(measured, budgets)
    if budget["within_budget"] is False and status == TargetStatus.OK.value:
        status = TargetStatus.BUDGET_OVERRUN.value
    return json_safe(
        {
            "variant": variant,
            "target": target,
            "status": status,
            "deterministic": {
                "checksum": measured.get("checksum"),
                "feature_count": measured.get("feature_count") or payload.get("feature_count"),
                "surface": measured.get("surface") or payload.get("surface"),
                "correctness": payload.get("correctness"),
                "duplicate_work": measured.get("duplicate_work") if measured.get("duplicate_work") is not None else payload.get("duplicate_work"),
                "partial_state": measured.get("partial_state") if measured.get("partial_state") is not None else payload.get("partial_state"),
                "budget": budget,
                "input_size": measured.get("input_size") or payload.get("input_size"),
            },
            "telemetry": {
                "runtime_best_s": measured.get("runtime_best_s"),
                "runtime_mean_s": measured.get("runtime_mean_s"),
                "tracemalloc_peak_bytes": measured.get("tracemalloc_peak_bytes"),
                "rss_after_bytes": measured.get("rss_after_bytes"),
                "disk_bytes": measured.get("disk_bytes"),
                "planning_latency_s": measured.get("planning_latency_s") if measured.get("planning_latency_s") is not None else payload.get("planning_latency_s"),
                "eviction_latency_s": measured.get("eviction_latency_s") if measured.get("eviction_latency_s") is not None else payload.get("eviction_latency_s"),
                "retry_attempts": measured.get("retry_attempts") if measured.get("retry_attempts") is not None else payload.get("retry_attempts"),
                "cache_occupancy_bytes": measured.get("cache_occupancy_bytes") if measured.get("cache_occupancy_bytes") is not None else payload.get("cache_occupancy_bytes"),
                "worker_count": measured.get("worker_count") or 1,
            },
            "production_module": measured.get("production_module") or payload.get("production_module"),
            "production_available": payload.get("production_available"),
            "error": measured.get("error") or payload.get("notes"),
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
        }
    )


def _optimization_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_target: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_target.setdefault(row["target"], {})[row["variant"]] = row
    out: List[Dict[str, Any]] = []
    for target, variants in sorted(by_target.items()):
        baseline = variants.get("current_main")
        if not baseline or baseline.get("status") not in {TargetStatus.OK.value, "duplicate_work"}:
            continue
        base_tel = baseline.get("telemetry") or {}
        for name, row in sorted(variants.items()):
            if name == "current_main" or row.get("status") not in {TargetStatus.OK.value, "duplicate_work"}:
                continue
            tel = row.get("telemetry") or {}
            tm_ratio = _ratio(tel.get("tracemalloc_peak_bytes"), base_tel.get("tracemalloc_peak_bytes"))
            rt_ratio = _ratio(tel.get("runtime_best_s"), base_tel.get("runtime_best_s"))
            disk_ratio = _ratio(tel.get("disk_bytes"), base_tel.get("disk_bytes"))
            tm_abs = tel.get("tracemalloc_peak_bytes")
            rt_abs = tel.get("runtime_best_s")
            disk_abs = tel.get("disk_bytes")
            if tm_ratio is not None and tm_ratio > OPT_TM_RATIO and tm_abs is not None and tm_abs >= OPT_TM_ABS_BYTES:
                out.append(
                    {
                        "variant": name,
                        "target": target,
                        "kind": "memory",
                        "metric": "tracemalloc_peak_bytes",
                        "ratio": tm_ratio,
                        "supported_by": "measured_tracemalloc_ratio_vs_current_main",
                        "recommendation": _hints(target, "memory"),
                    }
                )
            if rt_ratio is not None and rt_ratio > OPT_RT_RATIO and rt_abs is not None and rt_abs >= OPT_RT_ABS_S:
                out.append(
                    {
                        "variant": name,
                        "target": target,
                        "kind": "runtime_advisory",
                        "metric": "runtime_best_s",
                        "ratio": rt_ratio,
                        "supported_by": "measured_runtime_ratio_vs_current_main",
                        "recommendation": _hints(target, "runtime"),
                    }
                )
            if disk_ratio is not None and disk_ratio > OPT_DISK_RATIO and disk_abs is not None and disk_abs >= OPT_DISK_ABS_BYTES:
                out.append(
                    {
                        "variant": name,
                        "target": target,
                        "kind": "disk",
                        "metric": "disk_bytes",
                        "ratio": disk_ratio,
                        "supported_by": "measured_disk_ratio_vs_current_main",
                        "recommendation": _hints(target, "runtime"),
                    }
                )
    return out


def _regressions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_target: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_target.setdefault(row["target"], {})[row["variant"]] = row
    found: List[Dict[str, Any]] = []
    for target, variants in sorted(by_target.items()):
        baseline = variants.get("current_main")
        if not baseline:
            continue
        base_ck = (baseline.get("deterministic") or {}).get("checksum")
        base_surface = (baseline.get("deterministic") or {}).get("surface")
        base_tel = baseline.get("telemetry") or {}
        for name, row in sorted(variants.items()):
            if name == "current_main":
                continue
            det = row.get("deterministic") or {}
            if (
                row.get("status") == TargetStatus.OK.value
                and baseline.get("status") == TargetStatus.OK.value
                and det.get("surface") == base_surface
                and base_ck
                and det.get("checksum")
                and det.get("checksum") != base_ck
            ):
                found.append(
                    {
                        "variant": name,
                        "target": target,
                        "kind": "checksum",
                        "detail": "same surface, different correctness checksum vs current_main",
                    }
                )
            tel = row.get("telemetry") or {}
            rt_ratio = _ratio(tel.get("runtime_best_s"), base_tel.get("runtime_best_s"))
            rt_abs = tel.get("runtime_best_s")
            if (
                rt_ratio is not None
                and rt_ratio > OPT_RT_RATIO
                and rt_abs is not None
                and rt_abs >= OPT_RT_ABS_S
                and det.get("surface") == base_surface
            ):
                found.append(
                    {
                        "variant": name,
                        "target": target,
                        "kind": "runtime_advisory",
                        "ratio": rt_ratio,
                        "detail": "same-surface runtime slower than current_main on this host",
                    }
                )
    return found


def _comparison_matrix(rows: List[Dict[str, Any]], variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix: Dict[str, Dict[str, Any]] = {}
    for target in sorted(TARGET_NAMES):
        matrix[target] = {}
        for spec in variants:
            name = spec["variant"]
            hit = next((row for row in rows if row["target"] == target and row["variant"] == name), None)
            if hit is None:
                matrix[target][name] = {"runnable": False, "status": "missing"}
            else:
                tel = hit.get("telemetry") or {}
                det = hit.get("deterministic") or {}
                matrix[target][name] = {
                    "runnable": hit.get("status") not in {TargetStatus.PRODUCTION_UNAVAILABLE.value, TargetStatus.ERROR.value},
                    "status": hit.get("status"),
                    "surface": det.get("surface"),
                    "checksum": det.get("checksum"),
                    "runtime_best_s": tel.get("runtime_best_s"),
                    "tracemalloc_peak_bytes": tel.get("tracemalloc_peak_bytes"),
                    "rss_after_bytes": tel.get("rss_after_bytes"),
                    "disk_bytes": tel.get("disk_bytes"),
                    "planning_latency_s": tel.get("planning_latency_s"),
                    "eviction_latency_s": tel.get("eviction_latency_s"),
                    "cache_occupancy_bytes": tel.get("cache_occupancy_bytes"),
                    "retry_attempts": tel.get("retry_attempts"),
                    "duplicate_work": det.get("duplicate_work"),
                    "partial_state": det.get("partial_state"),
                }
    return {
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": True,
        "cells": matrix,
        "variants": [item["variant"] for item in variants],
        "targets": sorted(TARGET_NAMES),
    }


def run_all(
    budgets: Optional[ResourceBudgets] = None,
    *,
    seed: int = 0,
    size: int = 64,
    repetitions: int = 1,
    isolated: bool = False,
    per_target_timeout_s: float = 45.0,
    harness_root: Optional[str | Path] = None,
    variant_roots: Optional[Dict[str, str]] = None,
    variants: Optional[List[str]] = None,
    targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    budgets = budgets or ResourceBudgets()
    root = Path(harness_root or Path(__file__).resolve().parents[3])
    variant_names = list(variants) if variants else list(VARIANT_SPECS.keys())
    target_names = list(targets) if targets else sorted(TARGET_NAMES)
    catalog = inventory_variants(root, overrides=variant_roots)
    catalog = [item for item in catalog if item["variant"] in variant_names]
    rows: List[Dict[str, Any]] = []
    for spec in catalog:
        name = spec["variant"]
        if not spec["available"]:
            for target in target_names:
                rows.append(
                    json_safe(
                        {
                            "variant": name,
                            "target": target,
                            "status": TargetStatus.PRODUCTION_UNAVAILABLE.value,
                            "deterministic": {
                                "checksum": None,
                                "feature_count": None,
                                "surface": None,
                                "correctness": None,
                                "duplicate_work": None,
                                "partial_state": None,
                                "budget": None,
                                "input_size": None,
                            },
                            "telemetry": None,
                            "production_module": None,
                            "production_available": False,
                            "error": "variant_root_missing",
                            "evidence_class": EVIDENCE_CLASS,
                            "synthetic": True,
                        }
                    )
                )
            continue
        vroot = Path(spec["root"])
        for target in target_names:
            if isolated or name != "current_main":
                measured = run_variant_child(
                    harness_root=root,
                    variant=name,
                    variant_root=vroot,
                    target=target,
                    seed=seed,
                    size=size,
                    repetitions=repetitions,
                    timeout_s=per_target_timeout_s,
                )
            else:
                measured = run_in_process(target, seed=seed, size=size, repetitions=repetitions)
            rows.append(_row_from_measured(name, target, measured, budgets))

    summary: Dict[str, int] = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    ranking = []
    for row in rows:
        tel = row.get("telemetry") or {}
        ranking.append(
            {
                "variant": row["variant"],
                "target": row["target"],
                "status": row["status"],
                "runtime_best_s": tel.get("runtime_best_s"),
                "tracemalloc_peak_bytes": tel.get("tracemalloc_peak_bytes"),
                "disk_bytes": tel.get("disk_bytes"),
                "score_proxy": tel.get("runtime_best_s"),
            }
        )
    ranking.sort(key=lambda item: (item["score_proxy"] is None, -(item["score_proxy"] or 0)))
    for index, item in enumerate(ranking, start=1):
        item["rank"] = index

    notes = [
        "Synthetic performance evidence only; no scientific claims, no real data, no OpenNeuro/AWS/DANDI access.",
        "runtime and RSS are hardware-dependent (advisory); tracemalloc peak and disk usage are the comparable signals.",
        "Missing metrics are null, never zero.",
        "Planning surfaces differ by PR (approved adapter, fetch.plan, WindowRequest, BoundedS3). Same-surface checksums are the only cross-variant correctness comparison.",
        "Optimization candidates are emitted only when a measured ratio vs current_main exceeds floors. No production code is modified.",
        "PRs #344 and #345 are closed/unmerged; current_main already contains related bounded OpenNeuro and DANDI/NWB work.",
    ]
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
                "targets": target_names,
                "variants": variant_names,
                "max_workers": 1,
                "isolated": isolated,
            },
            "budgets": budgets.to_dict(),
            "variant_inventory": catalog,
            "results": rows,
            "num_results": len(rows),
            "summary": summary,
            "comparison_matrix": _comparison_matrix(rows, catalog),
            "regressions": _regressions(rows),
            "optimization_candidates": _optimization_candidates(rows),
            "bottleneck_ranking": ranking,
            "notes": notes,
            "network_used": False,
            "remote_data_accessed": False,
        }
    )
