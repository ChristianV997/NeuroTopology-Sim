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
