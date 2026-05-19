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


# O4 ontology tracking tests

def _write_manifest(root: str) -> None:
    import pathlib
    p = pathlib.Path(root) / "artifact_manifest.json"
    p.write_text(json.dumps({"artifact_count": 0, "artifacts": []}), encoding="utf-8")


def _write_ontology_eval(ont_root: str) -> None:
    import pathlib
    p = pathlib.Path(ont_root)
    p.mkdir(parents=True, exist_ok=True)
    (p / "ontology_claim_evaluation.json").write_text(json.dumps({
        "max_claim_scope": "engineering_runtime",
        "promotion_state": "engineering_validated",
        "ontology_claim_status": "ontology_quarantined",
        "claims": [],
        "blockers": ["run_mode_is_mock_e2e"],
        "safe_claim": "Ontology evaluation constrains claim scopes.",
    }), encoding="utf-8")
    (p / "ontology_promotion_decision.json").write_text(json.dumps({
        "ontology_promotion": False,
        "empirical_marker_promotion": False,
        "empirical_topology_promotion": False,
        "mechanism_promotion": False,
        "metaphysical_promotion": False,
    }), encoding="utf-8")
    (p / "bridge_claim_status.json").write_text(
        json.dumps({"bridge_statuses": []}), encoding="utf-8"
    )


def test_next_action_is_evaluate_ontology_claims_when_manifest_exists_but_no_ontology(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    _write_manifest(str(tmp_path))
    ont_root = str(tmp_path / "nonexistent_ontology")
    state = build_runtime_state("DS005620", str(tmp_path), ontology_root=ont_root)
    assert state.next_action == "evaluate_ontology_claims"


def test_next_action_proceeds_to_export_evidence_after_ontology_eval(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    _write_manifest(str(tmp_path))
    ont_root = str(tmp_path / "ont_eval")
    _write_ontology_eval(ont_root)
    state = build_runtime_state("DS005620", str(tmp_path), ontology_root=ont_root)
    assert state.next_action == "export_evidence_packet"


def test_runtime_state_includes_ontology_status_when_available(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    _write_manifest(str(tmp_path))
    ont_root = str(tmp_path / "ont_eval")
    _write_ontology_eval(ont_root)
    state = build_runtime_state("DS005620", str(tmp_path), ontology_root=ont_root)
    assert state.ontology_available is True
    assert state.ontology_max_claim_scope == "engineering_runtime"
    assert state.ontology_claim_status == "ontology_quarantined"
    assert state.ontology_next_action is None


def test_runtime_snapshot_includes_ontology_fields(tmp_path):
    _write_execution(str(tmp_path), {
        "benchmark_completed": True,
        "p12_succeeded": True,
        "p13_succeeded": True,
        "p11_succeeded": True,
        "mode": "mock_e2e",
        "stages": [],
    })
    _write_manifest(str(tmp_path))
    ont_root = str(tmp_path / "ont_eval")
    _write_ontology_eval(ont_root)
    state = build_runtime_state("DS005620", str(tmp_path), ontology_root=ont_root)
    snap = build_runtime_snapshot(state)
    assert "ontology_available" in snap.state
    assert "ontology_max_claim_scope" in snap.state
    assert "ontology_claim_status" in snap.state
    assert snap.state["ontology_available"] is True
