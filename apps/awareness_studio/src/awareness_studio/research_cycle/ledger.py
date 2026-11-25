"""Transactional, append-only SQLite storage for research-cycle records."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator, Mapping

from .models import (
    RECORD_TYPES,
    SCHEMA_VERSION,
    RecordMixin,
    ResearchCycleError,
    VALID_STATUSES,
    canonical_json,
    json_safe,
    record_from_dict,
    sha256_json,
    stable_id,
)


EVENT_SCHEMA_VERSION = "awareness-studio-research-cycle-event.v1"
EVENT_TYPES = frozenset(
    {
        "cycle_created", "cycle_finalized", "cycle_revision", "orchestrator_stage",
        "execution_outcome", "planning_artifact", "validation_outcome",
        "evidence_graph_update", "release_review", *RECORD_TYPES.keys(),
    }
)
_UNSET = object()


class LedgerError(ResearchCycleError):
    """Base class for persistent ledger failures."""


class ImmutableCycleError(LedgerError):
    """Raised when a finalized cycle or record is changed."""


class EventValidationError(LedgerError):
    """Raised when an event is unknown, malformed, or inconsistent."""


@dataclass(frozen=True)
class LedgerEvent:
    cycle_id: str
    event_id: str
    sequence: int
    event_type: str
    producer: str
    status: str
    payload: Mapping[str, Any]
    previous_hash: str | None
    event_hash: str
    schema_version: str = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "producer": self.producer,
            "status": self.status,
            "payload": json_safe(self.payload),
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "schema_version": self.schema_version,
        }


class ResearchCycleLedger:
    """A local append-only ledger with durable hash chaining.

    Each method opens a short-lived connection and uses ``BEGIN IMMEDIATE``;
    this protects sequence allocation across independent processes as well as
    threads. SQLite automatically rolls back an interrupted transaction.
    """

    def __init__(self, database_path: str | Path):
        path = Path(database_path)
        if str(path) == ":memory:":
            raise LedgerError("the research-cycle ledger requires a dedicated SQLite file")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = path
        self._thread_lock = threading.RLock()
        with self._connect() as connection:
            self._initialize(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cycles (
                cycle_id TEXT PRIMARY KEY,
                parent_cycle_id TEXT REFERENCES cycles(cycle_id),
                status TEXT NOT NULL,
                finalized INTEGER NOT NULL DEFAULT 0 CHECK (finalized IN (0,1)),
                metadata_json TEXT NOT NULL,
                created_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                cycle_id TEXT NOT NULL REFERENCES cycles(cycle_id),
                record_type TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                record_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS record_links (
                cycle_id TEXT NOT NULL REFERENCES cycles(cycle_id),
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                PRIMARY KEY (cycle_id, parent_id, child_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                cycle_id TEXT NOT NULL REFERENCES cycles(cycle_id),
                event_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                producer TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                PRIMARY KEY (cycle_id, event_id),
                UNIQUE (cycle_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS idx_records_cycle ON records(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_events_cycle_sequence ON events(cycle_id, sequence);
            """
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._thread_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def _ensure_status(status: str) -> str:
        if not isinstance(status, str) or status not in VALID_STATUSES:
            raise EventValidationError(f"unknown ledger status: {status!r}")
        return status

    @staticmethod
    def _ensure_event(cycle_id: str, event_type: str, producer: str, status: str, payload: Mapping[str, Any]) -> None:
        if not isinstance(cycle_id, str) or not cycle_id:
            raise EventValidationError("event cycle_id is required")
        if event_type not in EVENT_TYPES:
            raise EventValidationError(f"unknown event_type: {event_type!r}")
        if not isinstance(producer, str) or not producer.strip():
            raise EventValidationError("event producer is required")
        ResearchCycleLedger._ensure_status(status)
        if not isinstance(payload, Mapping):
            raise EventValidationError("event payload must be an object")
        # canonical_json has allow_nan=False and rejects unsupported values.
        canonical_json(payload)

    @staticmethod
    def _event_id(cycle_id: str, event_type: str, producer: str, status: str, payload: Mapping[str, Any]) -> str:
        return stable_id("event", {"cycle_id": cycle_id, "event_type": event_type, "producer": producer, "status": status, "payload": payload, "schema_version": EVENT_SCHEMA_VERSION})

    @staticmethod
    def _event_hash(event_id: str, cycle_id: str, sequence: int, event_type: str, producer: str, status: str, payload: Mapping[str, Any], previous_hash: str | None) -> str:
        return sha256_json({"cycle_id": cycle_id, "event_id": event_id, "sequence": sequence, "event_type": event_type, "producer": producer, "status": status, "payload": payload, "previous_hash": previous_hash, "schema_version": EVENT_SCHEMA_VERSION})

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> LedgerEvent:
        return LedgerEvent(
            cycle_id=row["cycle_id"], event_id=row["event_id"], sequence=row["sequence"],
            event_type=row["event_type"], producer=row["producer"], status=row["status"],
            payload=json.loads(row["payload_json"]), previous_hash=row["previous_hash"],
            event_hash=row["event_hash"], schema_version=row["schema_version"],
        )

    @staticmethod
    def _reference_fields(record: RecordMixin) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Return typed record-reference fields that must resolve in the cycle lineage."""
        field_names = {
            "evidence_record": ("source_snapshot_ids",),
            "claim": ("evidence_ids",),
            "hypothesis": ("claim_ids",),
            "experiment_spec": ("hypothesis_ids",),
            "run_record": ("experiment_id",),
            "artifact_manifest": ("run_record_id",),
            "validation_report": ("artifact_manifest_ids", "run_record_id"),
            "theory_revision": ("hypothesis_ids", "validation_report_ids"),
        }
        references: list[tuple[str, tuple[str, ...]]] = []
        for field_name in field_names.get(record.record_type, ()):
            value = getattr(record, field_name)
            references.append((field_name, (value,) if isinstance(value, str) else tuple(value)))
        return tuple(references)

    @staticmethod
    def _cycle_is_in_lineage(connection: sqlite3.Connection, cycle_id: str, candidate: str) -> bool:
        """Return whether candidate is this cycle or one of its ancestors."""
        current = cycle_id
        seen: set[str] = set()
        while current and current not in seen:
            if current == candidate:
                return True
            seen.add(current)
            row = connection.execute("SELECT parent_cycle_id FROM cycles WHERE cycle_id = ?", (current,)).fetchone()
            if row is None:
                return False
            current = row["parent_cycle_id"]
        return False

    @classmethod
    def _ensure_record_reference(
        cls,
        connection: sqlite3.Connection,
        cycle_id: str,
        referenced_id: str,
        *,
        relation: str,
    ) -> None:
        row = connection.execute("SELECT cycle_id FROM records WHERE record_id = ?", (referenced_id,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown {relation} record: {referenced_id}")
        if not cls._cycle_is_in_lineage(connection, cycle_id, row["cycle_id"]):
            raise LedgerError(
                f"{relation} record {referenced_id} belongs to unrelated cycle {row['cycle_id']}; "
                f"target cycle is {cycle_id}"
            )

    @classmethod
    def _ensure_record_references(cls, connection: sqlite3.Connection, cycle_id: str, record: RecordMixin) -> None:
        for parent_id in record.parent_ids:
            cls._ensure_record_reference(connection, cycle_id, parent_id, relation="parent")
        for child_id in record.child_ids:
            cls._ensure_record_reference(connection, cycle_id, child_id, relation="child")
        for field_name, references in cls._reference_fields(record):
            for referenced_id in references:
                cls._ensure_record_reference(connection, cycle_id, referenced_id, relation=field_name)

    @classmethod
    def _ensure_link_integrity(cls, connection: sqlite3.Connection, cycle_id: str) -> None:
        """Validate link rows and ensure they are represented by typed records."""
        expected: set[tuple[str, str]] = set()
        for row in connection.execute("SELECT payload_json FROM records WHERE cycle_id = ?", (cycle_id,)):
            record = record_from_dict(json.loads(row["payload_json"]))
            for parent_id in record.parent_ids:
                expected.add((parent_id, record.record_id))
            for child_id in record.child_ids:
                expected.add((record.record_id, child_id))
            cls._ensure_record_references(connection, cycle_id, record)
        actual: set[tuple[str, str]] = set()
        for row in connection.execute("SELECT parent_id, child_id FROM record_links WHERE cycle_id = ?", (cycle_id,)):
            cls._ensure_record_reference(connection, cycle_id, row["parent_id"], relation="link parent")
            cls._ensure_record_reference(connection, cycle_id, row["child_id"], relation="link child")
            actual.add((row["parent_id"], row["child_id"]))
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise LedgerError(f"record link index mismatch for {cycle_id}: missing={missing}, extra={extra}")

    def _append_event_connection(self, connection: sqlite3.Connection, *, cycle_id: str, event_type: str, producer: str, status: str, payload: Mapping[str, Any], event_id: str | None = None) -> LedgerEvent:
        self._ensure_event(cycle_id, event_type, producer, status, payload)
        cycle = connection.execute("SELECT finalized FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
        if cycle is None:
            raise LedgerError(f"unknown cycle: {cycle_id}")
        if cycle["finalized"] and event_type != "cycle_finalized":
            raise ImmutableCycleError(f"cycle {cycle_id} is finalized")
        canonical_payload = json_safe(payload)
        derived_id = self._event_id(cycle_id, event_type, producer, status, canonical_payload)
        selected_id = event_id or derived_id
        existing = connection.execute("SELECT * FROM events WHERE cycle_id = ? AND event_id = ?", (cycle_id, selected_id)).fetchone()
        if existing is not None:
            old = self._row_to_event(existing)
            if old.payload == canonical_payload and old.event_type == event_type and old.status == status and old.producer == producer:
                return old
            raise ImmutableCycleError(f"event_id {selected_id} already exists with different content")
        if event_id is not None and event_id != derived_id:
            raise EventValidationError("event_id must be the stable hash of event content")
        last = connection.execute("SELECT * FROM events WHERE cycle_id = ? ORDER BY sequence DESC LIMIT 1", (cycle_id,)).fetchone()
        sequence = 1 if last is None else int(last["sequence"]) + 1
        previous_hash = None if last is None else last["event_hash"]
        event_hash = self._event_hash(selected_id, cycle_id, sequence, event_type, producer, status, canonical_payload, previous_hash)
        connection.execute(
            "INSERT INTO events (cycle_id,event_id,sequence,event_type,producer,status,payload_json,previous_hash,event_hash,schema_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cycle_id, selected_id, sequence, event_type, producer, status, canonical_json(canonical_payload), previous_hash, event_hash, EVENT_SCHEMA_VERSION),
        )
        row = connection.execute("SELECT * FROM events WHERE cycle_id = ? AND event_id = ?", (cycle_id, selected_id)).fetchone()
        return self._row_to_event(row)

    def create_cycle(self, cycle_id: str | None = None, *, parent_cycle_id: str | None = None, metadata: Mapping[str, Any] | None = None, status: str = "IN_PROGRESS", producer: str = "awareness_studio") -> str:
        metadata = {} if metadata is None else dict(metadata)
        self._ensure_status(status)
        selected_id = cycle_id or stable_id("cycle", {"parent_cycle_id": parent_cycle_id, "metadata": metadata})
        if not isinstance(selected_id, str) or not selected_id:
            raise LedgerError("cycle_id is required")
        if any(character in selected_id for character in ("/", "\\", " ")):
            raise LedgerError("cycle_id must be a stable path-free identifier")
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM cycles WHERE cycle_id = ?", (selected_id,)).fetchone()
            if existing is not None:
                if existing["parent_cycle_id"] == parent_cycle_id and existing["status"] == status and json.loads(existing["metadata_json"]) == json_safe(metadata):
                    return selected_id
                raise ImmutableCycleError(f"cycle {selected_id} already exists with different content")
            if parent_cycle_id is not None and connection.execute("SELECT 1 FROM cycles WHERE cycle_id = ?", (parent_cycle_id,)).fetchone() is None:
                raise LedgerError(f"unknown parent cycle: {parent_cycle_id}")
            created_hash = sha256_json({"cycle_id": selected_id, "parent_cycle_id": parent_cycle_id, "metadata": metadata})
            connection.execute("INSERT INTO cycles (cycle_id,parent_cycle_id,status,finalized,metadata_json,created_hash) VALUES (?,?,?,?,?,?)", (selected_id, parent_cycle_id, status, 0, canonical_json(metadata), created_hash))
            self._append_event_connection(connection, cycle_id=selected_id, event_type="cycle_created", producer=producer, status=status, payload={"cycle_id": selected_id, "parent_cycle_id": parent_cycle_id, "metadata": metadata})
        return selected_id

    def create_child_cycle(self, parent_cycle_id: str, cycle_id: str | None = None, *, revision_reason: str, metadata: Mapping[str, Any] | None = None, producer: str = "awareness_studio") -> str:
        revision = {"revision_reason": revision_reason, **({} if metadata is None else dict(metadata))}
        child_id = self.create_cycle(cycle_id, parent_cycle_id=parent_cycle_id, metadata=revision, producer=producer)
        with self._transaction() as connection:
            self._append_event_connection(connection, cycle_id=child_id, event_type="cycle_revision", producer=producer, status="REVIEW_REQUIRED", payload={"parent_cycle_id": parent_cycle_id, "revision_reason": revision_reason})
        return child_id

    def append_event(self, cycle_id: str, event_type: str, *, producer: str, status: str, payload: Mapping[str, Any], event_id: str | None = None) -> LedgerEvent:
        with self._transaction() as connection:
            return self._append_event_connection(connection, cycle_id=cycle_id, event_type=event_type, producer=producer, status=status, payload=payload, event_id=event_id)

    def append_record(self, cycle_id: str, record: RecordMixin, *, producer: str = "awareness_studio") -> RecordMixin:
        if not isinstance(record, RecordMixin) or record.cycle_id != cycle_id:
            raise LedgerError("record must be a typed record for the target cycle")
        payload = record.to_dict()
        record_id = record.record_id
        record_hash = record.checksum
        with self._transaction() as connection:
            cycle = connection.execute("SELECT finalized FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise LedgerError(f"unknown cycle: {cycle_id}")
            existing = connection.execute("SELECT * FROM records WHERE record_id = ?", (record_id,)).fetchone()
            if existing is not None:
                if existing["cycle_id"] == cycle_id and existing["record_hash"] == record_hash and existing["payload_json"] == canonical_json(payload):
                    return record
                if existing["cycle_id"] != cycle_id:
                    raise ImmutableCycleError(f"record {record_id} already exists in cycle {existing['cycle_id']}")
                raise ImmutableCycleError(f"record {record_id} already exists with different content")
            if cycle["finalized"]:
                raise ImmutableCycleError(f"cycle {cycle_id} is finalized")
            self._ensure_record_references(connection, cycle_id, record)
            connection.execute("INSERT INTO records (record_id,cycle_id,record_type,schema_version,payload_json,record_hash) VALUES (?,?,?,?,?,?)", (record_id, cycle_id, record.record_type, SCHEMA_VERSION, canonical_json(payload), record_hash))
            for parent_id in record.parent_ids:
                connection.execute("INSERT OR IGNORE INTO record_links (cycle_id,parent_id,child_id) VALUES (?,?,?)", (cycle_id, parent_id, record_id))
            for child_id in record.child_ids:
                connection.execute("INSERT OR IGNORE INTO record_links (cycle_id,parent_id,child_id) VALUES (?,?,?)", (cycle_id, record_id, child_id))
            self._append_event_connection(connection, cycle_id=cycle_id, event_type=record.record_type, producer=producer, status=record.status, payload=payload)
        return record

    def finalize_cycle(self, cycle_id: str, *, producer: str = "awareness_studio") -> None:
        with self._transaction() as connection:
            row = connection.execute("SELECT finalized FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
            if row is None:
                raise LedgerError(f"unknown cycle: {cycle_id}")
            if row["finalized"]:
                return
            self._append_event_connection(connection, cycle_id=cycle_id, event_type="cycle_finalized", producer=producer, status="FINALIZED", payload={"cycle_id": cycle_id})
            connection.execute("UPDATE cycles SET status = 'FINALIZED', finalized = 1 WHERE cycle_id = ?", (cycle_id,))

    def events(self, cycle_id: str) -> list[LedgerEvent]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events WHERE cycle_id = ? ORDER BY sequence", (cycle_id,)).fetchall()
            return [self._row_to_event(row) for row in rows]

    def records(self, cycle_id: str) -> list[RecordMixin]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM records WHERE cycle_id = ? ORDER BY record_id", (cycle_id,)).fetchall()
            return [record_from_dict(json.loads(row["payload_json"])) for row in rows]

    def recover(self, cycle_id: str | None = None) -> bool:
        """Check integrity, JSON payloads, sequence monotonicity, and hash chains."""
        with self._connect() as connection:
            check = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise LedgerError(f"SQLite integrity check failed: {check}")
            if cycle_id is not None and connection.execute("SELECT 1 FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone() is None:
                raise LedgerError(f"unknown cycle: {cycle_id}")
            cycles = [cycle_id] if cycle_id else [row[0] for row in connection.execute("SELECT cycle_id FROM cycles ORDER BY cycle_id")]
            for current in cycles:
                rows = connection.execute("SELECT * FROM events WHERE cycle_id = ? ORDER BY sequence", (current,)).fetchall()
                previous = None
                for expected_sequence, row in enumerate(rows, 1):
                    event = self._row_to_event(row)
                    if event.sequence != expected_sequence or event.previous_hash != previous:
                        raise LedgerError(f"event sequence/hash chain broken for cycle {current}")
                    if self._event_hash(event.event_id, event.cycle_id, event.sequence, event.event_type, event.producer, event.status, event.payload, event.previous_hash) != event.event_hash:
                        raise LedgerError(f"event hash broken for {event.event_id}")
                    previous = event.event_hash
                for row in connection.execute("SELECT payload_json,record_hash FROM records WHERE cycle_id = ?", (current,)):
                    record = record_from_dict(json.loads(row[0]))
                    if record.cycle_id != current:
                        raise LedgerError(f"record {record.record_id} has cycle_id {record.cycle_id}, expected {current}")
                    if record.checksum != row[1]:
                        raise LedgerError(f"record hash broken for {record.record_id}")
                self._ensure_link_integrity(connection, current)
        return True

    def export_json(self, cycle_id: str, path: str | Path | None = None) -> str:
        with self._connect() as connection:
            cycle = connection.execute("SELECT * FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise LedgerError(f"unknown cycle: {cycle_id}")
            body: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "cycle": {"cycle_id": cycle["cycle_id"], "parent_cycle_id": cycle["parent_cycle_id"], "status": cycle["status"], "finalized": bool(cycle["finalized"]), "metadata": json.loads(cycle["metadata_json"]), "created_hash": cycle["created_hash"]},
                "records": [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM records WHERE cycle_id = ? ORDER BY record_id", (cycle_id,))],
                "events": [self._row_to_event(row).to_dict() for row in connection.execute("SELECT * FROM events WHERE cycle_id = ? ORDER BY sequence", (cycle_id,))],
                "links": [{"parent_id": row[0], "child_id": row[1]} for row in connection.execute("SELECT parent_id,child_id FROM record_links WHERE cycle_id = ? ORDER BY parent_id,child_id", (cycle_id,))],
            }
            body["export_checksum"] = sha256_json(body)
            output = canonical_json(body)
        if path is not None:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(output + "\n", encoding="utf-8")
        return output

    def export_jsonl(self, cycle_id: str, path: str | Path | None = None) -> str:
        lines = [canonical_json(event.to_dict()) for event in self.events(cycle_id)]
        output = "\n".join(lines) + ("\n" if lines else "")
        if path is not None:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(output, encoding="utf-8")
        return output

    def close(self) -> None:
        """Compatibility no-op; operations use short-lived connections."""

    def __enter__(self) -> "ResearchCycleLedger":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


__all__ = ["EVENT_SCHEMA_VERSION", "EVENT_TYPES", "EventValidationError", "ImmutableCycleError", "LedgerError", "LedgerEvent", "ResearchCycleLedger"]
