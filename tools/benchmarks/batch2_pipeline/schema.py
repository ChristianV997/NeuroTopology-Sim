"""Versioned schema for Batch-2 pipeline performance evidence.

Synthetic local fixtures only. Performance engineering evidence — never
scientific, clinical, ontology, or theory-of-everything claims.
"""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

SCHEMA_VERSION = "batch2_pipeline/v1"
EVIDENCE_CLASS = "performance_only"
PROVENANCE_LABEL = "local_synthetic_performance_only"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/benchmarks/batch2_pipeline/",
    "scripts/benchmark_batch2_pipeline.py",
    "tests/benchmarks/batch2_pipeline/",
    "docs/performance/batch2_pipeline_benchmarks.md",
)

PROTECTED_PATH_PREFIXES: Tuple[str, ...] = (
    "apps/awareness_studio/",
    "tools/data_access/",
    "tools/streaming/",
    "dataset_acquisition/",
    ".github/workflows/",
    "sim/",
    "core/",
    "tools/stream_pitnn_cohort_ds005620.py",
)

FORBIDDEN_PHRASES: Tuple[str, ...] = (
    "proves consciousness",
    "consciousness solved",
    "clinical treatment",
    "validated theory of everything",
    "toe validation",
    "qabs proves",
    "q/qabs/fdress proof",
    "final theory",
    "ontology promotion",
    "as scientific evidence",
    "constitutes scientific evidence",
    "empirical proof of consciousness",
)

REQUIRED_OUTPUT_FILES: Tuple[str, ...] = (
    "batch2_pipeline_report.json",
    "batch2_pipeline_summary.md",
    "generation_manifest.json",
    "target_inventory.json",
    "bottleneck_ranking.json",
    "optimization_candidates.json",
    "telemetry_environment.json",
    "checksum_ledger.json",
    "budget_verdicts.json",
    "counter_comparison.json",
    "measurement_limitations.json",
    "governance_check.json",
    "tooling_availability.json",
    "rag_pack/rag_pack.json",
    "rag_pack/chunks.md",
)


class TargetStatus(str, Enum):
    OK = "ok"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    MALFORMED_RECORD = "malformed_record"
    ERROR = "error"
    TIMEOUT = "timeout"
    CHILD_CRASH = "child_crash"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    BUDGET_OVERRUN = "budget_overrun"


TARGET_NAMES: FrozenSet[str] = frozenset(
    {
        "full_recording_reread",
        "preprocess_per_window",
        "checkpoint_fsync_overhead",
        "manifest_write_amplification",
        "window_cache_hits",
        "subject_loop_disk_staging",
        "worker_bound_enforcement",
    }
)

COUNTER_KEYS: Tuple[str, ...] = (
    "read_counts",
    "preprocess_calls",
    "cache_hits",
    "cache_misses",
    "manifest_writes",
    "fsync_calls",
    "worker_count",
)
