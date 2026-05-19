"""
Ontology schema (O1).

Layered claim/scope/promotion model for DS005620 and adjacent benchmarks.
All types are stdlib-only dataclasses with `to_dict` helpers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


class OntologyLayer:
    D_PHENOMENOLOGY = "D_PHENOMENOLOGY"
    M_MARKER = "M_MARKER"
    T_TOPOLOGY = "T_TOPOLOGY"
    C_SUBSTRATE = "C_SUBSTRATE"
    Q_THEORY = "Q_THEORY"
    O_ONTOLOGY_CANDIDATE = "O_ONTOLOGY_CANDIDATE"
    OMEGA_GOVERNANCE = "OMEGA_GOVERNANCE"


ONTOLOGY_LAYERS: list[str] = [
    OntologyLayer.D_PHENOMENOLOGY,
    OntologyLayer.M_MARKER,
    OntologyLayer.T_TOPOLOGY,
    OntologyLayer.C_SUBSTRATE,
    OntologyLayer.Q_THEORY,
    OntologyLayer.O_ONTOLOGY_CANDIDATE,
    OntologyLayer.OMEGA_GOVERNANCE,
]


class ClaimScope:
    ENGINEERING_RUNTIME = "engineering_runtime"
    MARKER_ASSOCIATION = "marker_association"
    TOPOLOGY_RESIDUAL = "topology_residual"
    MECHANISM_CANDIDATE = "mechanism_candidate"
    THEORY_CONSISTENCY = "theory_consistency"
    ONTOLOGY_CANDIDATE = "ontology_candidate"
    BLOCKED_OVERREACH = "blocked_overreach"
    REJECTED = "rejected"


CLAIM_SCOPES: list[str] = [
    ClaimScope.ENGINEERING_RUNTIME,
    ClaimScope.MARKER_ASSOCIATION,
    ClaimScope.TOPOLOGY_RESIDUAL,
    ClaimScope.MECHANISM_CANDIDATE,
    ClaimScope.THEORY_CONSISTENCY,
    ClaimScope.ONTOLOGY_CANDIDATE,
    ClaimScope.BLOCKED_OVERREACH,
    ClaimScope.REJECTED,
]


class PromotionState:
    DRAFT = "draft"
    ENGINEERING_VALIDATED = "engineering_validated"
    EMPIRICAL_CANDIDATE = "empirical_candidate"
    EMPIRICAL_SUPPORTED_LIMITED = "empirical_supported_limited"
    MECHANISM_CANDIDATE = "mechanism_candidate"
    THEORY_CONSISTENCY_ONLY = "theory_consistency_only"
    ONTOLOGY_QUARANTINED = "ontology_quarantined"
    BLOCKED_PENDING_REAL_EXECUTION = "blocked_pending_real_execution"
    BLOCKED_PENDING_CONTROLS = "blocked_pending_controls"
    BLOCKED_PENDING_REVIEW = "blocked_pending_review"
    BLOCKED_OVERREACH = "blocked_overreach"
    REJECTED = "rejected"


PROMOTION_STATES: list[str] = [
    PromotionState.DRAFT,
    PromotionState.ENGINEERING_VALIDATED,
    PromotionState.EMPIRICAL_CANDIDATE,
    PromotionState.EMPIRICAL_SUPPORTED_LIMITED,
    PromotionState.MECHANISM_CANDIDATE,
    PromotionState.THEORY_CONSISTENCY_ONLY,
    PromotionState.ONTOLOGY_QUARANTINED,
    PromotionState.BLOCKED_PENDING_REAL_EXECUTION,
    PromotionState.BLOCKED_PENDING_CONTROLS,
    PromotionState.BLOCKED_PENDING_REVIEW,
    PromotionState.BLOCKED_OVERREACH,
    PromotionState.REJECTED,
]


@dataclass
class OntologyNode:
    node_id: str
    label: str
    layer: str
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OntologyClaim:
    claim_id: str
    title: str
    layer: str
    scope: str
    statement: str
    allowed: bool
    promotion_state: str
    required_evidence: list[str] = field(default_factory=list)
    required_controls: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BridgeClaim:
    bridge_id: str
    source_layer: str
    target_layer: str
    allowed_claim: str
    forbidden_claims: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    required_controls: list[str] = field(default_factory=list)
    falsifiers: list[str] = field(default_factory=list)
    alternative_explanations: list[str] = field(default_factory=list)
    promotion_thresholds: dict = field(default_factory=dict)
    always_quarantined: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceRequirement:
    requirement_id: str
    description: str
    required_artifacts: list[str] = field(default_factory=list)
    required_controls: list[str] = field(default_factory=list)
    requires_real_execution: bool = False
    requires_human_review: bool = False
    requires_independent_dataset: bool = False
    max_scope_without_requirement: str = ClaimScope.ENGINEERING_RUNTIME

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Falsifier:
    falsifier_id: str
    description: str
    status: str = "not_evaluated"
    required_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlternativeExplanation:
    alternative_id: str
    description: str
    status: str = "not_evaluated"
    required_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OntologyEvaluationResult:
    dataset_id: str
    run_mode: str
    max_claim_scope: str
    promotion_state: str
    claims: list[OntologyClaim] = field(default_factory=list)
    bridge_statuses: list[dict] = field(default_factory=list)
    falsifier_statuses: list[Falsifier] = field(default_factory=list)
    alternative_explanations: list[AlternativeExplanation] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_claim: str = ""
    forbidden_claims: list[str] = field(default_factory=list)
    omega_invariants: dict = field(default_factory=dict)
    ontology_claim_status: str = PromotionState.ONTOLOGY_QUARANTINED
    generated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "run_mode": self.run_mode,
            "max_claim_scope": self.max_claim_scope,
            "promotion_state": self.promotion_state,
            "ontology_claim_status": self.ontology_claim_status,
            "claims": [c.to_dict() for c in self.claims],
            "bridge_statuses": self.bridge_statuses,
            "falsifier_statuses": [f.to_dict() for f in self.falsifier_statuses],
            "alternative_explanations": [a.to_dict() for a in self.alternative_explanations],
            "blockers": self.blockers,
            "warnings": self.warnings,
            "safe_claim": self.safe_claim,
            "forbidden_claims": self.forbidden_claims,
            "omega_invariants": self.omega_invariants,
            "generated_at": self.generated_at,
        }
