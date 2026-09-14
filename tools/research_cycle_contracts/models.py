"""Typed versioned schemas and models for research cycle contract compatibility.

Defines schemas:
- HypothesisRecord.v1
- ExperimentPlan.v1
- PredictionRecord.v1
- EvidenceUpdate.v1
- AwarenessHypothesisNode.v1
- AwarenessStudioCycleInput.v1
- ExperimentLedgerRow.v1
- MigrationWarning
"""
from __future__ import annotations

import enum
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


class RejectionReasonCode(str, enum.Enum):
    """Machine-readable rejection reason codes."""
    MISSING_SOURCE_PROVENANCE = "missing_source_provenance"
    UNSUPPORTED_PROMOTION = "unsupported_promotion"
    SYNTHETIC_EMPIRICAL_CLAIMS = "synthetic_empirical_claims"
    MISSING_FALSIFICATION_CRITERIA = "missing_falsification_criteria"
    MISSING_NULL_PREDICTION = "missing_null_prediction"
    INCOMPATIBLE_FEATURE_FAMILIES = "incompatible_feature_families"
    UNVERIFIED_FORMAL_STATUS = "unverified_formal_status"


class SupportedFeatureFamily(str, enum.Enum):
    """Permitted feature families for topological and neurodynamic representations."""
    TOPOLOGICAL_HOMOLOGY = "topological_homology"
    TRIADIC_HYPERGRAPH = "triadic_hypergraph"
    SPECTRAL_COUPLING = "spectral_coupling"
    AUTONOMIC_MODULATION = "autonomic_modulation"
    DYNAMICAL_METASTABILITY = "dynamical_metastability"
    SURROGATE_NULL = "surrogate_null"


@dataclass(frozen=True)
class MigrationWarning:
    """Record of non-breaking schema adaptation or field translation."""
    source_version: str
    target_version: str
    field_name: str
    warning_type: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class HypothesisRecordV1:
    """HypothesisRecord.v1 matching the hypothesis registry schema."""
    hypothesis_id: str
    precise_claim: str
    construct_definitions: dict[str, str]
    operational_variables: dict[str, str]
    predicted_direction: str
    null_prediction: str
    alternative_explanations: list[str]
    falsification_criterion: str
    min_sample_size_or_power: dict[str, Any]
    preregistration_reference: str | None
    data_requirements: list[str]
    analysis_plan: str
    provenance: dict[str, Any]
    feature_family: str = SupportedFeatureFamily.TOPOLOGICAL_HOMOLOGY.value
    dataset_ids: list[str] = field(default_factory=list)
    epistemic_label: str = "speculative_hypothesis"
    status: str = "proposed"
    evidence_class: str = "descriptive_or_paired_statistics"
    schema_version: str = "HypothesisRecord.v1"
    human_review_gate: dict[str, Any] = field(default_factory=lambda: {"passed": False, "reviewer": None, "timestamp": None, "notes": ""})
    evidence_links: list[str] = field(default_factory=list)
    contradictory_evidence_links: list[str] = field(default_factory=list)
    revision_history: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "hypothesis_id": self.hypothesis_id,
            "precise_claim": self.precise_claim,
            "construct_definitions": self.construct_definitions,
            "operational_variables": self.operational_variables,
            "feature_family": self.feature_family,
            "predicted_direction": self.predicted_direction,
            "null_prediction": self.null_prediction,
            "alternative_explanations": list(self.alternative_explanations),
            "falsification_criterion": self.falsification_criterion,
            "min_sample_size_or_power": self.min_sample_size_or_power,
            "preregistration_reference": self.preregistration_reference,
            "data_requirements": list(self.data_requirements),
            "dataset_ids": list(self.dataset_ids),
            "analysis_plan": self.analysis_plan,
            "provenance": self.provenance,
            "epistemic_label": self.epistemic_label,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "human_review_gate": self.human_review_gate,
            "evidence_links": list(self.evidence_links),
            "contradictory_evidence_links": list(self.contradictory_evidence_links),
            "revision_history": self.revision_history,
            "unresolved_questions": list(self.unresolved_questions),
            "checksum": self.checksum,
        })


@dataclass
class ExperimentPlanV1:
    """ExperimentPlan.v1 representing an experiment execution plan."""
    plan_id: str
    hypothesis_id: str
    domain: str
    design_type: str
    variables: dict[str, Any]
    target_sample_size: int
    power_analysis: dict[str, Any]
    analysis_protocol: str
    surrogate_method: str | None = None
    data_source: str = ""
    dataset_id: str = ""
    is_synthetic: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "ExperimentPlan.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "hypothesis_id": self.hypothesis_id,
            "domain": self.domain,
            "design_type": self.design_type,
            "variables": self.variables,
            "target_sample_size": self.target_sample_size,
            "power_analysis": self.power_analysis,
            "analysis_protocol": self.analysis_protocol,
            "surrogate_method": self.surrogate_method,
            "data_source": self.data_source,
            "dataset_id": self.dataset_id,
            "is_synthetic": self.is_synthetic,
            "provenance": self.provenance,
            "checksum": self.checksum,
        })


@dataclass
class PredictionRecordV1:
    """PredictionRecord.v1 representing a preregistered prediction."""
    prediction_id: str
    hypothesis_id: str
    plan_id: str
    metric_name: str
    expected_direction: str
    expected_effect_range: list[float] | tuple[float, float] | None
    falsification_threshold: dict[str, Any]
    is_preregistered: bool = True
    schema_version: str = "PredictionRecord.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "prediction_id": self.prediction_id,
            "hypothesis_id": self.hypothesis_id,
            "plan_id": self.plan_id,
            "metric_name": self.metric_name,
            "expected_direction": self.expected_direction,
            "expected_effect_range": self.expected_effect_range,
            "falsification_threshold": self.falsification_threshold,
            "is_preregistered": self.is_preregistered,
            "checksum": self.checksum,
        })


@dataclass
class EvidenceUpdateV1:
    """EvidenceUpdate.v1 reporting empirical or simulation outcomes."""
    evidence_id: str
    hypothesis_id: str
    experiment_id: str
    source_checksum: str
    experiment_checksum: str
    data_type: str
    is_synthetic: bool
    is_out_of_sample: bool
    metrics_observed: dict[str, Any]
    observed_effect_size: float | None
    observed_p_value: float | None
    source_ids: list[str] = field(default_factory=list)
    dataset_ids: list[str] = field(default_factory=list)
    is_contradictory: bool = False
    contradiction_details: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    schema_version: str = "EvidenceUpdate.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "hypothesis_id": self.hypothesis_id,
            "experiment_id": self.experiment_id,
            "source_ids": list(self.source_ids),
            "dataset_ids": list(self.dataset_ids),
            "source_checksum": self.source_checksum,
            "experiment_checksum": self.experiment_checksum,
            "data_type": self.data_type,
            "is_synthetic": self.is_synthetic,
            "is_out_of_sample": self.is_out_of_sample,
            "metrics_observed": self.metrics_observed,
            "observed_effect_size": self.observed_effect_size,
            "observed_p_value": self.observed_p_value,
            "is_contradictory": self.is_contradictory,
            "contradiction_details": self.contradiction_details,
            "provenance": self.provenance,
            "notes": self.notes,
            "checksum": self.checksum,
        })


@dataclass
class AwarenessHypothesisNodeV1:
    """AwarenessHypothesisNode.v1 consumed by Awareness Studio graph/orchestrator."""
    node_id: str
    label: str
    construct: str
    operationalization: dict[str, Any]
    feature_family: str
    null_prediction: str
    falsification_criteria: str
    status: str
    evidence_class: str
    human_reviewer: str | None
    human_review_passed: bool
    source_ids: list[str] = field(default_factory=list)
    dataset_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    schema_version: str = "AwarenessHypothesisNode.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "label": self.label,
            "construct": self.construct,
            "operationalization": self.operationalization,
            "feature_family": self.feature_family,
            "null_prediction": self.null_prediction,
            "falsification_criteria": self.falsification_criteria,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "human_reviewer": self.human_reviewer,
            "human_review_passed": self.human_review_passed,
            "source_ids": list(self.source_ids),
            "dataset_ids": list(self.dataset_ids),
            "evidence_ids": list(self.evidence_ids),
            "contradictions": list(self.contradictions),
            "checksum": self.checksum,
        })


@dataclass
class AwarenessStudioCycleInputV1:
    """AwarenessStudioCycleInput.v1 top-level input artifact for research orchestrator."""
    cycle_id: str
    contract_version: str
    nodes: list[AwarenessHypothesisNodeV1]
    plans: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "AwarenessStudioCycleInput.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "cycle_id": self.cycle_id,
            "contract_version": self.contract_version,
            "nodes": [n.to_dict() for n in self.nodes],
            "plans": self.plans,
            "evidence": self.evidence,
            "metadata": self.metadata,
            "checksum": self.checksum,
        })


@dataclass
class ExperimentLedgerRowV1:
    """ExperimentLedgerRow.v1 row-oriented experiment ledger entry."""
    row_id: str
    experiment_id: str
    hypothesis_id: str
    plan_id: str
    dataset_id: str
    source_id: str
    feature_family: str
    is_synthetic: bool
    falsification_threshold: str
    null_prediction: str
    observed_effect: float | None
    observed_p: float | None
    outcome_status: str
    is_contradictory: bool
    contradiction_reason: str | None
    reviewer_signoff: str | None
    evidence_checksum: str
    provenance_tag: str
    schema_version: str = "ExperimentLedgerRow.v1"
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "row_id": self.row_id,
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "plan_id": self.plan_id,
            "dataset_id": self.dataset_id,
            "source_id": self.source_id,
            "feature_family": self.feature_family,
            "is_synthetic": self.is_synthetic,
            "falsification_threshold": self.falsification_threshold,
            "null_prediction": self.null_prediction,
            "observed_effect": self.observed_effect,
            "observed_p": self.observed_p,
            "outcome_status": self.outcome_status,
            "is_contradictory": self.is_contradictory,
            "contradiction_reason": self.contradiction_reason,
            "reviewer_signoff": self.reviewer_signoff,
            "evidence_checksum": self.evidence_checksum,
            "provenance_tag": self.provenance_tag,
            "checksum": self.checksum,
        })


def _safe_dict(val: Any) -> Any:
    """Enforces standard JSON RFC-8259 compliance (finite floats, recursive serialization)."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, enum.Enum):
        return val.value
    if isinstance(val, Mapping):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_dict(v) for v in val]
    return str(val)
