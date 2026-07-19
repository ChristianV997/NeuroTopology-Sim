"""Tests for the shared level_m/base_windows_real.py extraction logic.

The individual dataset behaviors are already covered by
tests/test_ds005620_real_level_m.py and tests/test_ds003969_real_level_m.py
(which exercise the per-dataset shims end-to-end, including monkeypatch
compatibility). This file covers the shared function directly: dependency
injection (discover_fn/read_fn) and task-map-driven state labeling.
"""
from __future__ import annotations

import numpy as np

from data.bids_ingest import BIDSEEGRecord
from sciencer_d.btc_icft.level_m.base_windows_real import (
    build_and_extract_real_windows_from_task_map,
)
from sciencer_d.btc_icft.level_m.ds005620_windows import LevelMWindowRow


def test_uses_injected_discover_and_read_functions():
    """The shared function must use the discover_fn/read_fn it's given, not
    import its own copies -- this is what makes per-dataset-module
    monkeypatching work (see base_windows_real.py's docstring)."""
    records = [
        BIDSEEGRecord(
            path="/fake/sub-001_task-x_eeg.edf", relative_path="sub-001/eeg/sub-001_task-x_eeg.edf",
            subject_id="sub-001", session_id=None, task_label="x", run_id=None,
            acq_label=None, extension=".edf", is_eeg_candidate=True,
        )
    ]
    discover_calls = []
    read_calls = []

    def fake_discover(root):
        discover_calls.append(root)
        return records

    def fake_read(path, start, end, pick, max_channels):
        read_calls.append((path, start, end))
        return np.ones(50)

    rows = build_and_extract_real_windows_from_task_map(
        "/fake/root", LevelMWindowRow, {"x": "state_x"}, fake_discover, fake_read,
        max_windows_per_file=1,
    )
    assert discover_calls == ["/fake/root"]
    assert len(read_calls) == 1
    assert len(rows) == 1
    assert rows[0].state_label == "state_x"


def test_task_to_state_maps_correctly_and_unknown_task_is_none():
    records = [
        BIDSEEGRecord(
            path="/fake/a.edf", relative_path="a.edf", subject_id="sub-001", session_id=None,
            task_label="known", run_id=None, acq_label=None, extension=".edf", is_eeg_candidate=True,
        ),
        BIDSEEGRecord(
            path="/fake/b.edf", relative_path="b.edf", subject_id="sub-002", session_id=None,
            task_label="unmapped", run_id=None, acq_label=None, extension=".edf", is_eeg_candidate=True,
        ),
    ]
    rows = build_and_extract_real_windows_from_task_map(
        "/fake", LevelMWindowRow, {"known": "mapped_state"},
        lambda root: records, lambda *a, **k: np.ones(50),
        max_windows_per_file=1,
    )
    by_subject = {r.subject_id: r for r in rows}
    assert by_subject["sub-001"].state_label == "mapped_state"
    assert by_subject["sub-002"].state_label is None


def test_row_ids_unique_across_windows():
    records = [
        BIDSEEGRecord(
            path="/fake/a.edf", relative_path="a.edf", subject_id="sub-001", session_id=None,
            task_label="x", run_id=None, acq_label=None, extension=".edf", is_eeg_candidate=True,
        ),
    ]
    rows = build_and_extract_real_windows_from_task_map(
        "/fake", LevelMWindowRow, {"x": "state_x"},
        lambda root: records, lambda *a, **k: np.ones(50),
        max_windows_per_file=3,
    )
    ids = [r.row_id for r in rows]
    assert len(ids) == len(set(ids)) == 3


def test_subject_filter():
    records = [
        BIDSEEGRecord(
            path=f"/fake/{sub}.edf", relative_path=f"{sub}.edf", subject_id=sub, session_id=None,
            task_label="x", run_id=None, acq_label=None, extension=".edf", is_eeg_candidate=True,
        )
        for sub in ("sub-001", "sub-002")
    ]
    rows = build_and_extract_real_windows_from_task_map(
        "/fake", LevelMWindowRow, {"x": "state_x"},
        lambda root: records, lambda *a, **k: np.ones(50),
        max_windows_per_file=1, subject_filter="sub-001",
    )
    assert {r.subject_id for r in rows} == {"sub-001"}
