"""Typed records for the Level O ontology evidence ledger."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, TypeVar


CLAIM_STATUSES = {"O-A", "O-B", "O-C", "O-X"}
SUPPORT_DIRECTIONS = {"supports", "opposes", "mixed", "background"}
FALSIFIER_SEVERITIES = {"low", "medium", "high", "decisive"}
SCORE_DIMENSIONS = (
    "empirical_support",
    "phenomenological_depth",
    "metaphysical_coherence",
    "falsifiability",
    "btc_icft_relevance",
    "risk_of_overclaim",
)

T = TypeVar("T", bound="Record")


class Record:
    """Common serialization helper for ledger records."""

    required_fields: ClassVar[tuple[str, ...]] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def _require(cls, data: dict[str, Any]) -> None:
        missing = [name for name in cls.required_fields if name not in data]
        if missing:
            raise ValueError(f"{cls.__name__} missing fields: {', '.join(missing)}")


@dataclass(frozen=True)
class OntologyClaim(Record):
    claim_id: str
    title: str
    statement: str
    status: str
    ladder_level: str
    required_evidence: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    score_inputs: dict[str, float] = field(default_factory=dict)

    required_fields = ("claim_id", "title", "statement", "status", "ladder_level")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OntologyClaim":
        cls._require(data)
        if data["status"] not in CLAIM_STATUSES:
            raise ValueError(f"Unknown claim status: {data['status']}")
        score_inputs = dict(data.get("score_inputs", {}))
        unknown = set(score_inputs) - set(SCORE_DIMENSIONS)
        if unknown:
            raise ValueError(f"Unknown score dimensions: {sorted(unknown)}")
        return cls(
            claim_id=str(data["claim_id"]),
            title=str(data["title"]),
            statement=str(data["statement"]),
            status=str(data["status"]),
            ladder_level=str(data["ladder_level"]),
            required_evidence=list(data.get("required_evidence", [])),
            guardrails=list(data.get("guardrails", [])),
            score_inputs={key: float(value) for key, value in score_inputs.items()},
        )


@dataclass(frozen=True)
class OntologyPaper(Record):
    paper_id: str
    title: str
    year: int
    field: str
    evidence_type: str
    url_or_doi: str
    notes: str

    required_fields = (
        "paper_id",
        "title",
        "year",
        "field",
        "evidence_type",
        "url_or_doi",
        "notes",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OntologyPaper":
        cls._require(data)
        return cls(
            paper_id=str(data["paper_id"]),
            title=str(data["title"]),
            year=int(data["year"]),
            field=str(data["field"]),
            evidence_type=str(data["evidence_type"]),
            url_or_doi=str(data["url_or_doi"]),
            notes=str(data["notes"]),
        )


@dataclass(frozen=True)
class OntologyClaimLink(Record):
    claim_id: str
    paper_id: str
    support_direction: str
    strength: float
    notes: str

    required_fields = (
        "claim_id",
        "paper_id",
        "support_direction",
        "strength",
        "notes",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OntologyClaimLink":
        cls._require(data)
        direction = str(data["support_direction"])
        strength = float(data["strength"])
        if direction not in SUPPORT_DIRECTIONS:
            raise ValueError(f"Unknown support direction: {direction}")
        if not 0 <= strength <= 5:
            raise ValueError("Claim-link strength must be between 0 and 5")
        return cls(
            claim_id=str(data["claim_id"]),
            paper_id=str(data["paper_id"]),
            support_direction=direction,
            strength=strength,
            notes=str(data["notes"]),
        )


@dataclass(frozen=True)
class OntologyScore(Record):
    claim_id: str
    empirical_support: float
    phenomenological_depth: float
    metaphysical_coherence: float
    falsifiability: float
    btc_icft_relevance: float
    risk_of_overclaim: float
    composite: float
    status: str
    gate_reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for dimension in SCORE_DIMENSIONS:
            value = getattr(self, dimension)
            if not 0 <= value <= 5:
                raise ValueError(f"{dimension} must be between 0 and 5")
        if self.status not in CLAIM_STATUSES:
            raise ValueError(f"Unknown claim status: {self.status}")


@dataclass(frozen=True)
class OntologyFalsifier(Record):
    claim_id: str
    falsifier_id: str
    description: str
    required_test: str
    severity: str

    required_fields = (
        "claim_id",
        "falsifier_id",
        "description",
        "required_test",
        "severity",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OntologyFalsifier":
        cls._require(data)
        severity = str(data["severity"])
        if severity not in FALSIFIER_SEVERITIES:
            raise ValueError(f"Unknown falsifier severity: {severity}")
        return cls(
            claim_id=str(data["claim_id"]),
            falsifier_id=str(data["falsifier_id"]),
            description=str(data["description"]),
            required_test=str(data["required_test"]),
            severity=severity,
        )


@dataclass(frozen=True)
class OntologyEvidenceEvent(Record):
    event_id: str
    claim_id: str
    event_type: str
    description: str
    source_ids: list[str] = field(default_factory=list)
    resulting_status: str = "O-C"

    def __post_init__(self) -> None:
        if self.resulting_status not in CLAIM_STATUSES:
            raise ValueError(f"Unknown claim status: {self.resulting_status}")
