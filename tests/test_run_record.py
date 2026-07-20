"""Tests for RunRecordV1 — all offline, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from runs.run_record import RunRecordV1, read_json, write_json

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

_REQUIRED_KEYS = (
    "schema_version", "run_id", "run_kind", "created_at",
    "elapsed_s", "spec_id", "claim_type", "layer",
    "data_mode", "dataset_id", "verdict",
    "metrics", "artifacts", "source", "steps",
)


# ── Construction ──────────────────────────────────────────────────────────────

def test_make_sets_run_id():
    r = RunRecordV1.make("abc123", "hypothesis", _now=_NOW)
    assert r.run_id == "abc123"


def test_make_sets_run_kind():
    r = RunRecordV1.make("abc123", "orchestrator", _now=_NOW)
    assert r.run_kind == "orchestrator"


def test_make_sets_created_at_from_now():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.created_at == _NOW.isoformat()


def test_make_defaults_metrics_empty():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.metrics == {}


def test_make_defaults_artifacts_empty():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.artifacts == {}


def test_make_accepts_optional_fields():
    r = RunRecordV1.make(
        "x", "hypothesis",
        elapsed_s=1.23,
        spec_id="HYP-001",
        claim_type="topology",
        layer="biophysical",
        data_mode="synthetic",
        dataset_id="ds001",
        verdict="PASS",
        metrics={"I_mean": 0.5},
        artifacts={"summary.json": "artifacts/summary.json"},
        source="governance/specs/HYP-001.yaml",
        _now=_NOW,
    )
    assert r.spec_id == "HYP-001"
    assert r.verdict == "PASS"
    assert r.metrics["I_mean"] == 0.5


# ── Serialization ─────────────────────────────────────────────────────────────

def test_to_dict_has_all_required_keys():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    d = r.to_dict()
    for key in _REQUIRED_KEYS:
        assert key in d, f"Missing key: {key}"


def test_to_dict_schema_version():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.to_dict()["schema_version"] == "0.1"


def test_from_dict_roundtrip():
    r = RunRecordV1.make(
        "run42", "hypothesis",
        spec_id="HYP-042", verdict="PASS",
        metrics={"I_mean": 0.7}, _now=_NOW,
    )
    d = r.to_dict()
    r2 = RunRecordV1.from_dict(d)
    assert r2.run_id == r.run_id
    assert r2.run_kind == r.run_kind
    assert r2.spec_id == r.spec_id
    assert r2.verdict == r.verdict
    assert r2.metrics == r.metrics


# ── steps (per-step telemetry sub-record, Phase 8) ────────────────────────────

def test_steps_defaults_to_none():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.steps is None


def test_steps_none_serializes_to_null_in_to_dict():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.to_dict()["steps"] is None


def test_steps_none_serializes_to_empty_list_in_to_sim_dict():
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    assert r.to_sim_dict()["steps"] == []


def test_steps_roundtrips_through_to_dict_from_dict():
    steps = [
        {"step": 0, "I": 0.5, "Q": 1.0, "Qabs": 3.0, "f_dress": 2.0, "energy": 10.0},
        {"step": 1, "I": 0.4, "Q": 1.0, "Qabs": 2.5, "f_dress": 1.5, "energy": 8.0},
    ]
    r = RunRecordV1(run_id="x", run_kind="psi", created_at=_NOW.isoformat(), steps=steps)
    d = r.to_dict()
    r2 = RunRecordV1.from_dict(d)
    assert r2.steps == steps


def test_steps_roundtrips_through_write_json_read_json(tmp_path):
    steps = [{"step": 0, "I": 0.1, "Q": 0.0, "Qabs": 1.0, "f_dress": 0.5, "energy": 2.0}]
    r = RunRecordV1(run_id="x", run_kind="psi", created_at=_NOW.isoformat(), steps=steps)
    out = tmp_path / "RunRecord.json"
    r.write_json(out)
    r2 = read_json(out)
    assert r2.steps == steps


def test_from_dict_backward_compatible_with_missing_steps_key():
    """A RunRecord.json written before Phase 8 (no "steps" key at all) must
    still load cleanly, with steps defaulting to None -- not KeyError."""
    d = RunRecordV1.make("x", "hypothesis", _now=_NOW).to_dict()
    del d["steps"]
    r = RunRecordV1.from_dict(d)
    assert r.steps is None


# ── write_json / read_json ────────────────────────────────────────────────────

def test_write_json_creates_file(tmp_path):
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    out = tmp_path / "RunRecord.json"
    r.write_json(out)
    assert out.exists()


def test_write_json_valid_json(tmp_path):
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    out = tmp_path / "RunRecord.json"
    r.write_json(out)
    data = json.loads(out.read_text())
    assert data["run_id"] == "x"


def test_write_json_module_function(tmp_path):
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    out = tmp_path / "RunRecord.json"
    write_json(r, out)
    assert out.exists()


def test_read_json_roundtrip(tmp_path):
    r = RunRecordV1.make(
        "roundtrip", "hypothesis",
        spec_id="HYP-RT", verdict="FAIL",
        metrics={"val": 42}, _now=_NOW,
    )
    out = tmp_path / "RunRecord.json"
    r.write_json(out)
    r2 = read_json(out)
    assert r2.run_id == "roundtrip"
    assert r2.spec_id == "HYP-RT"
    assert r2.verdict == "FAIL"
    assert r2.metrics["val"] == 42


def test_read_json_preserves_nullable_fields(tmp_path):
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    out = tmp_path / "RunRecord.json"
    r.write_json(out)
    r2 = read_json(out)
    assert r2.spec_id is None
    assert r2.elapsed_s is None
    assert r2.verdict is None


def test_write_json_creates_parent_dirs(tmp_path):
    r = RunRecordV1.make("x", "hypothesis", _now=_NOW)
    out = tmp_path / "nested" / "deep" / "RunRecord.json"
    r.write_json(out)
    assert out.exists()
