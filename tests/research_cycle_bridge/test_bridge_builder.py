"""Integration tests for Research Cycle Bridge builder and validator."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.research_cycle_bridge.builder import build_research_cycle_bridge
from tools.research_cycle_bridge.models import (
    BRIDGE_SCHEMA_VERSION,
    ResearchCycleBridgeRecord,
    verify_bridge_checksum,
)
from tools.research_cycle_bridge.validator import validate_bridge_record


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _create_run_dir(tmp_path: Path, *, name: str = "run_001", synthetic: bool = False, partial: bool = False, failed: bool = False) -> Path:
    run = tmp_path / name
    _write_json(
        run / "RunRecord.json",
        {
            "run_id": f"run_{name}",
            "run_kind": "topology_sim",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "local_synthesizer",
            "dataset_id": "ds005620",
            "data_mode": "synthetic" if synthetic else "empirical",
            "synthetic": synthetic,
            "git_commit": "d4dc5fc0647ba06e9708683ad6c19c445d5d778d",
            "config": {"iterations": 50, "dt": 0.01},
            "input": {"channels": 16},
        },
    )
    _write_json(run / "summary.json", {"status": "complete", "loss": 0.042, "runtime_s": 1.25})
    _write_json(run / "metrics.json", {"accuracy": 0.95, "null_metric": None})
    _write_json(run / "validation_report.json", {"validation_id": f"val_{name}", "status": "complete", "checks_passed": True})

    if partial:
        _write_json(run / "partial_output.json", {"status": "interrupted", "resumable": True})
    if failed:
        (run / "failed.marker").write_text("simulation divergence error", encoding="utf-8")

    return run


def test_complete_run_bridge_success(tmp_path: Path) -> None:
    """Test full happy path linking complete simulation run to research cycle bridge."""
    run_dir = _create_run_dir(tmp_path, name="happy_run")
    bridge = build_research_cycle_bridge(run_dir, cycle_id="rc-cycle-happy")

    assert bridge.schema_version == BRIDGE_SCHEMA_VERSION
    assert bridge.status == "COMPLETE"
    assert bridge.cycle_id == "rc-cycle-happy"
    assert bridge.dataset_id == "ds005620"
    assert bridge.empirical is True
    assert bridge.synthetic is False
    assert bridge.evidence_class == "empirical_dataset"

    # Evidence graph validation
    egraph = bridge.evidence_graph
    assert egraph is not None
    assert len(egraph["nodes"]) == 5
    assert len(egraph["edges"]) == 4

    # Release evidence evaluation
    rel_ev = bridge.release_evidence
    assert rel_ev is not None
    assert "decision" in rel_ev

    # Validation
    errors = validate_bridge_record(bridge)
    assert len(errors) == 0

    # Checksum
    assert verify_bridge_checksum(bridge.to_dict()) is True


def test_partial_run_marks_partial_status(tmp_path: Path) -> None:
    """Partial or interrupted runs must be marked PARTIAL and fail closed."""
    run_dir = _create_run_dir(tmp_path, name="partial_run", partial=True)
    bridge = build_research_cycle_bridge(run_dir)

    assert bridge.status == "PARTIAL"
    assert bridge.evidence_graph["partial"] is True
    assert len(bridge.diagnostics["partial"]) > 0


def test_failed_run_marks_failed_status(tmp_path: Path) -> None:
    """Failed runs must be marked FAILED and fail closed."""
    run_dir = _create_run_dir(tmp_path, name="failed_run", failed=True)
    bridge = build_research_cycle_bridge(run_dir)

    assert bridge.status == "FAILED"
    assert len(bridge.diagnostics["failed"]) > 0


def test_synthetic_run_guardrails(tmp_path: Path) -> None:
    """Synthetic runs must be flagged, assigned synthetic_demo_only, and never receive PASS."""
    run_dir = _create_run_dir(tmp_path, name="synth_run", synthetic=True)
    bridge = build_research_cycle_bridge(run_dir)

    assert bridge.synthetic is True
    assert bridge.empirical is False
    assert bridge.evidence_class in ("synthetic_simulation", "synthetic_demo_only")
    assert bridge.scientific_verdict != "PASS"

    errors = validate_bridge_record(bridge)
    assert len(errors) == 0


def test_null_metrics_preserved(tmp_path: Path) -> None:
    """Missing metrics in metrics.json must remain None (null) and not zero-filled."""
    run_dir = _create_run_dir(tmp_path, name="null_metrics_run")
    bridge = build_research_cycle_bridge(run_dir)

    metrics = bridge.simulation_run["metrics"]
    assert "null_metric" in metrics
    assert metrics["null_metric"] is None  # preserved as null


def test_missing_provenance_rejected(tmp_path: Path) -> None:
    """Missing or unauthenticated provenance must be caught by validator."""
    run_dir = tmp_path / "bad_prov_run"
    _write_json(
        run_dir / "RunRecord.json",
        {
            "run_id": "",  # empty string
            "created_at": "unknown",  # prohibited placeholder
            "source": "",
        },
    )
    _write_json(run_dir / "summary.json", {"status": "complete"})
    bridge = build_research_cycle_bridge(run_dir)

    errors = validate_bridge_record(bridge)
    assert any("Provenance field" in err for err in errors)


def test_network_url_in_provenance_rejected(tmp_path: Path) -> None:
    """Network/cloud URLs in provenance or inputs must be strictly rejected."""
    run_dir = tmp_path / "cloud_prov_run"
    _write_json(
        run_dir / "RunRecord.json",
        {
            "run_id": "run_cloud_001",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "https://s3.amazonaws.com/openneuro/ds005620",  # forbidden URL
        },
    )
    _write_json(run_dir / "summary.json", {"status": "complete"})
    bridge = build_research_cycle_bridge(run_dir)

    errors = validate_bridge_record(bridge)
    assert any("Network/cloud URL forbidden" in err for err in errors)
