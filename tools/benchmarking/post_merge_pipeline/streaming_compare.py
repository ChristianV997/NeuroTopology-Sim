"""Compare current-main measurements to the recorded streaming ingest baseline.

Compatible probes only. Missing values stay null. performance_only / synthetic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import EVIDENCE_CLASS

REPO_ROOT = Path(__file__).resolve().parents[3]
RECORDED_BASELINE = (
    REPO_ROOT / "tests" / "performance" / "streaming_optimization" / "recorded_baseline.json"
)


def load_recorded_streaming_baseline() -> Optional[Dict[str, Any]]:
    if not RECORDED_BASELINE.is_file():
        return None
    return json.loads(RECORDED_BASELINE.read_text(encoding="utf-8"))


def _ratio(current: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if current is None or baseline is None or baseline <= 0:
        return None
    value = current / baseline
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def compare_streaming_baseline(report: Dict[str, Any]) -> Dict[str, Any]:
    """Attach compatible comparisons. Does not invent metrics."""
    recorded = load_recorded_streaming_baseline()
    by_target = {row.get("target"): row for row in report.get("results") or []}
    manifest = by_target.get("manifest_recovery") or {}
    cand = ((manifest.get("telemetry") or {}).get("candidate") or {})
    current_runtime = cand.get("runtime_best_s")
    current_tm = cand.get("tracemalloc_peak_bytes")

    pre = (recorded or {}).get("save_manifest") or {}
    loop = (recorded or {}).get("manifest_loop") or {}
    pre_write_s = pre.get("elapsed_s")
    pre_loop_s = loop.get("first_pass_s")
    pre_tm = loop.get("tracemalloc_peak_bytes")

    notes = [
        "Compatible comparison is streaming manifest checkpoint cost vs current "
        "manifest_recovery (save_manifest + corrupt-dest recovery on this host).",
        "Pre-change recorded_baseline.json was taken on unmodified 55edf5c before "
        "fsync/atomic recovery. Current main includes PR #329 streaming optimizations.",
        "BIDS window preprocess timings are not re-run here (would require MNE and "
        "is not an owned measurement of this harness).",
        "Runtime ratios are advisory and host-dependent. Missing metrics are null.",
    ]
    probes = {
        "recorded_save_manifest_200_writes_s": pre_write_s,
        "recorded_manifest_loop_80_items_s": pre_loop_s,
        "recorded_manifest_loop_tracemalloc_peak_bytes": pre_tm,
        "current_manifest_recovery_runtime_best_s": current_runtime,
        "current_manifest_recovery_tracemalloc_peak_bytes": current_tm,
        "runtime_ratio_current_recovery_over_recorded_200_writes": _ratio(current_runtime, pre_write_s),
        "tracemalloc_ratio_current_recovery_over_recorded_loop": _ratio(current_tm, pre_tm),
    }
    return {
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": True,
        "recorded_baseline_path": str(RECORDED_BASELINE) if recorded is not None else None,
        "recorded_present": recorded is not None,
        "recorded_phase": (recorded or {}).get("phase"),
        "recorded_base_commit": (recorded or {}).get("base_commit"),
        "probes": probes,
        "notes": notes,
        "compatible_targets": ["manifest_recovery"],
        "incompatible_recorded_probes": [
            "bids.preprocess_read_s",
            "preprocess_read_reuse",
            "list_s3_task_labels (would require AWS)",
        ],
    }
