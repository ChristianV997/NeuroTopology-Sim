"""Tests for the real Level-M window/feature path (PR-2 scope; depends on PR-1's bids_ingest)."""
from __future__ import annotations

import importlib.util

import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("mne", "mne_bids", "edfio"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires mne, mne-bids, edfio")


@pytest.fixture(scope="module")
def bids_root(tmp_path_factory):
    from tests.fixtures.make_synthetic_bids import build

    root = tmp_path_factory.mktemp("bids_synth")
    return str(build(str(root)))


def test_features_track_signal_not_filename(bids_root):
    from sciencer_d.btc_icft.level_m.ds005620_windows_real import build_and_extract_real_windows

    rows = build_and_extract_real_windows(bids_root, max_channels=8)
    aw = [r.spectral_power_proxy for r in rows if r.state_label == "awake"]
    se = [r.spectral_power_proxy for r in rows if r.state_label == "sedated"]
    assert aw and se
    # by fixture construction the two states have different power; features must reflect signal
    assert abs(sum(aw) / len(aw) - sum(se) / len(se)) > 0
    assert all("real_bids" in r.warnings[0] for r in rows)


def test_subject_filter_narrows_to_one_subject(bids_root):
    """Regression test: streaming per-subject processing passes the DATASET root
    plus subject_filter (not a single subject's own directory as bids_root),
    because mne_bids misparses a root whose own path looks like a sub-XXXX
    entity, producing doubled/broken file paths -- exactly what broke the
    initial full-dataset streaming run.
    """
    from sciencer_d.btc_icft.level_m.ds005620_windows_real import build_and_extract_real_windows

    all_rows = build_and_extract_real_windows(bids_root, max_channels=4)
    subjects_present = {r.subject_id for r in all_rows}
    assert len(subjects_present) >= 2  # sanity: fixture has multiple subjects

    one_subject = sorted(subjects_present)[0]
    filtered_rows = build_and_extract_real_windows(
        bids_root, max_channels=4, subject_filter=one_subject
    )
    assert filtered_rows  # non-empty
    assert {r.subject_id for r in filtered_rows} == {one_subject}
    assert len(filtered_rows) < len(all_rows)


def test_row_ids_unique_across_acquisitions(monkeypatch):
    """Regression test: two distinct recordings for the same subject/task/run that only
    differ by the BIDS `acq` entity (e.g. acq-EC vs acq-EO, as in real DS005620) must not
    collide into the same row_id. Previously row_id dropped `acq` entirely, causing
    false leakage_detected on real data.
    """
    import numpy as np
    from data.bids_ingest import BIDSEEGRecord
    import sciencer_d.btc_icft.level_m.ds005620_windows_real as mod

    records = [
        BIDSEEGRecord(
            path=f"/fake/sub-1010_task-awake_acq-{acq}_eeg.vhdr",
            relative_path=f"sub-1010/eeg/sub-1010_task-awake_acq-{acq}_eeg.vhdr",
            subject_id="sub-1010", session_id=None, task_label="awake",
            run_id=None, acq_label=acq, extension=".vhdr", is_eeg_candidate=True,
        )
        for acq in ("EC", "EO")
    ]
    monkeypatch.setattr(mod, "discover_bids_eeg", lambda root: records)
    monkeypatch.setattr(mod, "read_window_signal", lambda *a, **k: np.ones(50))

    rows = mod.build_and_extract_real_windows("/fake", max_windows_per_file=1)
    row_ids = [r.row_id for r in rows]
    assert len(row_ids) == len(set(row_ids)), f"duplicate row_ids: {row_ids}"


def test_cli_real_output_feeds_level_t(tmp_path, bids_root):
    """Regression test for the P9(real)->P10 handoff: run_ds005620_m_real --real must
    write per-window rows that load_level_m_window_features (Level T's loader) can
    actually consume. Previously features_m.csv held only one aggregate summary row,
    so Level T raised ValueError('Missing required columns: [...]') on any real run.
    """
    import subprocess
    import sys

    out = tmp_path / "m_real"
    r = subprocess.run(
        [
            sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_m_real",
            "--real", "--bids-root", bids_root, "--out", str(out),
            "--window-seconds", "4", "--max-windows-per-file", "2", "--max-channels", "4",
        ],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    from sciencer_d.btc_icft.level_t.ds005620_real_topology import load_level_m_window_features

    rows = load_level_m_window_features(str(out))
    assert len(rows) > 0
    assert len({row["row_id"] for row in rows}) == len(rows)  # unique
    assert all(row["source_file"] for row in rows)
