"""Read-only reader for the research-cycle ledger's SQLite database.

The schema mirrored here (tables ``cycles``, ``records``, ``record_links``,
``events``) is documented in
``apps/awareness_studio/src/awareness_studio/research_cycle/ledger.py``
(Batch 1 / codex, read-only, not imported or modified). This module opens
the database in SQLite's own read-only URI mode (``mode=ro``) so it is
structurally impossible for this CLI to write to it, even by accident.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.research_cycle_cli.guardrails import (
    INVALID_DATABASE,
    INVALID_JSON,
    MISSING_SOURCE,
    Diagnostic,
)


@dataclass(frozen=True)
class LedgerSnapshot:
    ok: bool
    path: str | None
    error: str | None
    cycles: list[dict[str, Any]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _parse_json_field(raw: str | None, *, source: str, record_id: str | None, field_name: str, diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"{field_name} is not valid JSON: {exc}", record_id))
        return None
    if not isinstance(parsed, dict):
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"{field_name} must decode to a JSON object, got {type(parsed).__name__}", record_id))
        return None
    return parsed


def read_ledger(path: Path | None) -> LedgerSnapshot:
    """Read every row of every table. Never writes; never creates the
    file if it is absent (SQLite's ``mode=ro`` URI flag makes this the
    driver's own guarantee, not just this function's intent)."""
    if path is None:
        return LedgerSnapshot(ok=False, path=None, error="not_provided")
    if not path.is_file():
        return LedgerSnapshot(ok=False, path=str(path), error="file_not_found")

    source = str(path)
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return LedgerSnapshot(ok=False, path=source, error=f"sqlite_open_error: {exc}")

    diagnostics: list[Diagnostic] = []
    try:
        cycle_rows = connection.execute("SELECT cycle_id, parent_cycle_id, status, finalized, metadata_json, created_hash FROM cycles ORDER BY cycle_id").fetchall()
        record_rows = connection.execute("SELECT record_id, cycle_id, record_type, schema_version, payload_json, record_hash FROM records ORDER BY cycle_id, record_type, record_id").fetchall()
        link_rows = connection.execute("SELECT cycle_id, parent_id, child_id FROM record_links ORDER BY cycle_id, parent_id, child_id").fetchall()
        event_rows = connection.execute("SELECT cycle_id, event_id, sequence, event_type, producer, status, payload_json, previous_hash, event_hash, schema_version FROM events ORDER BY cycle_id, sequence").fetchall()
    except sqlite3.Error as exc:
        connection.close()
        return LedgerSnapshot(ok=False, path=source, error=f"sqlite_query_error: {exc}", diagnostics=[Diagnostic(INVALID_DATABASE, source, f"database does not match the expected ledger schema: {exc}", None)])
    finally:
        connection.close()

    cycles = []
    for row in cycle_rows:
        cycles.append(
            {
                "cycle_id": row["cycle_id"],
                "parent_cycle_id": row["parent_cycle_id"],
                "status": row["status"],
                "finalized": bool(row["finalized"]),
                "metadata": _parse_json_field(row["metadata_json"], source=source, record_id=row["cycle_id"], field_name="metadata_json", diagnostics=diagnostics),
            }
        )

    records = []
    for row in record_rows:
        records.append(
            {
                "record_id": row["record_id"],
                "cycle_id": row["cycle_id"],
                "record_type": row["record_type"],
                "schema_version": row["schema_version"],
                "payload": _parse_json_field(row["payload_json"], source=source, record_id=row["record_id"], field_name="payload_json", diagnostics=diagnostics),
                "record_hash": row["record_hash"],
            }
        )

    links = [{"cycle_id": row["cycle_id"], "parent_id": row["parent_id"], "child_id": row["child_id"]} for row in link_rows]

    events = []
    for row in event_rows:
        events.append(
            {
                "cycle_id": row["cycle_id"],
                "event_id": row["event_id"],
                "sequence": row["sequence"],
                "event_type": row["event_type"],
                "producer": row["producer"],
                "status": row["status"],
                "payload": _parse_json_field(row["payload_json"], source=source, record_id=row["event_id"], field_name="payload_json", diagnostics=diagnostics),
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
                "schema_version": row["schema_version"],
            }
        )

    return LedgerSnapshot(ok=True, path=source, error=None, cycles=cycles, records=records, links=links, events=events, diagnostics=diagnostics)
