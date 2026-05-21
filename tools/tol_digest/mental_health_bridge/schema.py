from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

CLAIM_SCOPES = {
    "book_safe_model", "research_hypothesis", "wellness_support",
    "clinician_decision_support_candidate", "clinical_claim_blocked",
    "medical_device_claim_blocked",
}
EVIDENCE_STATES = {
    "conceptual_mapping", "artifact_derived", "literature_informed",
    "requires_validation", "validated_elsewhere_not_in_repo", "not_validated",
}
ALLOWED_USES = {
    "research", "education", "wellness_non_diagnostic",
    "clinician_support_after_validation", "not_for_public_claim",
}

@dataclass(frozen=True)
class MentalFlexibilityConstruct:
    construct_id: str
    name: str
    tol_mapping: list[str]
    systems_science_mapping: list[str]
    mental_health_relevance: str
    observables: list[str]
    ml_features: list[str]
    claim_scope: str
    evidence_state: str
    allowed_use: list[str]
    prohibited_claims: list[str]
    safety_notes: list[str]

@dataclass(frozen=True)
class DisorderDynamicsMapping:
    clinical_domain: str
    dynamics_hypothesis: list[str]
    ToL_constructs: list[str]
    candidate_observables: list[str]
    candidate_ML_features: list[str]
    safe_interventions_category: list[str]
    contraindications: list[str]
    safety_escalation_triggers: list[str]
    claim_scope: str = "research_hypothesis"
    prohibited_claims: list[str] = field(default_factory=lambda: ["diagnosis", "intervention efficacy", "cure"])

@dataclass(frozen=True)
class MLFeatureGroup:
    feature_name: str
    feature_group: str
    description: str
    source: str
    privacy_risk: str
    clinical_sensitivity: str
    allowed_mode: str
    prohibited_use: str
    missing_data_strategy: str
    bias_risk: str
    validation_required: bool

@dataclass(frozen=True)
class ObservableMatrixRow:
    layer: str
    observable: str
    maps_to_constructs: list[str]
    measurement_source: str
    invasiveness: str
    privacy_risk: str
    reliability_notes: str
    missingness_notes: str
    validation_status: str
    claim_scope: str

@dataclass(frozen=True)
class ClinicalTranslationTier:
    tier: str
    mode: str
    allowed_use: str
    requirements: list[str]
    blocked_claims: list[str]

@dataclass(frozen=True)
class InterventionSafetyTier:
    level: int
    name: str
    allowed_patterns: list[str]
    blocked_patterns: list[str]
    requirements: list[str]

@dataclass(frozen=True)
class ValidationProtocol:
    protocol_id: str
    target_validity: str
    hypothesis: str
    measures: list[str]
    falsifiers: list[str]
    safety_controls: list[str]

@dataclass(frozen=True)
class ProductOpportunity:
    opportunity_id: str
    name: str
    stage: str
    value: str
    risks: list[str]
    guardrails: list[str]

@dataclass(frozen=True)
class BridgeValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    checked_files: list[str]

def to_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)
