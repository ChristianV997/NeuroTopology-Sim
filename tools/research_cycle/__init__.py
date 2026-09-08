"""Versioned Hypothesis-and-Experiment Registry for Automated Scientific Inquiry.

Provides:
- Versioned Records (HypothesisRecord.v1, ExperimentPlan.v1, PredictionRecord.v1, EvidenceUpdate.v1, TheoryRevision.v1)
- Deterministic Promotion & Retention Gates (Rules A through G)
- Domain-specific Experiment Planners
- State Machine with Audit Trail and Human Oversight Gates
- Cryptographic SHA-256 and Strict RFC-8259 JSON Serialization
"""
from __future__ import annotations

from .experiment_planners import (
    DiscernmentNonjudgmentPlanner,
    HigherOrderSpectraPlanner,
    HypergraphTransitionPlanner,
    NullSurrogatePlanner,
    PairwiseVsTriadicFCPlanner,
    RespirationAutonomicPlanner,
)
from .gates import (
    InvalidStatusTransitionError,
    PromotionBlockedError,
    apply_evidence_to_hypothesis,
    check_promotion_gates,
    validate_status_transition,
)
from .registry import ResearchCycleRegistry
from .schema import (
    EpistemicLabel,
    EvidenceDataType,
    EvidenceUpdate,
    ExperimentDomain,
    ExperimentPlan,
    HumanReviewGate,
    HypothesisRecord,
    HypothesisStatus,
    PredictionRecord,
    TheoryRevision,
)
from .serialization import (
    compute_record_checksum,
    load_registry_json,
    save_registry_json,
    verify_record_checksum,
)

__all__ = [
    "DiscernmentNonjudgmentPlanner",
    "EpistemicLabel",
    "EvidenceDataType",
    "EvidenceUpdate",
    "ExperimentDomain",
    "ExperimentPlan",
    "HigherOrderSpectraPlanner",
    "HumanReviewGate",
    "HypergraphTransitionPlanner",
    "HypothesisRecord",
    "HypothesisStatus",
    "InvalidStatusTransitionError",
    "NullSurrogatePlanner",
    "PairwiseVsTriadicFCPlanner",
    "PredictionRecord",
    "PromotionBlockedError",
    "ResearchCycleRegistry",
    "RespirationAutonomicPlanner",
    "TheoryRevision",
    "apply_evidence_to_hypothesis",
    "check_promotion_gates",
    "compute_record_checksum",
    "load_registry_json",
    "save_registry_json",
    "validate_status_transition",
    "verify_record_checksum",
]
