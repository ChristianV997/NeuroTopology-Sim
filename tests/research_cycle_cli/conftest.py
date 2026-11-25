"""Shared fixtures for the research-cycle inspection CLI tests.

``build_ledger_db`` creates a real SQLite file matching the schema
mirrored in tools/research_cycle_cli/ledger_reader.py (which itself
mirrors the real, read-only Batch 1 ledger writer's schema) -- there is
no static JSON fixture for a database, so tests build one directly.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

_SCHEMA = """
CREATE TABLE cycles (
    cycle_id TEXT PRIMARY KEY,
    parent_cycle_id TEXT,
    status TEXT NOT NULL,
    finalized INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL,
    created_hash TEXT NOT NULL
);
CREATE TABLE records (
    record_id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    record_hash TEXT NOT NULL
);
CREATE TABLE record_links (
    cycle_id TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    PRIMARY KEY (cycle_id, parent_id, child_id)
);
CREATE TABLE events (
    cycle_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    producer TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    PRIMARY KEY (cycle_id, event_id)
);
"""


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@pytest.fixture
def build_ledger_db(tmp_path: Path):
    """Returns a function(cycles, records, links=(), events=()) -> Path
    that builds a fresh SQLite ledger file and returns its path.

    ``cycles``: list of dicts {cycle_id, parent_cycle_id, status, finalized, metadata}.
    ``records``: list of dicts {record_id, cycle_id, record_type, payload, schema_version}.
    ``links``: list of (cycle_id, parent_id, child_id) tuples.
    """
    counter = {"n": 0}

    def _make(cycles: list[dict[str, Any]], records: list[dict[str, Any]], links: list[tuple[str, str, str]] | None = None) -> Path:
        counter["n"] += 1
        db_path = tmp_path / f"ledger_{counter['n']}.sqlite3"
        connection = sqlite3.connect(db_path)
        connection.executescript(_SCHEMA)
        for cycle in cycles:
            metadata = cycle.get("metadata", {})
            connection.execute(
                "INSERT INTO cycles (cycle_id, parent_cycle_id, status, finalized, metadata_json, created_hash) VALUES (?,?,?,?,?,?)",
                (cycle["cycle_id"], cycle.get("parent_cycle_id"), cycle["status"], int(cycle.get("finalized", False)), json.dumps(metadata), _hash(metadata)),
            )
        for record in records:
            payload = record["payload"]
            connection.execute(
                "INSERT INTO records (record_id, cycle_id, record_type, schema_version, payload_json, record_hash) VALUES (?,?,?,?,?,?)",
                (record["record_id"], record["cycle_id"], record["record_type"], record.get("schema_version", "awareness-studio-research-cycle.v1"), record.get("payload_json_override", json.dumps(payload)), record.get("record_hash", _hash(payload))),
            )
        for cycle_id, parent_id, child_id in links or []:
            connection.execute("INSERT INTO record_links (cycle_id, parent_id, child_id) VALUES (?,?,?)", (cycle_id, parent_id, child_id))
        connection.commit()
        connection.close()
        return db_path

    return _make


@pytest.fixture
def write_json(tmp_path: Path):
    counter = {"n": 0}

    def _make(data: Any, *, name: str | None = None) -> Path:
        counter["n"] += 1
        path = tmp_path / (name or f"file_{counter['n']}.json")
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _make
