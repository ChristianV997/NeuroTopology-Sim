"""Tests for science runtime state (P18.2)."""
import json
import os
import tempfile

import pytest

from sciencer_d.btc_icft.runtime.state import (
    build_runtime_snapshot,
    build_runtime_state,
    load_latest_execution,
)


def _write_execution(root: str, data: dict) -> None:
    import pathlib
    p = pathlib.Path(root) / "ds005620_real_benchmark_execution.json"
    p.write_text(json.dumps(data), encoding="utf-8")


def test_load_latest_execution_missing_returns_none(tmp_path):
    result = load_latest_execution(str(tmp_path))
    assert result is None


def test_load_latest_execution_present_returns_dict(tmp_path):
    _write_execution(str(tmp_path), {"benchmark_completed": True})
    result = load_latest_execution(str(tmp_path))
    assert result is not None
    assert result["benchmark_completed"] is True


def test_build_runtime_state_no_artifact_has_blocker(tmp_path):
    state = build_runtime_state("DS005620", str(tmp_path))
    assert not state.benchmark_completed
    assert "no_execution_artifact_found" in state.blockers
    assert state.next_action == "run_mock_e2e"


def test_build_runtime_state_completed_mock_e2e(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    state = build_runtime_state("DS005620", str(tmp_path))
    assert state.benchmark_completed
    assert state.mock_e2e_run
    assert state.p12_succeeded
    assert state.next_action == "build_artifact_manifest"


def test_build_runtime_snapshot_has_required_fields(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    state = build_runtime_state("DS005620", str(tmp_path))
    snap = build_runtime_snapshot(state)
    assert snap.snapshot_id
    assert snap.created_at
    assert "benchmark_completed" in snap.state
    assert "next_action" in snap.state
