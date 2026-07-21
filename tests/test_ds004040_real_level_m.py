"""Tests for the real Level-M window/feature path for ds004040 (Trance
channeling EEG study) -- specifically the `_state_intervals` parser, since
this dataset's state comes from the `value` column (`rest1_start`/
`trance2_end`/...), not `trial_type` (always the literal "STATUS")."""
from __future__ import annotations

import numpy as np
import pytest

from data.bids_ingest import BIDSEEGRecord
from sciencer_d.btc_icft.level_m.ds004040_windows_real import (
    _state_intervals,
    build_and_extract_real_windows,
)
import sciencer_d.btc_icft.level_m.ds004040_windows_real as mod


def _write_events(tmp_path, rows):
    """rows: list of (onset, trial_type, value)."""
    p = tmp_path / "sub-001_ses-01_task-trance_events.tsv"
    with p.open("w") as f:
        f.write("onset\tduration\tsample\ttrial_type\tresponse_time\tstim_file\tvalue\n")
        for onset, trial_type, value in rows:
            f.write(f"{onset}\tn/a\t0\t{trial_type}\tn/a\tn/a\t{value}\n")
    return p


def test_parses_real_value_column_not_trial_type(tmp_path):
    """trial_type is always literal 'STATUS' in the real dataset; state must
    come from `value`, matched pairwise by <label>_start/<label>_end."""
    events = _write_events(tmp_path, [
        (100.0, "STATUS", "rest1_start"),
        (400.0, "STATUS", "rest1_end"),
        (450.0, "STATUS", "trance1_start"),
        (900.0, "STATUS", "trance1_end"),
    ])
    intervals = _state_intervals(events)
    assert intervals == [("rest", 100.0, 400.0), ("trance", 450.0, 900.0)]


def test_multiple_blocks_per_state_all_paired(tmp_path):
    events = _write_events(tmp_path, [
        (100.0, "STATUS", "trance1_start"), (300.0, "STATUS", "trance1_end"),
        (350.0, "STATUS", "rest1_start"), (500.0, "STATUS", "rest1_end"),
        (600.0, "STATUS", "trance2_start"), (800.0, "STATUS", "trance2_end"),
    ])
    intervals = _state_intervals(events)
    states = [s for s, _, _ in intervals]
    assert states == ["trance", "rest", "trance"]


def test_unpaired_marker_is_dropped_not_fabricated(tmp_path):
    """A _start with no matching _end (or vice versa) must yield no interval
    for that label -- no_label_inference: never guess a boundary."""
    events = _write_events(tmp_path, [
        (100.0, "STATUS", "rest1_start"),
        (400.0, "STATUS", "rest1_end"),
        (450.0, "STATUS", "trance1_start"),  # no matching trance1_end
    ])
    intervals = _state_intervals(events)
    assert intervals == [("rest", 100.0, 400.0)]


def test_missing_events_file_yields_no_intervals(tmp_path):
    assert _state_intervals(tmp_path / "does_not_exist_events.tsv") == []


def test_build_and_extract_windows_labels_states_from_real_markers(tmp_path, monkeypatch):
    events_path = _write_events(tmp_path, [
        (0.0, "STATUS", "rest1_start"), (100.0, "STATUS", "rest1_end"),
        (110.0, "STATUS", "trance1_start"), (250.0, "STATUS", "trance1_end"),
    ])
    eeg_path = tmp_path / "sub-001_ses-01_task-trance_eeg.set"
    eeg_path.write_text("")  # discover_bids_eeg is mocked; only events_path parsing needs to be real

    records = [
        BIDSEEGRecord(
            path=str(eeg_path), relative_path="sub-001/ses-01/eeg/sub-001_ses-01_task-trance_eeg.set",
            subject_id="sub-001", session_id="ses-01", task_label="trance", run_id=None,
            acq_label=None, extension=".set", is_eeg_candidate=True,
        )
    ]
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: records)
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))

    rows = build_and_extract_real_windows(str(tmp_path), window_seconds=10.0, max_windows_per_state=5)
    assert rows
    labels = {r.state_label for r in rows}
    assert labels == {"rest", "trance"}
    for r in rows:
        assert r.warnings and "real_bids" in r.warnings[0]


def test_non_trance_task_is_skipped(tmp_path, monkeypatch):
    """Regression guard: only task-trance recordings are windowed."""
    records = [
        BIDSEEGRecord(
            path="/fake/x.set", relative_path="sub-001/eeg/sub-001_task-rest_eeg.set",
            subject_id="sub-001", session_id=None, task_label="rest", run_id=None,
            acq_label=None, extension=".set", is_eeg_candidate=True,
        )
    ]
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: records)
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))
    rows = build_and_extract_real_windows("/fake")
    assert rows == []
