"""Versioned schema for data-migration effectiveness performance evidence."""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

SCHEMA_VERSION = "data_migration_effectiveness/v1"
EVIDENCE_CLASS = "performance_only"
PROVENANCE_LABEL = "local_synthetic_performance_only"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/benchmarking/data_migration_effectiveness/",
    "scripts/benchmark_data_migration_effectiveness.py",
    "tests/benchmarking/data_migration_effectiveness/",
    "docs/performance/data_migration_effectiveness.md",
)

PROTECTED_PATH_PREFIXES: Tuple[str, ...] = (
    "apps/awareness_studio/",
    "tools/data_access/chunk_cache/",
    "tools/data_access/policy_enforcement/",
    "tools/streaming/",
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
    "causal evidence",
    "formal bayes",
    "toe validation",
    "final theory",
    "ontology promotion",
)

REQUIRED_OUTPUT_FILES: Tuple[str, ...] = (
    "data_migration_effectiveness.json",
    "data_migration_effectiveness.md",
    "generation_manifest.json",
    "target_inventory.json",
    "validation.json",
    "obsidian/Data_Migration_Effectiveness_Index.md",
    "command_center/status.json",
    "command_center/checksum_gate.json",
    "command_center/optimization_queue.json",
    "rag/chunks.md",
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
    REJECTED = "rejected"
    PRODUCTION_UNAVAILABLE = "production_unavailable"


TARGET_NAMES: FrozenSet[str] = frozenset(
    {
        "bounded_vs_rejected_full_object",
        "planning_latency",
        "cache_occupancy_and_eviction",
        "retry_overhead",
        "manifest_recovery",
        "streaming_vs_full_materialization",
        "timeout_case",
        "corruption_case",
        "partial_transfer_case",
        "disk_budget_case",
    }
)
