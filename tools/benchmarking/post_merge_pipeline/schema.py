"""Versioned schema for post-merge pipeline performance evidence.

Output is synthetic performance evidence only. It makes no scientific,
clinical, ontology, or theory-of-everything claims.
"""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

SCHEMA_VERSION = "post_merge_pipeline/v1"
EVIDENCE_CLASS = "performance_only"
PROVENANCE_LABEL = "local_synthetic_performance_only"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/benchmarking/post_merge_pipeline/",
    "scripts/benchmark_post_merge_pipeline.py",
    "tests/benchmarking/post_merge_pipeline/",
    "docs/performance/post_merge_pipeline.md",
)

PROTECTED_PATH_PREFIXES: Tuple[str, ...] = (
    "apps/awareness_studio/",
    "tools/data_access/chunk_cache/",
    "tools/streaming/base_runner.py",
    "data/bids_ingest.py",
    "dataset_acquisition/",
    ".github/workflows/",
    "sim/",
    "core/",
    "ops/research_cycle/",
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
    "post_merge_pipeline_report.json",
    "post_merge_pipeline_summary.md",
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
    "streaming_baseline_comparison.json",
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
        "metadata_planning",
        "bounded_cache_operations",
        "cache_eviction",
        "manifest_recovery",
        "artifact_scanning",
        "literature_evidence_validation",
        "research_cycle_smoke_execution",
        "release_evidence_evaluation",
    }
)
