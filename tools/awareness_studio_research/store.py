"""Append-only, event-sourced evidence store.

Source of truth is a JSONL event log (never rewritten in place, never
truncated): every mutation -- creating a source, adding a claim,
downgrading/superseding/disputing a record -- is appended as one event.
The queryable "current state" (the dict-of-records views returned by
``list_sources()`` etc.) is a deterministic, rebuildable projection
produced by replaying the log from position zero. A record may be
downgraded, superseded, or disputed by appending a new event that
references its previous version -- it is never edited or deleted in
place, so the full history is always recoverable by replaying the log.

Stdlib-only: uses only ``json`` and ``pathlib``. No SQLite is used here
(JSONL was chosen as the single backing format for this package: append
is O(1) and the replay-to-projection model gives the immutability
guarantee directly, without a second schema to keep in sync).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from .models import (
    Correlate,
    DatasetLink,
    EvidenceUpdate,
    ExperimentLink,
    ExtractedClaim,
    HypothesisLink,
    LiteratureSource,
)

_ENTITY_TYPES = {
    "source": LiteratureSource,
    "claim": ExtractedClaim,
    "correlate": Correlate,
    "hypothesis_link": HypothesisLink,
    "dataset_link": DatasetLink,
    "experiment_link": ExperimentLink,
}

_ID_FIELD_BY_ENTITY_TYPE = {
    "source": "source_id",
    "claim": "claim_id",
    "correlate": "correlate_id",
    "hypothesis_link": "link_id",
    "dataset_link": "link_id",
    "experiment_link": "link_id",
}


class ImmutabilityError(ValueError):
    """Raised when a caller attempts to silently rewrite an existing
    record instead of appending a new versioned event."""


class EvidenceRegistry:
    """A registry bound to one JSONL log file. Every public mutation
    method appends exactly one event and returns the resulting record."""

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    # -- event log plumbing -------------------------------------------------

    def _append_event(self, event: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def iter_events(self) -> Iterator[dict]:
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def audit_history(self, entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> list[dict]:
        events = list(self.iter_events())
        if entity_type is not None:
            events = [e for e in events if e["entity_type"] == entity_type]
        if entity_id is not None:
            events = [e for e in events if e["entity_id"] == entity_id]
        return events

    # -- projection (rebuilt from the log every call -- always consistent) --

    def _project(self, entity_type: str) -> dict[str, Any]:
        cls = _ENTITY_TYPES[entity_type]
        id_field = _ID_FIELD_BY_ENTITY_TYPE[entity_type]
        current: dict[str, Any] = {}
        for event in self.iter_events():
            if event["entity_type"] != entity_type:
                continue
            record = cls(**event["record"])
            current[getattr(record, id_field)] = record
        return current

    # -- generic append helper ----------------------------------------------

    def _append_record_event(
        self, *, entity_type: str, entity_id: str, record: Any, update_type: str,
        previous_version: Optional[int], reason: str,
    ) -> EvidenceUpdate:
        event = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "record": record.to_dict(),
        }
        self._append_event(event)
        update = EvidenceUpdate(
            update_id=f"{entity_type}:{entity_id}:v{record.version if hasattr(record, 'version') else 1}",
            entity_type=entity_type,
            entity_id=entity_id,
            update_type=update_type,
            previous_version=previous_version,
            new_version=getattr(record, "version", 1),
            reason=reason,
        )
        self._append_event({"entity_type": "evidence_update", "entity_id": update.update_id, "record": update.to_dict()})
        return update

    # -- sources --------------------------------------------------------------

    def list_sources(self) -> list[LiteratureSource]:
        return sorted(self._project("source").values(), key=lambda s: s.source_id)

    def get_source(self, source_id: str) -> Optional[LiteratureSource]:
        return self._project("source").get(source_id)

    def add_source(self, source: LiteratureSource, *, reason: str = "initial ingestion") -> LiteratureSource:
        existing = self.get_source(source.source_id)
        if existing is not None:
            raise ImmutabilityError(
                f"source {source.source_id!r} already exists at version {existing.version}; "
                "use supersede_source()/dispute_source()/downgrade_source() to record a change, "
                "never re-add with the same id"
            )
        self._append_record_event(
            entity_type="source", entity_id=source.source_id, record=source,
            update_type="created", previous_version=None, reason=reason,
        )
        return source

    def _mutate_source(self, source_id: str, update_type: str, reason: str, **overrides) -> LiteratureSource:
        existing = self.get_source(source_id)
        if existing is None:
            raise KeyError(f"no such source: {source_id!r}")
        data = existing.to_dict()
        data.update(overrides)
        data["version"] = existing.version + 1
        new_record = LiteratureSource(**data)
        self._append_record_event(
            entity_type="source", entity_id=source_id, record=new_record,
            update_type=update_type, previous_version=existing.version, reason=reason,
        )
        return new_record

    def supersede_source(self, source_id: str, *, superseded_by: str, reason: str) -> LiteratureSource:
        return self._mutate_source(
            source_id, "superseded", reason, status="superseded", superseded_by=superseded_by
        )

    def dispute_source(self, source_id: str, *, reason: str, disagreements: tuple[str, ...]) -> LiteratureSource:
        existing = self.get_source(source_id)
        merged_disagreements = tuple(dict.fromkeys((*existing.disagreements, *disagreements))) if existing else disagreements
        return self._mutate_source(
            source_id, "disputed", reason,
            status="disputed", verification_status="disputed",
            evidence_tier="T4_disputed", disagreements=merged_disagreements,
        )

    def downgrade_source(self, source_id: str, *, new_evidence_tier: str, reason: str) -> LiteratureSource:
        return self._mutate_source(source_id, "downgraded", reason, evidence_tier=new_evidence_tier)

    # -- claims -----------------------------------------------------------------

    def list_claims(self) -> list[ExtractedClaim]:
        return sorted(self._project("claim").values(), key=lambda c: c.claim_id)

    def get_claim(self, claim_id: str) -> Optional[ExtractedClaim]:
        return self._project("claim").get(claim_id)

    def add_claim(self, claim: ExtractedClaim, *, reason: str = "initial extraction") -> ExtractedClaim:
        existing = self.get_claim(claim.claim_id)
        if existing is not None:
            raise ImmutabilityError(
                f"claim {claim.claim_id!r} already exists at version {existing.version}; "
                "append a new versioned event instead of re-adding"
            )
        self._append_record_event(
            entity_type="claim", entity_id=claim.claim_id, record=claim,
            update_type="created", previous_version=None, reason=reason,
        )
        return claim

    def dispute_claim(self, claim_id: str, *, reason: str, new_claim_status: str = "unsupported") -> ExtractedClaim:
        existing = self.get_claim(claim_id)
        if existing is None:
            raise KeyError(f"no such claim: {claim_id!r}")
        data = existing.to_dict()
        data["version"] = existing.version + 1
        data["status"] = "disputed"
        data["claim_status"] = new_claim_status
        new_record = ExtractedClaim(**data)
        self._append_record_event(
            entity_type="claim", entity_id=claim_id, record=new_record,
            update_type="disputed", previous_version=existing.version, reason=reason,
        )
        return new_record

    # -- correlates / links (append-only, single-version records) ---------------

    def add_correlate(self, correlate: Correlate, *, reason: str = "initial capture") -> Correlate:
        self._append_record_event(
            entity_type="correlate", entity_id=correlate.correlate_id, record=correlate,
            update_type="created", previous_version=None, reason=reason,
        )
        return correlate

    def list_correlates(self) -> list[Correlate]:
        return sorted(self._project("correlate").values(), key=lambda c: c.correlate_id)

    def add_hypothesis_link(self, link: HypothesisLink, *, reason: str = "initial link") -> HypothesisLink:
        self._append_record_event(
            entity_type="hypothesis_link", entity_id=link.link_id, record=link,
            update_type="created", previous_version=None, reason=reason,
        )
        return link

    def list_hypothesis_links(self) -> list[HypothesisLink]:
        return sorted(self._project("hypothesis_link").values(), key=lambda l: l.link_id)

    def add_dataset_link(self, link: DatasetLink, *, reason: str = "initial link") -> DatasetLink:
        self._append_record_event(
            entity_type="dataset_link", entity_id=link.link_id, record=link,
            update_type="created", previous_version=None, reason=reason,
        )
        return link

    def list_dataset_links(self) -> list[DatasetLink]:
        return sorted(self._project("dataset_link").values(), key=lambda l: l.link_id)

    def add_experiment_link(self, link: ExperimentLink, *, reason: str = "initial link") -> ExperimentLink:
        self._append_record_event(
            entity_type="experiment_link", entity_id=link.link_id, record=link,
            update_type="created", previous_version=None, reason=reason,
        )
        return link

    def list_experiment_links(self) -> list[ExperimentLink]:
        return sorted(self._project("experiment_link").values(), key=lambda l: l.link_id)
