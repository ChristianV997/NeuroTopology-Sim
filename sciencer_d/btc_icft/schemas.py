from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Literal

LayerName = Literal["D", "M", "T", "C", "Q", "OMEGA"]
ClaimStatus = Literal["active", "proposed", "quarantined", "blocked", "demoted", "rejected"]


def _finite(value: float | None, name: str) -> None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{name} must be finite or None")


def _prob(value: float | None, name: str) -> None:
    _finite(value, name)
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True)
class LabelContract:
    row_id: str
    subject_id: str
    session_id: str | None
    window_id: str
    state_label: str | None
    behavior_label: str | None
    report_label: str | None
    confidence: float | None = None
    caveats: list[str] = field(default_factory=list)

    def validate(self) -> None:
        _prob(self.confidence, "confidence")
        if not self.row_id or not self.subject_id or not self.window_id:
            raise ValueError("row_id, subject_id, and window_id are required")
        unresp = "un" + "responsive"
        if self.behavior_label == unresp and self.report_label == "no_experience":
            raise ValueError("invalid behavior/report shortcut")
        caveats = {c.lower() for c in self.caveats}
        if self.behavior_label == unresp and ("un" + "conscious") in caveats:
            raise ValueError("invalid behavior/state shortcut")
        if self.state_label == "cessation_candidate" and ("lib" + "eration") in caveats:
            raise ValueError("invalid state/outcome shortcut")
        if self.state_label == "meditation" and ("attain" + "ment") in caveats:
            raise ValueError("invalid condition/outcome shortcut")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class FeatureVector:
    row_id: str
    layer: LayerName
    features: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.layer not in {"D", "M", "T", "C", "Q", "OMEGA"}:
            raise ValueError(f"invalid layer: {self.layer}")
        if not self.row_id:
            raise ValueError("row_id is required")
        for key, value in self.features.items():
            _finite(value, f"features.{key}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ModelResult:
    task_id: str
    model_id: str
    feature_layers: list[LayerName]
    auc: float | None
    ece: float | None
    brier: float | None
    leakage_detected: bool
    artifact_dominance: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.task_id or not self.model_id:
            raise ValueError("task_id and model_id are required")
        _prob(self.auc, "auc")
        _finite(self.ece, "ece")
        _finite(self.brier, "brier")
        for layer in self.feature_layers:
            if layer not in {"D", "M", "T", "C", "Q", "OMEGA"}:
                raise ValueError(f"invalid feature layer: {layer}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ResidualResult:
    task_id: str
    baseline_model_id: str
    candidate_model_id: str
    auc_baseline: float | None
    auc_candidate: float | None
    delta_auc: float | None
    ece_baseline: float | None
    ece_candidate: float | None
    delta_ece: float | None
    nulls_passed: bool
    ablations_passed: bool
    leakage_detected: bool
    artifact_dominance: bool
    promoted: bool

    def validate(self) -> None:
        if not self.task_id:
            raise ValueError("task_id is required")
        _prob(self.auc_baseline, "auc_baseline")
        _prob(self.auc_candidate, "auc_candidate")
        _finite(self.delta_auc, "delta_auc")
        _finite(self.ece_baseline, "ece_baseline")
        _finite(self.ece_candidate, "ece_candidate")
        _finite(self.delta_ece, "delta_ece")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class OmegaEvidenceEvent:
    event_id: str
    dataset_id: str
    task_id: str
    claim_id: str
    layer: LayerName
    status: ClaimStatus
    metrics: dict[str, float | None]
    controls: dict[str, bool]
    allowed_claim: str
    blocked_claims: list[str]
    not_implied: list[str]
    next_required_test: str | None = None

    def validate(self) -> None:
        if self.layer not in {"D", "M", "T", "C", "Q", "OMEGA"}:
            raise ValueError(f"invalid layer: {self.layer}")
        if self.status not in {"active", "proposed", "quarantined", "blocked", "demoted", "rejected"}:
            raise ValueError(f"invalid status: {self.status}")
        if not all([self.event_id, self.dataset_id, self.task_id, self.claim_id, self.allowed_claim]):
            raise ValueError("event fields are incomplete")
        for key, value in self.metrics.items():
            _finite(value, f"metrics.{key}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class MBaselineResult:
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class ResidualGateInput:
    m_baseline_passed: bool
    delta_auc: float
    delta_ece: float | None
    nulls_passed: bool
    ablations_passed: bool
    leakage_detected: bool
    artifact_dominance: bool


@dataclass(frozen=True)
class ResidualGateResult:
    promoted: bool
    reason: str
