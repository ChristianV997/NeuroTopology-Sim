"""Versioned data models and schemas for the Research Cycle Registry.

Defines schemas:
- HypothesisRecord.v1
- ExperimentPlan.v1
- PredictionRecord.v1
- EvidenceUpdate.v1
- TheoryRevision.v1

Along with lifecycle status enums and validation records.
"""
from __future__ import annotations

import enum
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


class HypothesisStatus(str, enum.Enum):
    """Permitted lifecycle statuses for a hypothesis."""
    PROPOSED = "proposed"
    PREREGISTERED = "preregistered"
    READY_FOR_EXECUTION = "ready_for_execution"
    EXECUTED = "executed"
    SUPPORTED_AS_SPECIFIED = "supported_as_specified"
    WEAKENED = "weakened"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"
    BLOCKED_BY_DATA = "blocked_by_data"
    BLOCKED_BY_METHOD = "blocked_by_method"
    RETIRED = "retired"


class EpistemicLabel(str, enum.Enum):
    """Epistemic status of a claim."""
    SPECULATIVE_HYPOTHESIS = "speculative_hypothesis"
    EXPLORATORY = "exploratory"
    PREREGISTERED_EMPIRICAL = "preregistered_empirical"
    COMPUTATIONAL_MODEL = "computational_model"
    SURROGATE_BASELINE = "surrogate_baseline"
    EMPIRICALLY_CONSTRAINED = "empirically_constrained"


class ExperimentDomain(str, enum.Enum):
    """Domain categorization for planned experiments."""
    PAIRWISE_VS_TRIADIC_FC = "pairwise_vs_triadic_fc"
    HIGHER_ORDER_SPECTRA = "higher_order_spectra"
    RESPIRATION_AUTONOMIC_MODULATION = "respiration_autonomic_modulation"
    DISCERNMENT_NONJUDGMENT_OPERATIONALIZATION = "discernment_nonjudgment_operationalization"
    HYPERGRAPH_TRANSITION_FORECASTING = "hypergraph_transition_forecasting"
    NULL_AND_SURROGATE = "null_and_surrogate"


class EvidenceDataType(str, enum.Enum):
    """Classification of evidence data source."""
    EMPIRICAL_DATASET = "empirical_dataset"
    SYNTHETIC_SIMULATION = "synthetic_simulation"
    LITERATURE_CLAIM = "literature_claim"
    PROXY_BAYES_FACTOR = "proxy_bayes_factor"


@dataclass(frozen=True)
class HumanReviewGate:
    """Explicit human oversight gate required for promotion to supported/fact."""
    passed: bool = False
    reviewer: str | None = None
    timestamp: str | None = None
    review_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class HypothesisRecord:
    """Versioned hypothesis record (HypothesisRecord.v1)."""
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
    epistemic_label: str = EpistemicLabel.SPECULATIVE_HYPOTHESIS.value
    status: str = HypothesisStatus.PROPOSED.value
    schema_version: str = "HypothesisRecord.v1"
    human_review_gate: HumanReviewGate = field(default_factory=HumanReviewGate)
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
            "predicted_direction": self.predicted_direction,
            "null_prediction": self.null_prediction,
            "alternative_explanations": self.alternative_explanations,
            "falsification_criterion": self.falsification_criterion,
            "min_sample_size_or_power": self.min_sample_size_or_power,
            "preregistration_reference": self.preregistration_reference,
            "data_requirements": self.data_requirements,
            "analysis_plan": self.analysis_plan,
            "provenance": self.provenance,
            "epistemic_label": self.epistemic_label,
            "status": self.status,
            "human_review_gate": self.human_review_gate.to_dict(),
            "evidence_links": list(self.evidence_links),
            "contradictory_evidence_links": list(self.contradictory_evidence_links),
            "revision_history": self.revision_history,
            "unresolved_questions": list(self.unresolved_questions),
            "checksum": self.checksum,
        })


@dataclass
class ExperimentPlan:
    """Versioned experiment plan (ExperimentPlan.v1)."""
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
            "is_synthetic": self.is_synthetic,
            "provenance": self.provenance,
            "checksum": self.checksum,
        })


@dataclass
class PredictionRecord:
    """Versioned prediction record (PredictionRecord.v1)."""
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
class EvidenceUpdate:
    """Versioned evidence update record (EvidenceUpdate.v1)."""
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
class TheoryRevision:
    """Versioned theory revision record (TheoryRevision.v1)."""
    revision_id: str
    hypothesis_id: str
    previous_status: str
    new_status: str
    reason_codes: list[str]
    evidence_ids: list[str]
    modifications: dict[str, Any]
    unresolved_questions: list[str]
    human_review_signed: bool
    reviewer_id: str | None
    schema_version: str = "TheoryRevision.v1"
    timestamp: str = ""
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "hypothesis_id": self.hypothesis_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "reason_codes": list(self.reason_codes),
            "evidence_ids": list(self.evidence_ids),
            "modifications": self.modifications,
            "unresolved_questions": list(self.unresolved_questions),
            "human_review_signed": self.human_review_signed,
            "reviewer_id": self.reviewer_id,
            "timestamp": self.timestamp,
            "checksum": self.checksum,
        })


def _safe_dict(val: Any) -> Any:
    """Recursively enforce finite floats and serialize enums/objects."""
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
