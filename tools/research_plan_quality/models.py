"""Input schema (the research plan / preregistration manifest being
audited) and output schema (the audit result). Stdlib-only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

RUBRIC_DIMENSIONS: tuple[str, ...] = (
    "falsifiable_question",
    "primary_endpoint",
    "alternative_explanations",
    "source_quality_provenance",
    "dataset_identity_checksum",
    "condition_label_validity",
    "pairing_sample_size_adequacy",
    "power_or_precision_plan",
    "multiplicity_correction",
    "null_model_specification",
    "leakage_prevention",
    "split_strategy",
    "preprocessing_lock",
    "measurement_limitations",
    "compute_resource_budget",
    "reproducibility",
    "claim_calibration",
    "evidence_separation",
    "replication_plan",
    "ethical_privacy_constraints",
)
assert len(RUBRIC_DIMENSIONS) == 20

CRITERION_STATUSES: frozenset[str] = frozenset({"pass", "warning", "blocker", "missing"})

OVERALL_STATUSES: frozenset[str] = frozenset({"READY_FOR_EXECUTION", "NEEDS_REVISION", "BLOCKED"})

EVIDENCE_CLASSES: frozenset[str] = frozenset({"synthetic", "proxy", "empirical"})

_SCORE_BY_STATUS = {"pass": 1.0, "warning": 0.5, "blocker": 0.0, "missing": 0.0}


def _tuplify(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


@dataclass(frozen=True)
class SourceProvenance:
    title: str = ""
    identifier: Optional[str] = None  # a DOI, arXiv id, or URL
    verification_status: Optional[str] = None  # "verified" | "unverified" | "disputed" | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PowerAnalysis:
    method: Optional[str] = None
    target_power: Optional[float] = None
    effect_size: Optional[float] = None
    alpha: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NullModelSpec:
    method: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SplitStrategy:
    unit: Optional[str] = None  # "subject" | "session" | "time"
    method: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComputeBudget:
    estimated_hours: Optional[float] = None
    hardware: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReproducibilityPlan:
    seed: Optional[int] = None
    code_version: Optional[str] = None
    environment_pinned: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EthicsPrivacy:
    irb_status: Optional[str] = None
    privacy_measures: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {"irb_status": self.irb_status, "privacy_measures": list(self.privacy_measures)}


@dataclass
class ResearchPlan:
    """The plan/manifest being audited. Every field defaults to an
    explicit absence (``None``/empty tuple) -- the evaluator never
    fabricates a value for a field the caller left out."""

    plan_id: str = ""
    research_question: str = ""
    falsifiability_criteria: str = ""
    primary_endpoint: str = ""
    secondary_endpoints: tuple[str, ...] = field(default_factory=tuple)
    alternative_explanations: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[SourceProvenance, ...] = field(default_factory=tuple)
    dataset_id: Optional[str] = None
    dataset_checksum: Optional[str] = None
    condition_labels: tuple[str, ...] = field(default_factory=tuple)
    condition_label_definitions: dict[str, str] = field(default_factory=dict)
    sample_size: Optional[int] = None
    minimum_required_sample_size: Optional[int] = None
    pairing_strategy: Optional[str] = None
    power_analysis: Optional[PowerAnalysis] = None
    multiplicity_correction: Optional[str] = None
    number_of_planned_tests: Optional[int] = None
    null_model: Optional[NullModelSpec] = None
    leakage_controls: tuple[str, ...] = field(default_factory=tuple)
    known_leakage_risks: tuple[str, ...] = field(default_factory=tuple)
    split_strategy: Optional[SplitStrategy] = None
    preprocessing_steps: tuple[str, ...] = field(default_factory=tuple)
    preprocessing_locked_before_analysis: Optional[bool] = None
    measurement_limitations: tuple[str, ...] = field(default_factory=tuple)
    compute_budget: Optional[ComputeBudget] = None
    reproducibility: Optional[ReproducibilityPlan] = None
    claim_language: str = ""
    evidence_class_declared: Optional[str] = None
    replication_plan: Optional[str] = None
    ethics_privacy: Optional[EthicsPrivacy] = None

    def __post_init__(self) -> None:
        for name in (
            "secondary_endpoints", "alternative_explanations", "condition_labels",
            "leakage_controls", "known_leakage_risks", "preprocessing_steps",
            "measurement_limitations",
        ):
            setattr(self, name, _tuplify(getattr(self, name)))
        if isinstance(self.sources, list):
            self.sources = tuple(self.sources)
        self.sources = tuple(
            s if isinstance(s, SourceProvenance) else SourceProvenance(**s) for s in self.sources
        )
        if isinstance(self.power_analysis, dict):
            self.power_analysis = PowerAnalysis(**self.power_analysis)
        if isinstance(self.null_model, dict):
            self.null_model = NullModelSpec(**self.null_model)
        if isinstance(self.split_strategy, dict):
            self.split_strategy = SplitStrategy(**self.split_strategy)
        if isinstance(self.compute_budget, dict):
            self.compute_budget = ComputeBudget(**self.compute_budget)
        if isinstance(self.reproducibility, dict):
            self.reproducibility = ReproducibilityPlan(**self.reproducibility)
        if isinstance(self.ethics_privacy, dict):
            data = dict(self.ethics_privacy)
            data["privacy_measures"] = _tuplify(data.get("privacy_measures"))
            self.ethics_privacy = EthicsPrivacy(**data)
        elif isinstance(self.ethics_privacy, EthicsPrivacy):
            pass

    @staticmethod
    def from_dict(data: dict) -> "ResearchPlan":
        return ResearchPlan(**data)


@dataclass(frozen=True)
class CriterionResult:
    dimension: str
    status: str  # "pass" | "warning" | "blocker" | "missing"
    detail: str
    score: float

    def to_dict(self) -> dict:
        return {"dimension": self.dimension, "status": self.status, "detail": self.detail, "score": self.score}


def make_result(dimension: str, status: str, detail: str) -> CriterionResult:
    if status not in CRITERION_STATUSES:
        raise ValueError(f"unrecognized criterion status: {status!r}")
    return CriterionResult(dimension=dimension, status=status, detail=detail, score=_SCORE_BY_STATUS[status])


@dataclass(frozen=True)
class PlanAuditResult:
    plan_id: str
    criteria: tuple[CriterionResult, ...]
    missing_fields: tuple[str, ...]
    hard_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_revisions: tuple[str, ...]
    overall_status: str
    overall_score: float
    evidence_class: str = "research_plan_audit"
    generated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "criteria": [c.to_dict() for c in self.criteria],
            "missing_fields": list(self.missing_fields),
            "hard_blockers": list(self.hard_blockers),
            "warnings": list(self.warnings),
            "recommended_revisions": list(self.recommended_revisions),
            "overall_status": self.overall_status,
            "overall_score": self.overall_score,
            "evidence_class": self.evidence_class,
            "generated_at": self.generated_at,
        }
