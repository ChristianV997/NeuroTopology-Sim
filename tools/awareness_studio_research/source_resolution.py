"""Source-identity resolution for the Awareness Studio evidence registry.

This module is deliberately self-contained: it imports nothing from
``tools/awareness_studio_research/store.py`` or ``models.py`` (the
registry from PR #276), which this branch must not modify and may not
even be present yet in this checkout (parallel, unmerged sibling work).
Every type and the append-only event log used here are freshly,
independently implemented, exactly the same convention this session has
used for every other decoupled tool package.

**Source identity verification is not scientific claim verification.**
Resolving *which real paper* a claimed DOI/arXiv id refers to says
nothing about whether that paper's findings are true. Claim extraction
must be gated on identity resolution (see ``claim_extraction_permitted``)
precisely to keep those two questions separate: a claim should never be
attributed to a source whose very identity is still disputed or
ambiguous.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

RESOLUTION_STATES: frozenset[str] = frozenset({
    "confirmed_identity",
    "disputed_identity",
    "ambiguous_identity",
    "unavailable",
    "superseded",
    "duplicate",
})

# States under which it is safe to attribute an extracted scientific
# claim to a source. Everything else must report claim availability as
# "unavailable" (requirement 5).
_CLAIM_EXTRACTION_PERMITTED_STATES = frozenset({"confirmed_identity", "superseded", "duplicate"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def normalize_author(name: str) -> str:
    """Normalize an author name to a comparable surname-first token so
    'W. Huang' and 'Wenhao Huang' can overlap on surname even though
    they will never match as exact strings."""
    parts = normalize_text(name).replace(".", " ").split()
    return parts[-1] if parts else ""


@dataclass(frozen=True)
class SourceIdentity:
    """A minimal identity fingerprint for one claimed or candidate
    source -- deliberately narrower than the full registry's
    ``LiteratureSource``, since resolution only needs the fields that
    feed identity verification (requirement 2)."""

    source_ref: str  # a label/id the caller uses to refer to this identity
    title: str = ""
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    authors: tuple[str, ...] = field(default_factory=tuple)
    publication_date: Optional[str] = None  # ISO date or year string
    journal: Optional[str] = None
    checksum: Optional[str] = None
    exists: Optional[bool] = None  # None = unknown, False = confirmed not to exist anywhere

    def to_dict(self) -> dict:
        return {
            "source_ref": self.source_ref,
            "title": self.title,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "authors": list(self.authors),
            "publication_date": self.publication_date,
            "journal": self.journal,
            "checksum": self.checksum,
            "exists": self.exists,
        }

    @staticmethod
    def from_dict(data: dict) -> "SourceIdentity":
        data = dict(data)
        data["authors"] = tuple(data.get("authors") or ())
        return SourceIdentity(**data)


@dataclass(frozen=True)
class MatchEvidence:
    candidate_ref: str
    score: float
    signals: tuple[str, ...]


def _publication_year(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else None


def score_candidate(claimed: SourceIdentity, candidate: SourceIdentity) -> MatchEvidence:
    """Weighted identity-match score in [0, 1] plus the specific signals
    that fired, per requirement 2's field list."""
    signals: list[str] = []
    score = 0.0

    if claimed.doi and candidate.doi and normalize_text(claimed.doi) == normalize_text(candidate.doi):
        signals.append("doi_match")
        score += 0.45
    if (
        claimed.arxiv_id
        and candidate.arxiv_id
        and normalize_text(claimed.arxiv_id) == normalize_text(candidate.arxiv_id)
    ):
        signals.append("arxiv_id_match")
        score += 0.45
    if (
        claimed.checksum
        and candidate.checksum
        and claimed.checksum == candidate.checksum
    ):
        signals.append("checksum_match")
        score += 0.4

    if claimed.title and candidate.title and normalize_text(claimed.title) == normalize_text(candidate.title):
        signals.append("normalized_title_match")
        score += 0.25

    claimed_authors = {normalize_author(a) for a in claimed.authors if normalize_author(a)}
    candidate_authors = {normalize_author(a) for a in candidate.authors if normalize_author(a)}
    if claimed_authors and candidate_authors:
        overlap = claimed_authors & candidate_authors
        union = claimed_authors | candidate_authors
        if union:
            jaccard = len(overlap) / len(union)
            if jaccard > 0:
                signals.append(f"author_overlap({jaccard:.2f})")
                score += 0.15 * jaccard

    claimed_year = _publication_year(claimed.publication_date)
    candidate_year = _publication_year(candidate.publication_date)
    if claimed_year and candidate_year and claimed_year == candidate_year:
        signals.append("publication_year_match")
        score += 0.1

    if claimed.journal and candidate.journal and normalize_text(claimed.journal) == normalize_text(candidate.journal):
        signals.append("journal_match")
        score += 0.15

    return MatchEvidence(candidate_ref=candidate.source_ref, score=min(score, 1.0), signals=tuple(signals))


_CONFIRMED_THRESHOLD = 0.55
_STRONG_SIGNALS = frozenset({"doi_match", "arxiv_id_match", "checksum_match"})


@dataclass(frozen=True)
class ResolutionResult:
    state: str
    confidence: float
    reason: str
    matched_candidate_ref: Optional[str]
    evidence: tuple[str, ...]

    def claim_extraction_permitted(self) -> bool:
        return self.state in _CLAIM_EXTRACTION_PERMITTED_STATES


def resolve_source_identity(
    claimed: SourceIdentity,
    candidates: Iterable[SourceIdentity],
    *,
    operator_correction: Optional[SourceIdentity] = None,
    duplicate_of: Optional[str] = None,
    superseded_by: Optional[str] = None,
) -> ResolutionResult:
    """Resolve ``claimed`` against a set of independently obtained
    ``candidates`` (e.g. from a manual literature search), returning
    exactly one of the six ``RESOLUTION_STATES``. Never mutates
    ``claimed`` or any candidate -- purely a decision function; the
    caller is responsible for recording the result as an append-only
    event via :class:`SourceResolutionLog`.
    """
    if duplicate_of is not None:
        return ResolutionResult(
            state="duplicate",
            confidence=1.0,
            reason=f"identical to already-resolved source {duplicate_of!r} by operator/caller determination",
            matched_candidate_ref=duplicate_of,
            evidence=("duplicate_of_supplied_by_caller",),
        )

    if superseded_by is not None:
        return ResolutionResult(
            state="superseded",
            confidence=1.0,
            reason=f"superseded by a newer resolution {superseded_by!r}",
            matched_candidate_ref=superseded_by,
            evidence=("superseded_by_supplied_by_caller",),
        )

    if operator_correction is not None:
        # An operator correction is an authoritative human override of a
        # source claimed elsewhere to be wrong -- it is deliberately NOT
        # re-scored against the (disputed) original claim's own fields,
        # since the whole point is that those fields were wrong. It is
        # trusted only if it itself carries a verifiable identifier and
        # was not itself flagged as nonexistent.
        if operator_correction.exists is False:
            return ResolutionResult(
                state="disputed_identity",
                confidence=0.0,
                reason="operator-provided correction was itself independently confirmed NOT to exist",
                matched_candidate_ref=operator_correction.source_ref,
                evidence=("operator_correction_exists_false",),
            )
        if operator_correction.doi or operator_correction.arxiv_id:
            return ResolutionResult(
                state="confirmed_identity",
                confidence=0.95,
                reason=(
                    "operator-provided correction supplies a verifiable DOI/arXiv identity for this "
                    "source, overriding the original mismatched claim"
                ),
                matched_candidate_ref=operator_correction.source_ref,
                evidence=("operator_correction_doi_or_arxiv",),
            )
        return ResolutionResult(
            state="disputed_identity",
            confidence=0.1,
            reason="operator-provided correction lacks a verifiable DOI/arXiv identifier of its own",
            matched_candidate_ref=operator_correction.source_ref,
            evidence=(),
        )

    candidates = list(candidates)

    if not candidates:
        if claimed.exists is False:
            return ResolutionResult(
                state="disputed_identity",
                confidence=0.0,
                reason="claimed source was independently confirmed NOT to exist (exists=False), and no alternative candidate was supplied",
                matched_candidate_ref=None,
                evidence=("exists_false",),
            )
        return ResolutionResult(
            state="unavailable",
            confidence=0.0,
            reason="no independent candidate data was supplied to verify this claimed identity against",
            matched_candidate_ref=None,
            evidence=(),
        )

    scored = sorted(
        (score_candidate(claimed, c) for c in candidates), key=lambda m: (-m.score, m.candidate_ref)
    )
    best = scored[0]
    tied = [m for m in scored if m.score == best.score and best.score > 0]

    if best.score <= 0.0:
        return ResolutionResult(
            state="disputed_identity",
            confidence=0.0,
            reason="no candidate shares any identity signal with the claimed source",
            matched_candidate_ref=None,
            evidence=(),
        )

    if len(tied) > 1:
        return ResolutionResult(
            state="ambiguous_identity",
            confidence=best.score,
            reason=(
                f"{len(tied)} candidates tie at score {best.score:.2f} "
                f"({', '.join(m.candidate_ref for m in tied)}) -- cannot resolve to a single identity"
            ),
            matched_candidate_ref=None,
            evidence=best.signals,
        )

    has_strong_signal = any(signal in _STRONG_SIGNALS for signal in best.signals)
    if has_strong_signal:
        # A strong signal (DOI, arXiv id, or checksum match) is decisive
        # on its own -- it does not need to clear the combined-score
        # threshold, since a bare DOI match with no title/author overlap
        # supplied is still a confirmed identity (many operator exports
        # carry only a DOI).
        return ResolutionResult(
            state="confirmed_identity",
            confidence=max(best.score, _CONFIRMED_THRESHOLD),
            reason=f"best candidate {best.candidate_ref!r} matched with a strong identity signal ({', '.join(best.signals)})",
            matched_candidate_ref=best.candidate_ref,
            evidence=best.signals,
        )

    if best.signals:
        return ResolutionResult(
            state="disputed_identity",
            confidence=best.score,
            reason=(
                f"best candidate {best.candidate_ref!r} only matched on weak signals "
                f"({', '.join(best.signals)}) -- not sufficient to confirm identity"
            ),
            matched_candidate_ref=best.candidate_ref,
            evidence=best.signals,
        )

    return ResolutionResult(
        state="unavailable",
        confidence=0.0,
        reason="candidates were supplied but none shared any identity signal with the claim",
        matched_candidate_ref=None,
        evidence=(),
    )


@dataclass(frozen=True)
class ResolutionEvent:
    """One append-only record linking an original claimed source to a
    candidate and the resolution decision made about it (requirement 3).
    Never edited or removed once written -- a later re-resolution is a
    new event, not a replacement of this one."""

    event_id: str
    original_source_ref: str
    candidate_source_ref: Optional[str]
    state: str
    confidence: float
    reason: str
    resolver: str
    date: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "original_source_ref": self.original_source_ref,
            "candidate_source_ref": self.candidate_source_ref,
            "state": self.state,
            "confidence": self.confidence,
            "reason": self.reason,
            "resolver": self.resolver,
            "date": self.date,
            "evidence": list(self.evidence),
        }

    @staticmethod
    def from_dict(data: dict) -> "ResolutionEvent":
        data = dict(data)
        data["evidence"] = tuple(data.get("evidence") or ())
        return ResolutionEvent(**data)


def _event_id(original_source_ref: str, date: str, state: str) -> str:
    basis = f"{original_source_ref}:{date}:{state}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


class SourceResolutionLog:
    """Append-only JSONL log of :class:`ResolutionEvent` records.

    Independently implemented for this module -- does not import or
    reuse ``store.EvidenceRegistry`` (owned by PR #276, not to be
    modified or depended on here). A record is never rewritten in place:
    ``record_resolution`` always appends; the "current" resolution for a
    source is simply the most recent event for that ``original_source_ref``
    when replaying the log in order, and every prior event remains
    readable via ``history_for``.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def _append(self, event: ResolutionEvent) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def iter_events(self) -> Iterator[ResolutionEvent]:
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield ResolutionEvent.from_dict(json.loads(line))

    def record_resolution(
        self,
        *,
        original_source_ref: str,
        result: ResolutionResult,
        resolver: str = "operator",
        date: Optional[str] = None,
    ) -> ResolutionEvent:
        event = ResolutionEvent(
            event_id=_event_id(original_source_ref, date or _now_iso(), result.state),
            original_source_ref=original_source_ref,
            candidate_source_ref=result.matched_candidate_ref,
            state=result.state,
            confidence=result.confidence,
            reason=result.reason,
            resolver=resolver,
            date=date or _now_iso(),
            evidence=result.evidence,
        )
        self._append(event)
        return event

    def history_for(self, original_source_ref: str) -> list[ResolutionEvent]:
        return [e for e in self.iter_events() if e.original_source_ref == original_source_ref]

    def current_resolution(self, original_source_ref: str) -> Optional[ResolutionEvent]:
        history = self.history_for(original_source_ref)
        return history[-1] if history else None

    def all_current_resolutions(self) -> dict[str, ResolutionEvent]:
        current: dict[str, ResolutionEvent] = {}
        for event in self.iter_events():
            current[event.original_source_ref] = event
        return current


def claim_availability(state: str) -> str:
    """Requirement 5: claim extraction is only permitted once identity
    is sufficiently resolved. Returns ``"available"`` only for a state
    where extraction is permitted, ``"unavailable"`` for every other
    (including ambiguous/disputed) state -- never guesses."""
    if state not in RESOLUTION_STATES:
        raise ValueError(f"unrecognized resolution state: {state!r}")
    return "available" if state in _CLAIM_EXTRACTION_PERMITTED_STATES else "unavailable"
