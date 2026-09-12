"""Versioned schema for pipeline-efficiency performance evidence.

Output is synthetic performance evidence only. It makes no scientific,
clinical, ontology, or theory-of-everything claims.
"""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

SCHEMA_VERSION = "pipeline_efficiency/v1"
EVIDENCE_CLASS = "performance_only"
PROVENANCE_LABEL = "local_synthetic_performance_only"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/benchmarking/pipeline_efficiency/",
    "scripts/benchmark_pipeline_efficiency.py",
    "tests/benchmarking/pipeline_efficiency/",
    "docs/performance/pipeline_efficiency.md",
)

PROTECTED_PATH_PREFIXES: Tuple[str, ...] = (
    "apps/awareness_studio/",
    "tools/data_access/chunk_cache/",
    "tools/streaming/",
    "dataset_acquisition/",
    ".github/workflows/",
    "sim/",
    "core/",
    "ops/research_cycle/",
    "tools/research_cycle_release/",
    "tools/benchmarking/research_cycle_benchmarks/",
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
)

REQUIRED_OUTPUT_FILES: Tuple[str, ...] = (
    "pipeline_efficiency_report.json",
    "pipeline_efficiency_summary.md",
    "generation_manifest.json",
    "target_inventory.json",
    "bottleneck_ranking.json",
    "optimization_candidates.json",
    "telemetry_environment.json",
    "checksum_ledger.json",
    "budget_verdicts.json",
    "production_probe.json",
    "measurement_limitations.json",
    "governance_check.json",
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
    PRODUCTION_UNAVAILABLE = "production_unavailable"


TARGET_NAMES: FrozenSet[str] = frozenset(
    {
        "manifest_planning",
        "bounded_cache_planning",
        "artifact_manifest_scanning",
        "duplicate_detection",
        "evidence_graph_projection",
        "release_evidence_evaluation",
        "checkpoint_recovery_planning",
        "simulation_runner_overhead",
    }
)
