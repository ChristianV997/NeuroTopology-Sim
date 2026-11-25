"""Record schema for the literature evidence adapter. Stdlib-only.

Source identity (`LiteratureRecord`) is deliberately kept separate from
claims about that source (`ClaimRecord`) -- a claim references a
source_id but is never embedded in or merged with the source record.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = "LiteratureEvidence.v1"

IDENTIFIER_TYPES: frozenset[str] = frozenset({"doi", "arxiv", "isbn", "url", "other"})

PUBLICATION_TYPES: frozenset[str] = frozenset({
    "peer_reviewed_journal_article",
    "conference_paper",
    "preprint",
    "theory_paper",
    "book_chapter",
    "technical_report",
    "other",
    "unknown",
})

REVIEW_STATUSES: frozenset[str] = frozenset({
    "unreviewed", "review_required", "reviewed_accepted", "reviewed_rejected", "disputed",
})

# Deliberately does NOT include "empirical"/"confirmed" -- this schema
# structurally cannot represent a promoted, confirmed-empirical source
# or claim. See package docstring.
EVIDENCE_CLASSES: frozenset[str] = frozenset({"hypothesis", "theoretical", "review_required", "proxy"})
CLAIM_KINDS: frozenset[str] = frozenset({"hypothesis", "review_required"})

SOURCE_STATUSES: frozenset[str] = frozenset({"active", "superseded", "disputed", "retracted"})

SNAPSHOT_KINDS: frozenset[str] = frozenset({"full_local_snapshot", "metadata_only"})

CITATION_RELATION_TYPES: frozenset[str] = frozenset({"cites", "cited_by", "related_to", "supersedes", "superseded_by"})

VALIDATION_STATES: frozenset[str] = frozenset({
    "valid",
    "rejected_missing_identity",
    "rejected_fabricated_identifier",
    "rejected_invalid_checksum",
    "rejected_unsupported_publication_status",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuplify(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


@dataclass(frozen=True)
class CitationRelation:
    related_source_id: str
    relation_type: str = "cites"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "CitationRelation":
        return CitationRelation(**data)


@dataclass
class LiteratureRecord:
    """Source identity -- never carries claim text. Every field defaults
    to an explicit absence; nothing here is inferred or fabricated by
    this package."""

    source_id: str
    identifier: Optional[str] = None
    identifier_type: str = "other"
    title: str = ""
    authors: tuple[str, ...] = field(default_factory=tuple)
    venue: Optional[str] = None
    publication_type: str = "unknown"
    publication_date: Optional[str] = None
    source_url: Optional[str] = None
    retrieval_timestamp: str = field(default_factory=_now_iso)
    content_checksum: Optional[str] = None
    excerpt_hash: Optional[str] = None
    citation_relations: tuple[CitationRelation, ...] = field(default_factory=tuple)
    review_status: str = "review_required"
    evidence_class: str = "review_required"
    version: int = 1
    status: str = "active"
    superseded_by: Optional[str] = None

    def __post_init__(self) -> None:
        self.authors = _tuplify(self.authors)
        relations = self.citation_relations
        if isinstance(relations, list):
            relations = tuple(relations)
        self.citation_relations = tuple(
            r if isinstance(r, CitationRelation) else CitationRelation.from_dict(r) for r in relations
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["citation_relations"] = [r.to_dict() for r in self.citation_relations]
        data["schema"] = SCHEMA_VERSION
        return data

    @staticmethod
    def from_dict(data: dict) -> "LiteratureRecord":
        data = dict(data)
        data.pop("schema", None)
        return LiteratureRecord(**data)


@dataclass
class SourceSnapshot:
    """A local capture of a source's content -- either a full local
    snapshot (a file this package can checksum) or an explicit
    metadata-only record (no local content at all)."""

    snapshot_id: str
    source_id: str
    kind: str = "metadata_only"
    local_path: Optional[str] = None
    content_checksum: Optional[str] = None
    captured_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "SourceSnapshot":
        return SourceSnapshot(**data)


@dataclass
class ClaimRecord:
    """A claim ABOUT a source, kept structurally separate from the
    source's own identity record. ``claim_kind`` can only ever be
    ``hypothesis`` or ``review_required`` -- this schema has no
    "empirical"/"confirmed" value to promote a claim into."""

    claim_id: str
    source_id: str
    claim_text: str
    claim_kind: str = "hypothesis"
    confidence: Optional[float] = None
    notes: str = ""
    version: int = 1
    status: str = "active"

    def __post_init__(self) -> None:
        if self.claim_kind not in CLAIM_KINDS:
            raise ValueError(
                f"claim_kind={self.claim_kind!r} is not one of {sorted(CLAIM_KINDS)} -- "
                "this adapter never represents a claim as empirical/confirmed"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ClaimRecord":
        return ClaimRecord(**data)


@dataclass(frozen=True)
class ValidationResult:
    state: str
    errors: tuple[str, ...]

    def is_valid(self) -> bool:
        return self.state == "valid"

    def to_dict(self) -> dict:
        return {"state": self.state, "errors": list(self.errors), "is_valid": self.is_valid()}
