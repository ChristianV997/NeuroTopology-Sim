"""End-to-end test of REAL mne-bids discovery + real sample reading (PR-1 scope only).

Requires mne, mne-bids, edfio. Skips cleanly if unavailable. Uses a generated, spec-valid
synthetic-BIDS fixture (real EDF I/O, synthetic signal content) so this is CI-testable
without a network download.
"""
from __future__ import annotations

import importlib.util

import numpy as np
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


def test_read_window_signal_default_preserves_prior_behavior(bids_root):
    """preprocess=None (the default) must produce output identical to before
    data/preprocessing.py existed -- every currently-published number in the
    three dataset reports was computed this way and must stay reproducible."""
    from data.bids_ingest import discover_bids_eeg, read_window_signal

    recs = discover_bids_eeg(bids_root)
    sig_no_kwarg = read_window_signal(recs[0].path, 0.0, 10.0)
    sig_explicit_none = read_window_signal(recs[0].path, 0.0, 10.0, preprocess=None)
    assert np.array_equal(sig_no_kwarg, sig_explicit_none)


def test_read_window_signal_preprocess_opt_in_changes_output(bids_root):
    """Passing `preprocess` must actually take effect -- proves the wiring is
    live, not silently ignored."""
    from data.bids_ingest import discover_bids_eeg, read_window_signal

    recs = discover_bids_eeg(bids_root)
    sig_raw = read_window_signal(recs[0].path, 0.0, 10.0, pick="all")
    sig_filtered = read_window_signal(
        recs[0].path, 0.0, 10.0, pick="all",
        preprocess={"l_freq": 0.5, "h_freq": 45.0, "reference": "average"},
    )
    assert sig_raw.shape == sig_filtered.shape
    assert not np.array_equal(sig_raw, sig_filtered)


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


# ── per-recording read cache (throughput optimization) ───────────────────────

def test_read_cache_is_byte_identical_to_fresh_read(bids_root):
    """A cached read must return exactly the same samples as an independent
    fresh parse of the same file/window (the optimization changes only how many
    times the header is parsed, never the numbers)."""
    import mne
    from data.bids_ingest import discover_bids_eeg, read_window_signal, _read_raw, clear_raw_cache

    path = discover_bids_eeg(bids_root)[0].path
    clear_raw_cache()
    cached = read_window_signal(path, 0.0, 2.0, pick="all", max_channels=4)
    raw = _read_raw(path)
    picks = mne.pick_types(raw.info, eeg=True)[:4]
    sfreq = float(raw.info["sfreq"])
    fresh = raw.get_data(picks=picks, start=0, stop=int(round(2.0 * sfreq)))
    assert np.array_equal(cached, fresh)


def test_read_cache_avoids_reparsing_same_recording(bids_root, monkeypatch):
    """Repeated windows of one recording must parse the file header ONCE, not
    once per window -- the whole point of the cache."""
    import data.bids_ingest as bi
    from data.bids_ingest import discover_bids_eeg

    path = discover_bids_eeg(bids_root)[0].path
    bi.clear_raw_cache()
    calls = {"n": 0}
    real = bi._read_raw

    def counting(p):
        calls["n"] += 1
        return real(p)

    monkeypatch.setattr(bi, "_read_raw", counting)
    for _ in range(5):
        bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4)
    assert calls["n"] == 1, f"expected 1 parse for 5 windows, got {calls['n']}"


def test_read_cache_invalidated_when_file_changes(bids_root, tmp_path, monkeypatch):
    """A changed file (different mtime/size) must not be served a stale raw."""
    import data.bids_ingest as bi
    from data.bids_ingest import discover_bids_eeg

    path = discover_bids_eeg(bids_root)[0].path
    bi.clear_raw_cache()
    calls = {"n": 0}
    real = bi._read_raw
    monkeypatch.setattr(bi, "_read_raw", lambda p: (calls.__setitem__("n", calls["n"] + 1), real(p))[1])

    bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4)
    # bump mtime -> cache key changes -> re-parse
    import os, time
    os.utime(path, (time.time() + 10, time.time() + 10))
    bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4)
    assert calls["n"] == 2, "stale cache served after file changed"


def test_preprocess_path_does_not_use_cached_raw(bids_root, monkeypatch):
    """The mutating preprocess path must read a FRESH raw each call so it never
    corrupts the shared cached instance (regression guard for the cache)."""
    import data.bids_ingest as bi
    from data.bids_ingest import discover_bids_eeg

    path = discover_bids_eeg(bids_root)[0].path
    bi.clear_raw_cache()
    seen = {"cached": 0, "fresh": 0}
    real_cached = bi._read_raw_cached
    real_fresh = bi._read_raw
    monkeypatch.setattr(bi, "_read_raw_cached", lambda p: (seen.__setitem__("cached", seen["cached"] + 1), real_cached(p))[1])
    monkeypatch.setattr(bi, "_read_raw", lambda p: (seen.__setitem__("fresh", seen["fresh"] + 1), real_fresh(p))[1])

    bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4,
                          preprocess={"l_freq": 1.0, "h_freq": 40.0})
    assert seen["fresh"] >= 1 and seen["cached"] == 0
