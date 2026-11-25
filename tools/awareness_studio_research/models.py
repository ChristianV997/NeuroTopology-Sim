"""Record schema for the evidence registry. Stdlib-only (dataclasses).

Every record is content-addressed by a stable id derived from its
identity fields (never a random UUID), so re-ingesting the same source
or claim is detectable and deterministic across runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

SOURCE_TYPES = frozenset({
    "journal_article", "preprint", "conference_paper", "book_chapter",
    "dataset", "technical_report", "manual_capture", "other",
})

PEER_REVIEW_STATUSES = frozenset({
    "peer_reviewed", "preprint_not_peer_reviewed", "editorial_review", "unknown",
})

EVIDENCE_TIERS = frozenset({
    "T1_verified_primary",       # metadata independently confirmed against a real record
    "T2_verified_secondary",     # confirmed via a secondary/aggregator source
    "T3_unverified_claimed",     # only the operator's/prompt's claim, not independently confirmed
    "T4_disputed",               # verification attempted and produced a contradiction
})

VERIFICATION_STATUSES = frozenset({"verified", "unverified", "disputed"})

SOURCE_STATUSES = frozenset({"active", "superseded", "disputed", "retracted"})

CLAIM_STATUSES = frozenset({
    "empirical", "theoretical", "proxy", "speculative", "unsupported",
})

CLAIM_CLASSES = frozenset({
    "correlational", "causal", "theoretical", "methodological", "descriptive",
})

BIO_VS_METHODOLOGICAL = frozenset({"biological", "methodological", "mixed", "not_applicable"})

CORRELATE_TYPES = frozenset({"neural", "physiological", "autonomic", "behavioral", "other"})

LINK_RELATIONSHIPS = frozenset({"supports", "contradicts", "refines", "extends", "unrelated"})

RETRIEVAL_METHODS = frozenset({
    "operator_manual", "arxiv_api", "doi_operator_supplied", "manual_capture",
    "json_export", "csv_export",
})


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _coerce_tuple_fields(instance: Any, *field_names: str) -> None:
    """Round-tripping a record through JSON (the event log) turns every
    tuple field into a list; call this from ``__post_init__`` to coerce
    it back so records are always hashable/comparable the same way
    regardless of whether they came fresh from a constructor call or
    were replayed from the log."""
    for name in field_names:
        value = getattr(instance, name)
        if isinstance(value, list):
            setattr(instance, name, tuple(value))


@dataclass
class LiteratureSource:
    source_id: str
    title: str
    authors: tuple[str, ...] = field(default_factory=tuple)
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    publication_date: Optional[str] = None
    source_type: str = "other"
    retrieval_timestamp: str = ""
    source_checksum: str = ""
    abstract_or_excerpt: str = ""
    peer_review_status: str = "unknown"
    evidence_tier: str = "T3_unverified_claimed"
    limitations: tuple[str, ...] = field(default_factory=tuple)
    license_or_access_status: str = "unknown"
    verification_status: str = "unverified"
    disagreements: tuple[str, ...] = field(default_factory=tuple)
    retrieval_metadata: dict = field(default_factory=dict)
    version: int = 1
    status: str = "active"
    superseded_by: Optional[str] = None

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "authors", "limitations", "disagreements")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedClaim:
    claim_id: str
    source_id: str
    claim_text: str
    claim_class: str = "descriptive"
    source_location: str = ""
    supporting_excerpt: str = ""
    confidence: float = 0.0
    alternative_interpretation: str = ""
    bio_vs_methodological: str = "not_applicable"
    linked_hypothesis: Optional[str] = None
    claim_status: str = "unsupported"
    tags: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1
    status: str = "active"
    superseded_by: Optional[str] = None

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "tags")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Correlate:
    correlate_id: str
    name: str
    correlate_type: str = "other"
    linked_claims: tuple[str, ...] = field(default_factory=tuple)
    measurement_method: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "linked_claims")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HypothesisLink:
    link_id: str
    hypothesis_id: str
    claim_ids: tuple[str, ...] = field(default_factory=tuple)
    relationship: str = "supports"
    notes: str = ""

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "claim_ids")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DatasetLink:
    link_id: str
    dataset_id: str
    claim_ids: tuple[str, ...] = field(default_factory=tuple)
    relationship: str = "supports"

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "claim_ids")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExperimentLink:
    link_id: str
    experiment_ref: str
    claim_ids: tuple[str, ...] = field(default_factory=tuple)
    relationship: str = "supports"

    def __post_init__(self) -> None:
        _coerce_tuple_fields(self, "claim_ids")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceUpdate:
    update_id: str
    entity_type: str
    entity_id: str
    update_type: str  # "created" | "downgraded" | "superseded" | "disputed" | "amended"
    previous_version: Optional[int]
    new_version: int
    reason: str
    timestamp: str = field(default_factory=_now_iso)
    actor: str = "operator"

    def to_dict(self) -> dict:
        return asdict(self)
