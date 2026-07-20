"""Tests for the real Level-M window/feature path for ds001787 (expert vs novice
meditation, with continuous depth-of-meditation probes).

Two window modes are tested separately, mirroring the module split:
- "fixed" (Analysis A, trait/group): via a synthetic BIDS fixture with a
  participants.tsv group column, exercised end-to-end through real mne_bids
  discovery + real signal reads.
- "probe_locked" (Analysis B, depth correlation): via monkeypatched
  discover_bids_eeg/read_window_signal/events.tsv (the pattern already used by
  ds005620's/ds003969's row-uniqueness regression tests), since building a
  fully synthetic BIDS events.tsv + behavioral zip pair through mne_bids is
  unnecessary machinery for testing the alignment-gating logic itself (already
  covered directly in test_ds001787_behavioral.py against values verified
  against the real dataset).
"""
from __future__ import annotations

import importlib.util
import csv

import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("mne", "mne_bids", "edfio"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires mne, mne-bids, edfio")


def _build_ds001787_synthetic_bids(root, subjects=(("001", "expert"), ("002", "novice"), ("003", "expert"))):
    """ds001787-shaped synthetic BIDS: single task "meditation", participants.tsv
    with a group column (expert/novice) -- matching the real dataset's own schema.
    """
    import shutil
    from pathlib import Path

    import mne
    import numpy as np
    from mne_bids import BIDSPath, write_raw_bids

    def _make_raw(group: str, seed: int, sfreq: float = 200.0, secs: float = 60.0, n_ch: int = 8):
        rng = np.random.default_rng(seed)
        n = int(sfreq * secs)
        t = np.arange(n) / sfreq
        base_freq = 4 + (sum(ord(c) for c in group) % 20)
        sig = (np.sin(2 * np.pi * base_freq * t) + 0.5 * rng.standard_normal((n_ch, n)))
        sig = np.atleast_2d(sig)[:n_ch] * 1e-5
        ch_names = [f"EEG{i:02d}" for i in range(n_ch)]
        info = mne.create_info(ch_names, sfreq, ch_types="eeg")
        raw = mne.io.RawArray(sig, info, verbose="ERROR")
        raw.set_montage(mne.channels.make_standard_montage("standard_1020"), on_missing="ignore", verbose="ERROR")
        return raw

    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    group_by_sub = {}
    for si, (sub, group) in enumerate(subjects):
        raw = _make_raw(group, seed=si * 10 + (sum(ord(c) for c in group) % 7))
        raw.info["line_freq"] = 50
        bp = BIDSPath(subject=sub, session="01", task="meditation", datatype="eeg", root=root, suffix="eeg", extension=".edf")
        write_raw_bids(raw, bp, overwrite=True, allow_preload=True, format="EDF", verbose="ERROR")
        group_by_sub[f"sub-{sub}"] = group

    # write_raw_bids generates a default participants.tsv without a group column;
    # overwrite with the real dataset's schema (participant_id, gender, age, group).
    participants_path = root / "participants.tsv"
    with participants_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["participant_id", "gender", "age", "group"])
        for sub, group in subjects:
            w.writerow([f"sub-{sub}", "M", "30", group])
    return root


@pytest.fixture(scope="module")
def bids_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("bids_synth_ds001787")
    return str(_build_ds001787_synthetic_bids(root))


def test_participant_groups_loaded_from_participants_tsv(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import load_participant_groups

    groups = load_participant_groups(bids_root)
    assert groups["sub-001"] == "expert"
    assert groups["sub-002"] == "novice"
    assert groups["sub-003"] == "expert"


def test_fixed_mode_windows_labeled_by_trait_group(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows

    rows = build_and_extract_real_windows(bids_root, mode="fixed", n_fixed_windows=3, window_seconds=5.0, max_channels=4)
    assert rows
    experts = [r for r in rows if r.state_label == "expert"]
    novices = [r for r in rows if r.state_label == "novice"]
    assert experts and novices
    assert all(r.window_mode == "fixed" for r in rows)
    assert all(r.depth_of_meditation is None for r in rows)  # fixed mode carries no probe rating


def test_fixed_mode_windows_evenly_spaced_across_recording(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows

    rows = build_and_extract_real_windows(bids_root, mode="fixed", n_fixed_windows=3, window_seconds=5.0,
                                           max_channels=4, subject_filter="sub-001")
    assert len(rows) == 3
    starts = sorted(r.window_start_s for r in rows)
    assert starts[0] == 0.0
    assert starts[-1] > starts[0]  # not all bunched at the start (unlike fixed-10s-from-0 in prior datasets)


def test_subject_filter_narrows_to_one_subject(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows

    all_rows = build_and_extract_real_windows(bids_root, mode="fixed", n_fixed_windows=2, max_channels=4)
    subjects_present = {r.subject_id for r in all_rows}
    assert len(subjects_present) >= 2

    one = sorted(subjects_present)[0]
    filtered = build_and_extract_real_windows(bids_root, mode="fixed", n_fixed_windows=2, max_channels=4, subject_filter=one)
    assert filtered
    assert {r.subject_id for r in filtered} == {one}


def test_row_ids_unique(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows

    rows = build_and_extract_real_windows(bids_root, mode="fixed", n_fixed_windows=3, max_channels=4)
    ids = [r.row_id for r in rows]
    assert len(ids) == len(set(ids))


def test_probe_locked_mode_requires_behavioral_data(bids_root):
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows

    with pytest.raises(ValueError, match="probe_locked"):
        build_and_extract_real_windows(bids_root, mode="probe_locked")


def test_probe_locked_mode_produces_depth_labeled_windows(monkeypatch, tmp_path):
    """Monkeypatched end-to-end: one aligned probe -> one window carrying its
    depth-of-meditation rating; the pre-recording-start epoch is included.
    """
    import numpy as np
    from data.bids_ingest import BIDSEEGRecord
    import sciencer_d.btc_icft.level_m.ds001787_windows_real as mod
    from sciencer_d.btc_icft.level_m.ds001787_behavioral import ProbeRating

    eeg_file = tmp_path / "sub-001_ses-01_task-meditation_eeg.bdf"
    eeg_file.write_bytes(b"x")
    events_file = tmp_path / "sub-001_ses-01_task-meditation_events.tsv"
    events_file.write_text("onset\tduration\ttrial_type\tsample\tvalue\n30.0\tn/a\tstimulus\t0\t128\n", encoding="utf-8")
    participants = tmp_path / "participants.tsv"
    participants.write_text("participant_id\tgender\tage\tgroup\nsub-001\tM\t30\texpert\n", encoding="utf-8")

    record = BIDSEEGRecord(
        path=str(eeg_file), relative_path="sub-001/eeg/sub-001_ses-01_task-meditation_eeg.bdf",
        subject_id="sub-001", session_id="ses-01", task_label="meditation",
        run_id=None, acq_label=None, extension=".bdf", is_eeg_candidate=True,
    )
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: [record])
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))

    # behavioral_data subject keys are 2-digit zero-padded (matches the zip's own
    # filename convention, e.g. sub01_info.txt -> "01") -- NOT the BIDS subject_id's
    # own width. Regression-relevant: an earlier version of the lookup used "001"
    # here and silently matched nothing, producing 0 probe_locked rows even for
    # subjects with perfectly good alignment (found via the real sub-001 pilot run).
    behavioral_data = {"01": {"1": [ProbeRating(mw_question_time_s=25.0, depth_of_meditation=2,
                                                  depth_of_mind_wandering=1, tiredness=0)]}}
    rows = mod.build_and_extract_real_windows(
        str(tmp_path), mode="probe_locked", behavioral_data=behavioral_data,
    )
    assert len(rows) == 1
    assert rows[0].window_mode == "probe_locked"
    assert rows[0].depth_of_meditation == 2
    assert rows[0].window_start_s == 0.0
    assert rows[0].window_end_s == 30.0  # events.tsv stimulus onset (ground truth), not the behavioral clock time


def test_probe_locked_mode_excludes_unusable_alignment(monkeypatch, tmp_path):
    """A session whose alignment fails the quality gate must emit zero probe_locked
    windows, not a bad-but-present one.
    """
    import numpy as np
    from data.bids_ingest import BIDSEEGRecord
    import sciencer_d.btc_icft.level_m.ds001787_windows_real as mod
    from sciencer_d.btc_icft.level_m.ds001787_behavioral import ProbeRating

    eeg_file = tmp_path / "sub-013_ses-01_task-meditation_eeg.bdf"
    eeg_file.write_bytes(b"x")
    events_file = tmp_path / "sub-013_ses-01_task-meditation_events.tsv"
    # unreconcilable timestamps (mirrors the real sub-013/ses-01 finding)
    events_file.write_text(
        "onset\tduration\ttrial_type\tsample\tvalue\n"
        "71.3\tn/a\tstimulus\t0\t128\n242.1\tn/a\tstimulus\t0\t128\n"
        "281.6\tn/a\tstimulus\t0\t128\n343.9\tn/a\tstimulus\t0\t128\n",
        encoding="utf-8",
    )
    participants = tmp_path / "participants.tsv"
    participants.write_text("participant_id\tgender\tage\tgroup\nsub-013\tF\t47\tnovice\n", encoding="utf-8")

    record = BIDSEEGRecord(
        path=str(eeg_file), relative_path="sub-013/eeg/sub-013_ses-01_task-meditation_eeg.bdf",
        subject_id="sub-013", session_id="ses-01", task_label="meditation",
        run_id=None, acq_label=None, extension=".bdf", is_eeg_candidate=True,
    )
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: [record])
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones((4, 50)))

    behavioral_data = {"13": {"1": [
        ProbeRating(20.1, 1, 1, 0), ProbeRating(158.8, 1, 1, 0),
        ProbeRating(213.8, 1, 1, 0), ProbeRating(246.3, 1, 1, 0),
    ]}}
    rows = mod.build_and_extract_real_windows(
        str(tmp_path), mode="probe_locked", behavioral_data=behavioral_data,
    )
    assert rows == []


def test_cli_fixed_mode_output_feeds_level_t(tmp_path, bids_root):
    import subprocess
    import sys

    out = tmp_path / "m_real"
    r = subprocess.run(
        [
            sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds001787_m_real",
            "--bids-root", bids_root, "--out", str(out),
            "--mode", "fixed", "--n-fixed-windows", "2", "--window-seconds", "5", "--max-channels", "4",
        ],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    from sciencer_d.btc_icft.level_t.ds001787_real_topology import load_level_m_window_features

    rows = load_level_m_window_features(str(out))
    assert len(rows) > 0
    assert len({row["row_id"] for row in rows}) == len(rows)
    assert all(row["source_file"] for row in rows)
