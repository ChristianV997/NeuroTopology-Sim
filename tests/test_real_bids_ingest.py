"""End-to-end test of REAL mne-bids discovery + real sample reading (PR-1 scope only).

Requires mne, mne-bids, edfio. Skips cleanly if unavailable. Uses a generated, spec-valid
synthetic-BIDS fixture (real EDF I/O, synthetic signal content) so this is CI-testable
without a network download.
"""
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


def test_discovery_finds_all_recordings(bids_root):
    from data.bids_ingest import discover_bids_eeg

    recs = discover_bids_eeg(bids_root)
    assert len(recs) == 6  # 3 subjects x 2 tasks
    assert {r.task_label for r in recs} == {"awake", "sedated"}
    assert all(r.provenance == "real_bids" for r in recs)


def test_read_window_returns_real_samples(bids_root):
    from data.bids_ingest import discover_bids_eeg, read_window_signal

    recs = discover_bids_eeg(bids_root)
    sig = read_window_signal(recs[0].path, 0.0, 10.0)
    assert sig.ndim == 1 and sig.size > 100
    assert sig.std() > 0  # not a constant / not a filename hash


def test_get_sample_rate_matches_window_signal_derived_rate(bids_root):
    """get_sample_rate must agree with the sfreq read_window_signal computes
    internally (it re-derives sfreq to slice windows but never exposes it)."""
    from data.bids_ingest import discover_bids_eeg, get_sample_rate, read_window_signal

    recs = discover_bids_eeg(bids_root)
    sfreq = get_sample_rate(recs[0].path)
    assert sfreq > 0

    sig = read_window_signal(recs[0].path, 0.0, 2.0)
    expected_n_samples = round(2.0 * sfreq)
    assert abs(sig.size - expected_n_samples) <= 1
