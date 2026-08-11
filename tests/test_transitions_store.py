"""Tests for transitions.store.TransitionStore — filesystem artifact storage."""
from __future__ import annotations

import pytest

from transitions.record import TransitionRecordV1
from transitions.store import TransitionStore


def _make_record(**overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-1010",
        modality="eeg",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_induction",
        feature_names=["topology.q_net", "connectivity.mean_plv"],
        limitations=["synthetic fixture only"],
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


def test_write_creates_record_json(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    written = store.write(record)
    assert written["record"].exists()
    assert written["record"].name == "TransitionRecord.json"


def test_write_without_trajectory_has_no_trajectory_file(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    written = store.write(record)
    assert "trajectory" not in written
    assert not (tmp_path / record.transition_id / "TransitionTrajectory.csv").exists()


def test_write_with_trajectory_creates_csv(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    trajectory = [[1.0, 2.0], [1.5, 2.5], [2.0, 3.0]]
    written = store.write(record, trajectory=trajectory)
    assert written["trajectory"].exists()
    assert record.trajectory_artifact == "TransitionTrajectory.csv"
    assert record.artifact_paths["trajectory"] == "TransitionTrajectory.csv"


def test_read_roundtrip(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    store.write(record, trajectory=[[1.0, 2.0], [2.0, 3.0]])
    loaded = store.read(record.transition_id)
    assert loaded.to_dict() == record.to_dict()


def test_read_missing_record_raises(tmp_path):
    store = TransitionStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.read("nonexistent0000")


def test_read_trajectory_returns_header_and_rows(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    store.write(record, trajectory=[[1.0, 2.0], [1.5, 2.5]])
    header, rows = store.read_trajectory(record.transition_id)
    assert header == ["topology.q_net", "connectivity.mean_plv"]
    assert rows == [[1.0, 2.0], [1.5, 2.5]]


def test_read_trajectory_missing_raises(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    store.write(record)  # no trajectory written
    with pytest.raises(FileNotFoundError):
        store.read_trajectory(record.transition_id)


def test_list_records_empty_store(tmp_path):
    store = TransitionStore(tmp_path / "does_not_exist_yet")
    assert store.list_records() == []


def test_list_records_returns_sorted_ids(tmp_path):
    store = TransitionStore(tmp_path)
    r1 = _make_record(subject_id="sub-1010")
    r2 = _make_record(subject_id="sub-1011")
    store.write(r1)
    store.write(r2)
    ids = store.list_records()
    assert ids == sorted([r1.transition_id, r2.transition_id])


def test_read_all_returns_all_records(tmp_path):
    store = TransitionStore(tmp_path)
    r1 = _make_record(subject_id="sub-1010")
    r2 = _make_record(subject_id="sub-1011")
    store.write(r1)
    store.write(r2)
    loaded = store.read_all()
    assert {r.transition_id for r in loaded} == {r1.transition_id, r2.transition_id}


def test_artifact_paths_are_relative_not_absolute(tmp_path):
    store = TransitionStore(tmp_path)
    record = _make_record()
    store.write(record, trajectory=[[1.0, 2.0]])
    assert "/" not in record.trajectory_artifact
    assert not record.artifact_paths["trajectory"].startswith(str(tmp_path))
