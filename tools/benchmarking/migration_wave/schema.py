"""Versioned schema for migration-wave performance evidence.

Output is synthetic performance evidence only. It makes no scientific,
clinical, ontology, or theory-of-everything claims.
"""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

SCHEMA_VERSION = "migration_wave/v1"
EVIDENCE_CLASS = "performance_only"
PROVENANCE_LABEL = "local_synthetic_performance_only"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/benchmarking/migration_wave/",
    "scripts/benchmark_migration_wave.py",
    "tests/benchmarking/migration_wave/",
    "docs/performance/migration_wave.md",
)

PROTECTED_PATH_PREFIXES: Tuple[str, ...] = (
    "apps/awareness_studio/",
    "tools/data_access/chunk_cache/",
    "tools/data_access/approved_adapter/",
    "tools/streaming/base_runner.py",
    "data/bids_ingest.py",
    "data/dandi_nwb_ingest.py",
    "tools/fetch_ds000245.py",
    "validation/s3_fetchers.py",
    "dataset_acquisition/",
    ".github/workflows/",
    "sim/",
    "core/",
)

FORBIDDEN_PHRASES: Tuple[str, ...] = (
    "proves consciousness",
    "consciousness solved",
    "clinical treatment",
    "validated theory of everything",
    "proves scientific improvement",
    "toe validation",
    "qabs proves",
    "q/qabs/fdress proof",
    "final theory",
    "ontology promotion",
)

REQUIRED_OUTPUT_FILES: Tuple[str, ...] = (
    "migration_wave_report.json",
    "migration_wave_summary.md",
    "generation_manifest.json",
    "target_inventory.json",
    "variant_inventory.json",
    "comparison_matrix.json",
    "bottleneck_ranking.json",
    "optimization_candidates.json",
    "checksum_ledger.json",
    "budget_verdicts.json",
    "capability_probe.json",
    "measurement_limitations.json",
    "governance_check.json",
    "telemetry_environment.json",
    "rag_pack/rag_pack.json",
    "rag_pack/chunks.md",
)

# Absolute floors so tiny synthetic fixtures do not emit production patch hints.
OPT_TM_RATIO = 1.15
OPT_TM_ABS_BYTES = 64_000
OPT_RT_RATIO = 1.25
OPT_RT_ABS_S = 0.05
OPT_DISK_RATIO = 1.25
OPT_DISK_ABS_BYTES = 4_096


class TargetStatus(str, Enum):
    OK = "ok"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    MALFORMED_RECORD = "malformed_record"
    ERROR = "error"
    TIMEOUT = "timeout"
    CHILD_CRASH = "child_crash"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    BUDGET_OVERRUN = "budget_overrun"
    PARTIAL_STATE = "partial_state"
    DUPLICATE_WORK = "duplicate_work"
    PRODUCTION_UNAVAILABLE = "production_unavailable"


VARIANT_NAMES: FrozenSet[str] = frozenset(
    {
        "current_main",
        "pr_331",
        "pr_344",
        "pr_345",
        "pr_346",
    }
)

TARGET_NAMES: FrozenSet[str] = frozenset(
    {
        "planning_latency",
        "bounded_transfer_planning",
        "cache_occupancy",
        "eviction_latency",
        "retry_overhead",
        "manifest_recovery",
        "checksum_verification",
    }
)
