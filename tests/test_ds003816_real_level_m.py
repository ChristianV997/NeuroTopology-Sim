"""Tests for the real Level-M window/feature path for ds003816 (loving-
kindness meditation vs resting).

Mirrors tests/test_ds003969_real_level_m.py's structure and regression
coverage, reusing the same local synthetic-BIDS builder pattern with
ds003816's confirmed real task labels.
"""
from __future__ import annotations

import importlib.util

import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("mne", "mne_bids", "edfio"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires mne, mne-bids, edfio")


def _build_ds003816_synthetic_bids(root, subjects=("01lt", "02st", "03lt"), states=("LKMSelf", "PreResting")):
    """Local ds003816-shaped synthetic-BIDS builder (same rationale as
    ds003969's: `tests.fixtures.make_synthetic_bids.build`'s signal generator
    only differentiates content for the literal string "awake", so states
    outside that fall into its "else" branch with identical content)."""
    import shutil
    from pathlib import Path

    import mne
    import numpy as np
    from mne_bids import BIDSPath, write_raw_bids

    def _make_raw(state: str, seed: int, sfreq: float = 200.0, secs: float = 40.0, n_ch: int = 8):
        rng = np.random.default_rng(seed)
        n = int(sfreq * secs)
        t = np.arange(n) / sfreq
        base_freq = 4 + (sum(ord(c) for c in state) % 20)
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
    for si, sub in enumerate(subjects):
        for state in states:
            raw = _make_raw(state, seed=si * 10 + (sum(ord(c) for c in state) % 7))
            raw.info["line_freq"] = 60
            bp = BIDSPath(subject=sub, session="01", task=state, run="01", datatype="eeg", root=root, suffix="eeg", extension=".edf")
            write_raw_bids(raw, bp, overwrite=True, allow_preload=True, format="EDF", verbose="ERROR")
    return root


@pytest.fixture(scope="module")
def bids_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("bids_synth_ds003816")
    return str(_build_ds003816_synthetic_bids(root))


def test_features_track_signal_not_filename(bids_root):
    from sciencer_d.btc_icft.level_m.ds003816_windows_real import build_and_extract_real_windows

    rows = build_and_extract_real_windows(bids_root, max_channels=8)
    med = [r.spectral_power_proxy for r in rows if r.state_label == "meditation"]
    rest = [r.spectral_power_proxy for r in rows if r.state_label == "resting"]
    assert med and rest
    # by fixture construction the two states have different power; features must reflect signal
    assert abs(sum(med) / len(med) - sum(rest) / len(rest)) > 0
    assert all("real_bids" in r.warnings[0] for r in rows)


def test_task_label_mapping_confirmed_not_guessed(bids_root):
    """Regression/documentation test: ds003816's real BIDS task entities were
    confirmed via direct S3 listing (LKMSelf, LKMOther, PreResting,
    PostResting, VisualizeSelf, VisualizeOther), not assumed. This asserts
    the mapping table matches exactly the 2-class-relevant subset and
    nothing else, so a future edit can't silently drift toward guessing a
    label for the excluded Visualize* conditions.
    """
    from sciencer_d.btc_icft.level_m.ds003816_windows_real import _TASK_TO_STATE

    assert _TASK_TO_STATE == {
        "lkmself": "meditation",
        "lkmother": "meditation",
        "preresting": "resting",
        "postresting": "resting",
    }
    assert "visualizeself" not in _TASK_TO_STATE
    assert "visualizeother" not in _TASK_TO_STATE


def test_subject_filter_narrows_to_one_subject(bids_root):
    """Regression test: streaming per-subject processing passes the DATASET root
    plus subject_filter (not a single subject's own directory as bids_root).
    """
    from sciencer_d.btc_icft.level_m.ds003816_windows_real import build_and_extract_real_windows

    all_rows = build_and_extract_real_windows(bids_root, max_channels=4)
    subjects_present = {r.subject_id for r in all_rows}
    assert len(subjects_present) >= 2

    one_subject = sorted(subjects_present)[0]
    filtered_rows = build_and_extract_real_windows(
        bids_root, max_channels=4, subject_filter=one_subject
    )
    assert filtered_rows
    assert {r.subject_id for r in filtered_rows} == {one_subject}
    assert len(filtered_rows) < len(all_rows)


def test_row_ids_unique_across_windows_and_sessions(monkeypatch):
    """ds003816 has no `acq` BIDS entity but DOES have multiple `ses-NN`
    sessions per subject (long-term practitioners recorded up to 10 times);
    the row_id must stay unique across sessions, not just across tasks.
    """
    import numpy as np
    from data.bids_ingest import BIDSEEGRecord
    import sciencer_d.btc_icft.level_m.ds003816_windows_real as mod

    records = [
        BIDSEEGRecord(
            path=f"/fake/sub-01lt_ses-{ses}_task-{task}_eeg.vhdr",
            relative_path=f"sub-01lt/ses-{ses}/eeg/sub-01lt_ses-{ses}_task-{task}_eeg.vhdr",
            subject_id="sub-01lt", session_id=f"ses-{ses}", task_label=task,
            run_id=None, acq_label=None, extension=".vhdr", is_eeg_candidate=True,
        )
        for ses in ("01", "02")
        for task in ("LKMSelf", "LKMOther", "PreResting", "PostResting")
    ]
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: records)
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))

    rows = mod.build_and_extract_real_windows("/fake", max_windows_per_file=1)
    row_ids = [r.row_id for r in rows]
    assert len(row_ids) == len(set(row_ids)), f"duplicate row_ids: {row_ids}"


def test_visualize_tasks_left_unmapped(monkeypatch):
    """VisualizeSelf/VisualizeOther must produce state_label=None (excluded
    from the 2-class contrast), not be silently folded into meditation or
    resting."""
    import numpy as np
    from data.bids_ingest import BIDSEEGRecord
    import sciencer_d.btc_icft.level_m.ds003816_windows_real as mod

    records = [
        BIDSEEGRecord(
            path="/fake/sub-01lt_task-VisualizeSelf_eeg.vhdr",
            relative_path="sub-01lt/eeg/sub-01lt_task-VisualizeSelf_eeg.vhdr",
            subject_id="sub-01lt", session_id=None, task_label="VisualizeSelf",
            run_id=None, acq_label=None, extension=".vhdr", is_eeg_candidate=True,
        ),
    ]
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: records)
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))

    rows = mod.build_and_extract_real_windows("/fake", max_windows_per_file=1)
    assert len(rows) == 1
    assert rows[0].state_label is None


def test_features_are_native_python_types_not_numpy_scalars(bids_root):
    """Regression test for the same numpy-scalar-taint bug found while porting
    ds003969: real-signal features must be native Python floats, and the
    aggregate result must survive json.dumps regardless of whether
    mean_artifact_score crosses the 0.5 dominance threshold."""
    import json
    from dataclasses import asdict

    from sciencer_d.btc_icft.level_m.ds003816_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_m.ds003816_windows import evaluate_level_m_windows

    rows = build_and_extract_real_windows(bids_root, max_channels=8)
    for r in rows:
        for field in ("spectral_power_proxy", "entropy_proxy", "lzc_proxy", "artifact_score"):
            v = getattr(r, field)
            if v is not None:
                assert type(v) is float, f"{field} is {type(v)}, not native float"

    result = evaluate_level_m_windows(rows, task="lkm_vs_resting")
    assert type(result.artifact_report["artifact_dominance"]) is bool
    json.dumps({k: v for k, v in asdict(result).items() if k != "rows"})


def test_cli_real_output_feeds_level_t(tmp_path, bids_root):
    """Regression test for the M(real)->T handoff: run_ds003816_m_real --real must
    write per-window rows that load_level_m_window_features (Level T's loader) can
    actually consume.
    """
    import subprocess
    import sys

    out = tmp_path / "m_real"
    r = subprocess.run(
        [
            sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003816_m_real",
            "--real", "--bids-root", bids_root, "--out", str(out),
            "--window-seconds", "4", "--max-windows-per-file", "2", "--max-channels", "4",
        ],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    from sciencer_d.btc_icft.level_t.ds003816_real_topology import load_level_m_window_features

    rows = load_level_m_window_features(str(out))
    assert len(rows) > 0
    assert len({row["row_id"] for row in rows}) == len(rows)
    assert all(row["source_file"] for row in rows)
