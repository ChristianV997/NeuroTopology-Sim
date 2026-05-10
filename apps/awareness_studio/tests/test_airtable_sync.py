"""
Tests for AirtableSyncEngine — all offline, no Airtable calls.
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("AIRTABLE_ENABLED", "false")

from awareness_studio.integrations.airtable_sync import (
    RunCard,
    SyncSummary,
    _load_run_cards,
    airtable_status,
    make_run_card,
    save_run_card,
    sync_claims_from_evidence_log,
    sync_runs_from_run_cards,
)


# ── RunCard ───────────────────────────────────────────────────────────────────

def test_run_card_from_dict():
    data = {
        "run_id": "run-001",
        "mode": "EXPLAIN",
        "timestamp": "2026-05-04T12:00:00Z",
        "input_hash": "abcd1234",
    }
    card = RunCard.from_dict(data)
    assert card.run_id == "run-001"
    assert card.mode == "EXPLAIN"
    assert card.metrics == {}
    assert card.artifacts == []


def test_run_card_from_dict_with_extras():
    data = {
        "run_id": "run-002",
        "mode": "TEACH",
        "timestamp": "2026-05-04T00:00:00Z",
        "input_hash": "efgh5678",
        "metrics": {"retrieved": 8, "score": 0.9},
        "artifacts": ["output.txt"],
        "notes": "test run",
    }
    card = RunCard.from_dict(data)
    assert card.metrics["retrieved"] == 8
    assert card.notes == "test run"


def test_run_card_to_airtable_fields_required_keys():
    card = RunCard(
        run_id="run-001", mode="EXPLAIN",
        timestamp="2026-05-04T12:00:00Z", input_hash="abcd1234",
    )
    fields = card.to_airtable_fields()
    for key in ("run_id", "mode", "timestamp", "input_hash",
                "metrics_json", "artifacts_json", "summary"):
        assert key in fields, f"Missing key: {key}"


def test_run_card_summary_contains_mode():
    card = RunCard(
        run_id="abc123456789", mode="MATRIX",
        timestamp="2026-05-04T12:00:00Z", input_hash="x",
    )
    fields = card.to_airtable_fields()
    assert "MATRIX" in fields["summary"]


def test_make_run_card_hashes_question():
    card1 = make_run_card("r1", "EXPLAIN", "What is vedana?")
    card2 = make_run_card("r2", "EXPLAIN", "What is tanha?")
    assert card1.input_hash != card2.input_hash


def test_make_run_card_same_question_same_hash():
    card1 = make_run_card("r1", "EXPLAIN", "What is vedana?")
    card2 = make_run_card("r2", "EXPLAIN", "What is vedana?")
    assert card1.input_hash == card2.input_hash


# ── save_run_card ─────────────────────────────────────────────────────────────

def test_save_run_card_creates_file(tmp_path):
    card = make_run_card("save-test", "TEACH", "test question")
    path = save_run_card(card, base_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".json"
    data = json.loads(path.read_text())
    assert data["run_id"] == "save-test"


def test_save_run_card_updates_run_card_path(tmp_path):
    card = make_run_card("path-test", "EXPLAIN", "q")
    path = save_run_card(card, base_dir=tmp_path)
    data = json.loads(path.read_text())
    assert data["run_card_path"] != ""


# ── sync_runs_from_run_cards — dry run ────────────────────────────────────────

def test_sync_empty_dir_returns_zero_total(tmp_path):
    summary = sync_runs_from_run_cards(run_cards_dir=tmp_path)
    assert summary.total == 0
    assert summary.dry_run is True


def test_sync_dry_run_no_writes(tmp_path):
    card = make_run_card("dry-run-1", "EXPLAIN", "vedana?")
    save_run_card(card, base_dir=tmp_path)
    run_cards_dir = tmp_path / "run_cards"

    with patch("urllib.request.urlopen") as mock_http:
        summary = sync_runs_from_run_cards(run_cards_dir=run_cards_dir, allow_write=False)
        mock_http.assert_not_called()

    assert summary.dry_run is True
    assert summary.total == 1
    assert len(summary.planned) == 1


def test_sync_dry_run_planned_payload_structure(tmp_path):
    card = make_run_card("plan-test", "MATRIX", "tanha?")
    save_run_card(card, base_dir=tmp_path)
    run_cards_dir = tmp_path / "run_cards"

    summary = sync_runs_from_run_cards(run_cards_dir=run_cards_dir)
    plan = summary.planned[0]
    assert plan["action"] == "upsert"
    assert plan["table"] == "Runs"
    assert plan["key_field"] == "run_id"
    assert "fields" in plan


def test_sync_dry_run_when_airtable_enabled_false(tmp_path):
    import awareness_studio.config as cfg
    orig = cfg.AIRTABLE_ENABLED
    cfg.AIRTABLE_ENABLED = False
    card = make_run_card("check-1", "EXPLAIN", "q")
    save_run_card(card, base_dir=tmp_path)
    run_cards_dir = tmp_path / "run_cards"

    try:
        with patch("urllib.request.urlopen") as mock_http:
            summary = sync_runs_from_run_cards(
                run_cards_dir=run_cards_dir, allow_write=True
            )
            mock_http.assert_not_called()
        assert summary.dry_run is True
    finally:
        cfg.AIRTABLE_ENABLED = orig


# ── sync_runs_from_run_cards — live write ─────────────────────────────────────

def _fake_airtable_urlopen(req, timeout=15):
    method = req.get_method()
    if method == "GET":
        return _fake_response({"records": []})
    return _fake_response({"id": "recFAKE", "fields": {}})


def _fake_response(data):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


def test_sync_live_write_calls_airtable(tmp_path):
    import awareness_studio.config as cfg
    orig_enabled = cfg.AIRTABLE_ENABLED
    orig_key = cfg.AIRTABLE_API_KEY
    orig_base = cfg.AIRTABLE_BASE_ID
    cfg.AIRTABLE_ENABLED = True
    cfg.AIRTABLE_API_KEY = "test_key"
    cfg.AIRTABLE_BASE_ID = "appTEST"

    card = make_run_card("live-1", "EXPLAIN", "vedana?")
    save_run_card(card, base_dir=tmp_path)
    run_cards_dir = tmp_path / "run_cards"

    try:
        with patch("urllib.request.urlopen", side_effect=_fake_airtable_urlopen) as m:
            summary = sync_runs_from_run_cards(
                run_cards_dir=run_cards_dir, allow_write=True
            )
            assert m.called
        assert summary.dry_run is False
        assert summary.updated == 1
    finally:
        cfg.AIRTABLE_ENABLED = orig_enabled
        cfg.AIRTABLE_API_KEY = orig_key
        cfg.AIRTABLE_BASE_ID = orig_base


def test_sync_handles_malformed_run_card(tmp_path):
    run_cards_dir = tmp_path / "run_cards"
    run_cards_dir.mkdir()
    bad = run_cards_dir / "bad.run.json"
    bad.write_text("not valid json", encoding="utf-8")

    summary = sync_runs_from_run_cards(run_cards_dir=run_cards_dir)
    assert summary.total == 0  # skipped


# ── SyncSummary ───────────────────────────────────────────────────────────────

def test_sync_summary_to_dict():
    s = SyncSummary(total=3, created=1, updated=2, dry_run=False)
    d = s.to_dict()
    assert d["total"] == 3
    assert d["dry_run"] is False
    assert "errors" in d


# ── airtable_status ───────────────────────────────────────────────────────────

def test_airtable_status_returns_dict():
    status = airtable_status()
    assert isinstance(status, dict)
    assert "enabled" in status
    assert "api_key_set" in status
    assert "base_id_set" in status
    assert "tables" in status


def test_airtable_status_enabled_false_by_default():
    import awareness_studio.config as cfg
    orig = cfg.AIRTABLE_ENABLED
    cfg.AIRTABLE_ENABLED = False
    try:
        assert airtable_status()["enabled"] is False
    finally:
        cfg.AIRTABLE_ENABLED = orig


# ── sync_claims stub ──────────────────────────────────────────────────────────

def test_sync_claims_returns_dry_run_summary():
    summary = sync_claims_from_evidence_log()
    assert isinstance(summary, SyncSummary)
    assert summary.dry_run is True


# ── Web endpoints ─────────────────────────────────────────────────────────────

def test_airtable_status_endpoint():
    import os
    os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
    os.environ.setdefault("INDEX_BACKEND", "bm25")
    from fastapi.testclient import TestClient
    from awareness_studio.web.app import app
    client = TestClient(app)
    resp = client.get("/airtable/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data


def test_airtable_sync_runs_dry_run_endpoint():
    import os
    os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
    os.environ.setdefault("INDEX_BACKEND", "bm25")
    from fastapi.testclient import TestClient
    from awareness_studio.web.app import app
    client = TestClient(app)
    resp = client.post("/airtable/sync/runs?allow_write=false")
    assert resp.status_code == 200
    data = resp.json()
    assert "dry_run" in data
    assert data["dry_run"] is True


# ── RunRecord v1 format support ───────────────────────────────────────────────

def _run_record_v1_dict(run_id="abcdef1234567890"):
    return {
        "schema_version": "1",
        "run_id": run_id,
        "created_at": "2025-01-15T12:00:00+00:00",
        "mode": "psi",
        "repo": "ScienceR-Dsim",
        "git_commit": "abc1234",
        "argv": [],
        "input": {"N": 16, "n_steps": 5, "seed": 42},
        "metrics": {
            "I_mean": 0.5, "I_std": 0.1, "I_final": 0.45,
            "vort_mean": 1.2, "n_steps": 5.0,
            "Qz_mean": 0.0, "Qabs_mean": 0.0, "f_dress": 0.0,
        },
        "artifacts": {
            "md_path": "outputs/run_cards/run_20250115T120000_abcdef12.md",
            "json_path": "outputs/run_cards/run_20250115T120000_abcdef12.run.json",
        },
        "confounds": ["reproducibility_seed_fixed"],
        "guardrails": {"I_final_above_zero": True},
        "h8_falsifiers": [{"prediction": "I>0", "discriminator": "I<=0", "status": "PASS"}],
        "notes": "test run",
    }


def test_run_card_from_run_record_v1_parses():
    data = _run_record_v1_dict()
    card = RunCard.from_run_record_v1(data, path="/tmp/test.run.json")
    assert card.run_id == data["run_id"]
    assert card.mode == "psi"


def test_run_card_from_run_record_v1_timestamp_from_created_at():
    data = _run_record_v1_dict()
    card = RunCard.from_run_record_v1(data)
    assert card.timestamp == "2025-01-15T12:00:00+00:00"


def test_run_card_from_run_record_v1_artifacts_as_list():
    data = _run_record_v1_dict()
    card = RunCard.from_run_record_v1(data)
    assert isinstance(card.artifacts, list)
    assert any("md" in a for a in card.artifacts)


def test_run_card_from_run_record_v1_md_path_in_notes():
    data = _run_record_v1_dict()
    card = RunCard.from_run_record_v1(data)
    assert "md_path" in card.notes


def test_run_card_from_run_record_v1_input_hash_deterministic():
    data = _run_record_v1_dict()
    c1 = RunCard.from_run_record_v1(data)
    c2 = RunCard.from_run_record_v1(data)
    assert c1.input_hash == c2.input_hash


def test_run_card_from_run_record_v1_missing_field_raises():
    data = _run_record_v1_dict()
    del data["run_id"]
    with pytest.raises(ValueError, match="missing required keys"):
        RunCard.from_run_record_v1(data)


def test_load_run_cards_detects_v1_format(tmp_path):
    import json as _json
    path = tmp_path / "test.run.json"
    path.write_text(_json.dumps(_run_record_v1_dict()), encoding="utf-8")
    cards = _load_run_cards([path])
    assert len(cards) == 1
    assert cards[0].mode == "psi"


def test_load_run_cards_v1_airtable_fields_valid(tmp_path):
    import json as _json
    path = tmp_path / "test.run.json"
    path.write_text(_json.dumps(_run_record_v1_dict()), encoding="utf-8")
    cards = _load_run_cards([path])
    fields = cards[0].to_airtable_fields()
    assert "run_id" in fields
    assert "metrics_json" in fields


def test_sync_runs_discovers_v1_json(tmp_path):
    import json as _json
    path = tmp_path / "test.run.json"
    path.write_text(_json.dumps(_run_record_v1_dict()), encoding="utf-8")
    summary = sync_runs_from_run_cards(run_cards_dir=tmp_path, allow_write=False)
    assert summary.total == 1
    assert len(summary.planned) == 1
