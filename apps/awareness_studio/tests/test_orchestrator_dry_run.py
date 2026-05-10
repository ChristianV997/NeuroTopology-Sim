"""Tests for Orchestrator v0.1 dry-run pipeline — all offline, no LLM, no network."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
os.environ.setdefault("INDEX_BACKEND", "bm25")
os.environ.setdefault("TOOLS_ENABLED", "false")

from awareness_studio.orchestrator import Orchestrator, OrchestratorResult
from awareness_studio.orchestrator.event_model import (
    PIPELINE_STAGES,
    EventEnvelope,
    canonical_json,
)
from awareness_studio.orchestrator.event_log import EventLog
from awareness_studio.orchestrator.orchestrator import OrchestratorConfig

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── EventEnvelope ─────────────────────────────────────────────────────────────

def test_event_id_is_16_chars():
    e = EventEnvelope.make("run123", "ingest_inputs", "start", _now=_NOW)
    assert len(e.event_id) == 16


def test_event_id_stable():
    e1 = EventEnvelope.make("run123", "ingest_inputs", "start", _now=_NOW)
    e2 = EventEnvelope.make("run123", "ingest_inputs", "start", _now=_NOW)
    assert e1.event_id == e2.event_id


def test_event_id_differs_by_stage():
    e1 = EventEnvelope.make("run123", "ingest_inputs", "start", _now=_NOW)
    e2 = EventEnvelope.make("run123", "execute", "start", _now=_NOW)
    assert e1.event_id != e2.event_id


def test_event_roundtrip():
    e = EventEnvelope.make("r1", "validate", "ok", payload={"x": 1}, _now=_NOW)
    d = e.to_dict()
    e2 = EventEnvelope.from_dict(d)
    assert e2.event_id == e.event_id
    assert e2.stage == "validate"
    assert e2.payload == {"x": 1}


def test_event_to_jsonl_is_valid_json():
    e = EventEnvelope.make("r1", "validate", "ok", _now=_NOW)
    json.loads(e.to_jsonl())  # must not raise


def test_event_error_field_omitted_when_none():
    e = EventEnvelope.make("r1", "validate", "ok", _now=_NOW)
    assert "error" not in e.to_dict()


def test_event_error_field_present_when_set():
    e = EventEnvelope.make("r1", "validate", "error", error="boom", _now=_NOW)
    assert e.to_dict()["error"] == "boom"


def test_pipeline_stages_count():
    assert len(PIPELINE_STAGES) == 8


def test_canonical_json_sorted():
    d = {"b": 2, "a": 1}
    assert canonical_json(d).index('"a"') < canonical_json(d).index('"b"')


# ── EventLog ──────────────────────────────────────────────────────────────────

def test_event_log_append_creates_file(tmp_path):
    log = EventLog(tmp_path)
    log.append(EventEnvelope.make("r1", "ingest_inputs", "start", _now=_NOW))
    assert log.path.exists()


def test_event_log_load_all(tmp_path):
    log = EventLog(tmp_path)
    log.append(EventEnvelope.make("r1", "ingest_inputs", "start", _now=_NOW))
    log.append(EventEnvelope.make("r1", "ingest_inputs", "ok", _now=_NOW))
    events = log.load_all()
    assert len(events) == 2


def test_event_log_load_by_run_id(tmp_path):
    log = EventLog(tmp_path)
    log.append(EventEnvelope.make("r1", "ingest_inputs", "ok", _now=_NOW))
    log.append(EventEnvelope.make("r2", "ingest_inputs", "ok", _now=_NOW))
    r1 = log.load_by_run_id("r1")
    assert len(r1) == 1
    assert r1[0].run_id == "r1"


def test_event_log_list_recent(tmp_path):
    log = EventLog(tmp_path)
    for i in range(5):
        log.append(EventEnvelope.make("r1", f"stage{i}", "ok", _now=_NOW))
    recent = log.list_recent(n=3)
    assert len(recent) == 3


def test_event_log_empty_dir_returns_empty(tmp_path):
    log = EventLog(tmp_path / "subdir")
    assert log.load_all() == []


# ── Orchestrator dry run — output files ───────────────────────────────────────

@pytest.fixture
def dry_run_result(tmp_path) -> OrchestratorResult:
    orch = Orchestrator()
    return orch.run(
        config=OrchestratorConfig(dry_run=True, out_base_dir=tmp_path),
        _now=_NOW,
    )


def test_dry_run_returns_result(dry_run_result):
    assert isinstance(dry_run_result, OrchestratorResult)


def test_dry_run_run_id_is_16_chars(dry_run_result):
    assert len(dry_run_result.run_id) == 16


def test_dry_run_all_stages_completed(dry_run_result):
    assert dry_run_result.stages_completed == list(PIPELINE_STAGES)
    assert dry_run_result.stages_failed == []


def test_dry_run_out_dir_exists(dry_run_result):
    assert dry_run_result.out_dir.exists()


def test_dry_run_events_jsonl_exists(dry_run_result):
    assert (dry_run_result.out_dir / "events.jsonl").exists()


def test_dry_run_evidence_log_exists(dry_run_result):
    assert (dry_run_result.out_dir / "EvidenceLogDraft.md").exists()


def test_dry_run_report_exists(dry_run_result):
    assert (dry_run_result.out_dir / "Report.md").exists()


def test_dry_run_graph_update_exists(dry_run_result):
    assert (dry_run_result.out_dir / "GraphUpdate.json").exists()


def test_dry_run_ops_queue_item_exists(dry_run_result):
    assert (dry_run_result.out_dir / "OpsQueueItem.json").exists()


# ── Orchestrator dry run — event log content ──────────────────────────────────

def test_dry_run_event_log_covers_all_stages(dry_run_result):
    log = EventLog(dry_run_result.out_dir)
    events = log.load_all()
    stages_seen = {e.stage for e in events}
    for stage in PIPELINE_STAGES:
        assert stage in stages_seen, f"Missing stage in event log: {stage}"


def test_dry_run_event_log_has_start_and_ok_per_stage(dry_run_result):
    log = EventLog(dry_run_result.out_dir)
    events = log.load_all()
    by_stage: dict = {}
    for e in events:
        by_stage.setdefault(e.stage, set()).add(e.status)
    for stage in PIPELINE_STAGES:
        assert "start" in by_stage.get(stage, set()), f"No 'start' event for {stage}"
        assert "ok" in by_stage.get(stage, set()), f"No 'ok' event for {stage}"


# ── Orchestrator dry run — artifact content ───────────────────────────────────

def test_dry_run_events_jsonl_valid(dry_run_result):
    path = dry_run_result.out_dir / "events.jsonl"
    for line in path.read_text().splitlines():
        if line.strip():
            json.loads(line)  # must not raise


def test_dry_run_graph_update_json_valid(dry_run_result):
    data = json.loads((dry_run_result.out_dir / "GraphUpdate.json").read_text())
    assert "run_id" in data
    assert "nodes" in data


def test_dry_run_ops_queue_item_has_run_id(dry_run_result):
    data = json.loads((dry_run_result.out_dir / "OpsQueueItem.json").read_text())
    assert data["run_id"] == dry_run_result.run_id


def test_dry_run_ops_queue_item_dry_run_true(dry_run_result):
    data = json.loads((dry_run_result.out_dir / "OpsQueueItem.json").read_text())
    assert data["dry_run"] is True


def test_dry_run_report_contains_run_id(dry_run_result):
    content = (dry_run_result.out_dir / "Report.md").read_text()
    assert dry_run_result.run_id in content


def test_dry_run_evidence_contains_hypotheses(dry_run_result):
    content = (dry_run_result.out_dir / "EvidenceLogDraft.md").read_text()
    assert "h001" in content
    assert "h002" in content


# ── Determinism ────────────────────────────────────────────────────────────────

def test_dry_run_run_id_deterministic(tmp_path):
    cfg = OrchestratorConfig(dry_run=True, out_base_dir=tmp_path)
    r1 = Orchestrator().run(config=cfg, _now=_NOW)
    r2 = Orchestrator().run(config=cfg, _now=_NOW)
    assert r1.run_id == r2.run_id


def test_dry_run_different_seed_different_id(tmp_path):
    r1 = Orchestrator().run(
        config=OrchestratorConfig(dry_run=True, seed=1, out_base_dir=tmp_path), _now=_NOW
    )
    r2 = Orchestrator().run(
        config=OrchestratorConfig(dry_run=True, seed=2, out_base_dir=tmp_path), _now=_NOW
    )
    assert r1.run_id != r2.run_id


# ── No network / tool calls ────────────────────────────────────────────────────

def test_dry_run_no_tool_calls(tmp_path, monkeypatch):
    """Dry-run must not call any external tool or network."""
    import urllib.request
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: calls.append(a))
    Orchestrator().run(
        config=OrchestratorConfig(dry_run=True, out_base_dir=tmp_path), _now=_NOW
    )
    assert calls == [], "No network calls expected in dry-run"


def test_dry_run_result_to_dict(dry_run_result):
    d = dry_run_result.to_dict()
    assert "run_id" in d
    assert "stages_completed" in d
    assert "artifacts" in d


# ── Run cards ingestion ────────────────────────────────────────────────────────

def test_dry_run_with_run_cards_dir(tmp_path):
    """Orchestrator should ingest existing .run.json files from run_cards_dir."""
    run_cards_dir = tmp_path / "run_cards"
    run_cards_dir.mkdir()
    dummy = {
        "schema_version": "1", "run_id": "a" * 16,
        "created_at": "2025-01-15T12:00:00+00:00", "mode": "psi",
        "repo": "test", "git_commit": "abc", "argv": [],
        "input": {}, "metrics": {
            "I_mean": 0.5, "I_std": 0.1, "I_final": 0.4, "vort_mean": 1.0,
            "n_steps": 5.0, "Qz_mean": 0.0, "Qabs_mean": 0.0, "f_dress": 0.0,
        },
        "artifacts": {"md_path": "a.md", "json_path": "a.run.json"},
        "confounds": [], "guardrails": {}, "h8_falsifiers": [],
    }
    (run_cards_dir / "test.run.json").write_text(
        json.dumps(dummy), encoding="utf-8"
    )
    cfg = OrchestratorConfig(
        dry_run=True, run_cards_dir=run_cards_dir,
        out_base_dir=tmp_path / "out",
    )
    result = Orchestrator().run(config=cfg, _now=_NOW)
    assert result.stages_failed == []
    log = EventLog(result.out_dir)
    ingest_events = [e for e in log.load_all() if e.stage == "ingest_inputs" and e.status == "ok"]
    assert ingest_events[0].payload.get("run_cards_loaded") == 1
