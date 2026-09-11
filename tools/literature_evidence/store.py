"""Append-only, event-sourced literature evidence store.

Independently implemented for this package -- no import of
tools/awareness_studio_research/store.py (a separate, already-merged
sibling package with a similar append-only design; this branch must
have zero dependency on it). Source of truth is a JSONL event log:
every mutation is appended, never rewritten in place. The queryable
"current state" is a deterministic projection rebuilt by replaying the
log from position zero -- so re-adding an existing id raises
``ImmutabilityError`` rather than silently overwriting it, and a
disputed/superseded record's history is always recoverable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from .models import ClaimRecord, LiteratureRecord, SourceSnapshot

_ENTITY_TYPES = {
    "source": LiteratureRecord,
    "claim": ClaimRecord,
    "snapshot": SourceSnapshot,
}

_ID_FIELD_BY_ENTITY_TYPE = {
    "source": "source_id",
    "claim": "claim_id",
    "snapshot": "snapshot_id",
}


class ImmutabilityError(ValueError):
    """Raised when a caller attempts to silently rewrite an existing
    record instead of appending a new versioned event."""


class LiteratureEvidenceStore:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def _append(self, entity_type: str, entity_id: str, record: Any, *, reason: Optional[str] = None) -> None:
        event = {"entity_type": entity_type, "entity_id": entity_id, "record": record.to_dict(), "reason": reason}
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

    def _project(self, entity_type: str) -> dict[str, Any]:
        cls = _ENTITY_TYPES[entity_type]
        id_field = _ID_FIELD_BY_ENTITY_TYPE[entity_type]
        current: dict[str, Any] = {}
        for event in self.iter_events():
            if event["entity_type"] != entity_type:
                continue
            record = cls.from_dict(event["record"])
            current[getattr(record, id_field)] = record
        return current

    # -- sources --------------------------------------------------------------

    def list_sources(self) -> list[LiteratureRecord]:
        return sorted(self._project("source").values(), key=lambda s: s.source_id)

    def get_source(self, source_id: str) -> Optional[LiteratureRecord]:
        return self._project("source").get(source_id)

    def add_source(self, record: LiteratureRecord) -> LiteratureRecord:
        existing = self.get_source(record.source_id)
        if existing is not None:
            raise ImmutabilityError(
                f"source {record.source_id!r} already exists at version {existing.version}; "
                "use supersede_source()/dispute_source() to record a change, never re-add with the same id"
            )
        self._append("source", record.source_id, record)
        return record

    def _mutate_source(self, source_id: str, *, reason: Optional[str] = None, **overrides) -> LiteratureRecord:
        existing = self.get_source(source_id)
        if existing is None:
            raise KeyError(f"no such source: {source_id!r}")
        data = existing.to_dict()
        data.pop("schema", None)
        data.update(overrides)
        data["version"] = existing.version + 1
        new_record = LiteratureRecord.from_dict(data)
        self._append("source", source_id, new_record, reason=reason)
        return new_record

    def supersede_source(self, source_id: str, *, superseded_by: str, reason: Optional[str] = None) -> LiteratureRecord:
        return self._mutate_source(source_id, status="superseded", superseded_by=superseded_by, reason=reason)

    def dispute_source(self, source_id: str, *, reason: str) -> LiteratureRecord:
        return self._mutate_source(
            source_id, status="disputed", review_status="disputed", evidence_class="review_required", reason=reason,
        )

    def retract_source(self, source_id: str, *, reason: Optional[str] = None) -> LiteratureRecord:
        return self._mutate_source(source_id, status="retracted", reason=reason)

    # -- claims -----------------------------------------------------------------

    def list_claims(self) -> list[ClaimRecord]:
        return sorted(self._project("claim").values(), key=lambda c: c.claim_id)

    def get_claim(self, claim_id: str) -> Optional[ClaimRecord]:
        return self._project("claim").get(claim_id)

    def add_claim(self, claim: ClaimRecord) -> ClaimRecord:
        existing = self.get_claim(claim.claim_id)
        if existing is not None:
            raise ImmutabilityError(
                f"claim {claim.claim_id!r} already exists at version {existing.version}; "
                "append a new versioned event instead of re-adding"
            )
        self._append("claim", claim.claim_id, claim)
        return claim

    def mark_claim_review_required(self, claim_id: str) -> ClaimRecord:
        existing = self.get_claim(claim_id)
        if existing is None:
            raise KeyError(f"no such claim: {claim_id!r}")
        data = existing.to_dict()
        data["version"] = existing.version + 1
        data["claim_kind"] = "review_required"
        new_record = ClaimRecord.from_dict(data)
        self._append("claim", claim_id, new_record)
        return new_record

    # -- snapshots ----------------------------------------------------------------

    def list_snapshots(self) -> list[SourceSnapshot]:
        return sorted(self._project("snapshot").values(), key=lambda s: s.snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> Optional[SourceSnapshot]:
        return self._project("snapshot").get(snapshot_id)

    def add_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        existing = self.get_snapshot(snapshot.snapshot_id)
        if existing is not None:
            raise ImmutabilityError(f"snapshot {snapshot.snapshot_id!r} already exists; never re-add with the same id")
        self._append("snapshot", snapshot.snapshot_id, snapshot)
        return snapshot

    def snapshots_for_source(self, source_id: str) -> list[SourceSnapshot]:
        return [s for s in self.list_snapshots() if s.source_id == source_id]
