"""Simulation Release Bridge package.

Additive adapter connecting validated simulation execution results to artifact lineage,
research-cycle ledger, evidence graph, and release-evidence review.
"""
from __future__ import annotations

from .contracts import (
    BUNDLE_SCHEMA_VERSION,
    DEFAULT_SCIENTIFIC_LIMITATIONS,
    DataModality,
    EvidenceClass,
    ExecutionOutcomeSpec,
    ExecutionOutcomeState,
    ReleasePromotionStatus,
    SCHEMA_VERSION,
    SCIENTIFIC_CLAIM_SCOPE_DEFAULT,
    SCIENTIFIC_VERDICT_DEFAULT,
    SimulationReleaseBundle,
    SimulationReleaseError,
    canonical_hash,
    dumps_finite_json,
    finite_value,
)
from .builder import (
    SimulationReleaseBuilder,
    compile_simulation_release_bundle,
    render_bundle_markdown,
)
from .validator import (
    CHAIN_STAGES,
    ChainValidationResult,
    check_canonical_runner_presence,
    check_fabricated_provenance,
    check_manifest_completeness,
    check_non_finite_metrics,
    check_output_root_escapes,
    check_temporary_only_artifacts,
    validate_stages,
)

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "CHAIN_STAGES",
    "ChainValidationResult",
    "DEFAULT_SCIENTIFIC_LIMITATIONS",
    "DataModality",
    "EvidenceClass",
    "ExecutionOutcomeSpec",
    "ExecutionOutcomeState",
    "ReleasePromotionStatus",
    "SCHEMA_VERSION",
    "SCIENTIFIC_CLAIM_SCOPE_DEFAULT",
    "SCIENTIFIC_VERDICT_DEFAULT",
    "SimulationReleaseBundle",
    "SimulationReleaseBuilder",
    "SimulationReleaseError",
    "canonical_hash",
    "check_canonical_runner_presence",
    "check_fabricated_provenance",
    "check_manifest_completeness",
    "check_non_finite_metrics",
    "check_output_root_escapes",
    "check_temporary_only_artifacts",
    "compile_simulation_release_bundle",
    "dumps_finite_json",
    "finite_value",
    "render_bundle_markdown",
    "validate_stages",
]
