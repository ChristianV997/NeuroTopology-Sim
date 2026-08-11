"""Tests for phase_space.export_from_transitions.

Includes a real-artifact smoke integration that reads only the small,
git-committed `contracts/btc_icft/ds005620/pitnn_cohort/` files already in
the repository (no raw data, no downloads, no pipeline re-runs).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from phase_space.axes import AXIS_NAMES
from phase_space.export_from_transitions import ExportError, export
from phase_space.store import PhaseSpaceStore
from transitions.record import TransitionRecordV1
from transitions.store import TransitionStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DS005620_COHORT = _REPO_ROOT / "contracts/btc_icft/ds005620/pitnn_cohort"


def _record(**overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-9001",
        modality="EEG",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_propofol_awake_to_sedated",
        feature_names=["topology.q_abs", "connectivity.mean_plv"],
        limitations=["synthetic fixture only"],
        claim_scope="exploratory_metric",
        evidence_level="L2_single_subject_real_signal",
        delta_summary={
            "status": "ok", "delta_per_feature": [4.0, -0.2],
            "mean_abs_delta": 2.1, "n_timepoints": 2, "n_features": 2,
        },
        time_axis={"unit": "condition_summary", "n_samples": 2},
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


# ── Export from a single record file ────────────────────────────────────────

def test_export_from_single_record_file(tmp_path):
    rec = _record()
    record_path = tmp_path / "TransitionRecord.json"
    rec.write_json(record_path)

    result = export(record_path, tmp_path / "out")

    assert result["n_transitions"] == 1
    assert result["n_coordinates"] == len(AXIS_NAMES)
    assert result["n_estimated"] >= 1
    assert result["n_failed_validation"] == 0


def test_export_from_transition_store_directory(tmp_path):
    tx_dir = tmp_path / "tx"
    store = TransitionStore(tx_dir)
    for subject in ("sub-9001", "sub-9002", "sub-9003"):
        store.write(_record(subject_id=subject))

    result = export(tx_dir, tmp_path / "out")

    assert result["n_transitions"] == 3
    assert result["n_coordinates"] == 3 * len(AXIS_NAMES)
    assert len(result["per_transition"]) == 3


def test_export_writes_readable_store(tmp_path):
    rec = _record()
    record_path = tmp_path / "TransitionRecord.json"
    rec.write_json(record_path)
    out_dir = tmp_path / "out"

    export(record_path, out_dir)

    store = PhaseSpaceStore(out_dir)
    assert store.list_records() == [rec.transition_id]
    coords = store.read(rec.transition_id)
    assert len(coords) == len(AXIS_NAMES)
    for c in coords:
        assert c.validate() == []


def test_export_writes_trajectory_by_default(tmp_path):
    rec = _record()
    rec.write_json(tmp_path / "TransitionRecord.json")
    out_dir = tmp_path / "out"
    export(tmp_path / "TransitionRecord.json", out_dir)
    traj = PhaseSpaceStore(out_dir).read_trajectory(rec.transition_id)
    assert traj.validate() == []


def test_export_can_skip_trajectory(tmp_path):
    rec = _record()
    rec.write_json(tmp_path / "TransitionRecord.json")
    out_dir = tmp_path / "out"
    export(tmp_path / "TransitionRecord.json", out_dir, write_trajectory=False)
    with pytest.raises(FileNotFoundError):
        PhaseSpaceStore(out_dir).read_trajectory(rec.transition_id)


def test_summary_counts_estimated_and_insufficient(tmp_path):
    rec = _record()
    rec.write_json(tmp_path / "TransitionRecord.json")
    result = export(tmp_path / "TransitionRecord.json", tmp_path / "out")
    total = result["n_estimated"] + result["n_insufficient_data"] + result["n_failed_validation"]
    assert total == result["n_coordinates"]
    assert result["n_insufficient_data"] > 0  # placeholder axes always insufficient


def test_export_records_source_record_path(tmp_path):
    rec = _record()
    record_path = tmp_path / "TransitionRecord.json"
    rec.write_json(record_path)
    result = export(record_path, tmp_path / "out")
    for c in result["coordinates"]:
        assert c.provenance["source_record_path"] == str(record_path)


# ── Fail-closed behaviour ───────────────────────────────────────────────────

def test_missing_input_path_fails(tmp_path):
    with pytest.raises(ExportError, match="does not exist"):
        export(tmp_path / "nope", tmp_path / "out")


def test_empty_directory_fails(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ExportError, match="no TransitionRecord.json"):
        export(empty, tmp_path / "out")


def test_malformed_record_fails_closed(tmp_path):
    bad = tmp_path / "TransitionRecord.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ExportError):
        export(bad, tmp_path / "out")


def test_record_without_transition_id_is_rejected(tmp_path):
    bad = tmp_path / "TransitionRecord.json"
    bad.write_text(json.dumps({"dataset_id": "ds005620"}), encoding="utf-8")
    with pytest.raises(ExportError):
        export(bad, tmp_path / "out")


def test_unknown_normalization_mode_fails(tmp_path):
    rec = _record()
    rec.write_json(tmp_path / "TransitionRecord.json")
    with pytest.raises(ExportError, match="unknown normalization mode"):
        export(tmp_path / "TransitionRecord.json", tmp_path / "out",
               normalization_mode="minmax")


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_end_to_end(tmp_path):
    rec = _record()
    rec.write_json(tmp_path / "TransitionRecord.json")
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [sys.executable, "-m", "phase_space.export_from_transitions",
         "--input", str(tmp_path / "TransitionRecord.json"),
         "--out", str(out_dir), "--normalization-mode", "within_record"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["transitions_read"] == 1
    assert payload["coordinates_total"] == len(AXIS_NAMES)


def test_cli_missing_input_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "phase_space.export_from_transitions",
         "--input", str(tmp_path / "nope"), "--out", str(tmp_path / "out")],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


# ── Real-artifact smoke integration (committed artifacts only) ──────────────

@pytest.mark.skipif(
    not (_DS005620_COHORT / "cohort_summary.json").exists(),
    reason="committed ds005620 cohort artifact not present",
)
def test_ds005620_real_artifact_smoke_integration(tmp_path):
    """TransitionRecords from the committed ds005620 artifact -> coordinates.

    Reads only small committed JSON/CSV contract files; no raw EEG, no
    download, no pipeline re-run.
    """
    from tools.export_ds005620_pitnn_transitions import export as export_transitions

    tx_dir = tmp_path / "tx"
    tx_result = export_transitions(
        _DS005620_COHORT, tx_dir, feature_set="spatial_defect_map"
    )
    assert tx_result["subject_records"]

    ps_result = export(tx_dir, tmp_path / "ps", normalization_mode="within_record")

    assert ps_result["n_transitions"] == len(tx_result["subject_records"]) + 1
    assert ps_result["n_failed_validation"] == 0

    by_axis: dict[str, set[str]] = {}
    for c in ps_result["coordinates"]:
        by_axis.setdefault(c.axis, set()).add(c.status)

    # topology features are genuinely present in this artifact -> estimable
    assert "estimated" in by_axis["topological_organization"]

    # phenomenology-backed axes must stay honest, never guessed
    for axis in ("generative_depth_proxy", "self_model_proxy"):
        assert by_axis[axis] == {"insufficient_data"}

    # this artifact carries no connectivity features -> no fabricated value
    assert by_axis["integration"] == {"insufficient_data"}

    for c in ps_result["coordinates"]:
        assert c.validate() == []
        assert c.output_claim_scope in ("computational_artifact", "exploratory_metric")


@pytest.mark.skipif(
    not (_DS005620_COHORT / "cohort_summary.json").exists(),
    reason="committed ds005620 cohort artifact not present",
)
def test_ds005620_cohort_summary_feature_set_yields_integration_coordinate(tmp_path):
    """The cohort_summary feature set carries connectivity.mean_plv."""
    from tools.export_ds005620_pitnn_transitions import export as export_transitions

    tx_dir = tmp_path / "tx"
    export_transitions(_DS005620_COHORT, tx_dir, feature_set="cohort_summary")
    ps_result = export(tx_dir, tmp_path / "ps")

    integration = [c for c in ps_result["coordinates"] if c.axis == "integration"]
    assert any(c.status == "estimated" for c in integration)
    for c in integration:
        if c.status == "estimated":
            assert c.source_features == ["connectivity.mean_plv"]
            assert c.confidence in ("low", "moderate")
