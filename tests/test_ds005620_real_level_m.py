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
