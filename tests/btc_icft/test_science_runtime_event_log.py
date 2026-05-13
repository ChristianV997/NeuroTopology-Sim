"""Tests for science runtime JSONL event log (P18.2)."""
from pathlib import Path

import pytest

from sciencer_d.btc_icft.runtime.event_log import (
    append_event,
    append_envelope,
    clear_events,
    scan_events,
    tail_events,
)
from sciencer_d.btc_icft.runtime.events import build_event


def test_append_and_tail(tmp_path):
    log = str(tmp_path / "events.jsonl")
    append_event(log, "test_event", {"x": 1}, source="test")
    append_event(log, "test_event", {"x": 2}, source="test")
    tailed = tail_events(log, n=5)
    assert len(tailed) == 2
    assert tailed[0]["payload"]["x"] == 1


def test_tail_n_limit(tmp_path):
    log = str(tmp_path / "events.jsonl")
    for i in range(10):
        append_event(log, "ev", {"i": i}, source="s")
    tailed = tail_events(log, n=3)
    assert len(tailed) == 3
    assert tailed[-1]["payload"]["i"] == 9


def test_scan_by_type(tmp_path):
    log = str(tmp_path / "events.jsonl")
    append_event(log, "type_a", {"k": "v1"}, source="s")
    append_event(log, "type_b", {"k": "v2"}, source="s")
    append_event(log, "type_a", {"k": "v3"}, source="s")
    results = scan_events(log, event_type="type_a")
    assert len(results) == 2


def test_scan_missing_log(tmp_path):
    log = str(tmp_path / "missing.jsonl")
    assert scan_events(log) == []


def test_clear_events(tmp_path):
    log = str(tmp_path / "events.jsonl")
    append_event(log, "ev", {}, source="s")
    clear_events(log)
    assert tail_events(log) == []


def test_append_envelope(tmp_path):
    log = str(tmp_path / "events.jsonl")
    env = build_event("stage_done", {"ok": True}, source="test_runner")
    append_envelope(log, env)
    tailed = tail_events(log)
    assert len(tailed) == 1
    assert tailed[0]["type"] == "stage_done"


def test_log_creates_parent_dirs(tmp_path):
    log = str(tmp_path / "deep" / "nested" / "events.jsonl")
    append_event(log, "ev", {}, source="s")
    assert Path(log).exists()
