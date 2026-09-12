"""Bounded caches, chunk release, and preprocess reuse."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.performance.streaming_optimization.conftest import requires_mne

pytestmark = requires_mne


@pytest.fixture
def one_recording(tmp_path):
    from tests.fixtures.make_synthetic_bids import build
    from data.bids_ingest import clear_raw_cache, discover_bids_eeg

    root = build(str(tmp_path / "bids"), subjects=("01", "02"), states=("awake",))
    recs = discover_bids_eeg(str(root))
    clear_raw_cache()
    return recs


def test_window_cache_is_consulted_before_preprocess(one_recording, monkeypatch):
    import data.bids_ingest as bi

    path = one_recording[0].path
    bi.clear_raw_cache()
    calls = {"fresh": 0, "cached": 0}
    real_fresh = bi._read_raw
    real_cached = bi._read_raw_cached

    monkeypatch.setattr(
        bi, "_read_raw", lambda p: (calls.__setitem__("fresh", calls["fresh"] + 1), real_fresh(p))[1]
    )
    monkeypatch.setattr(
        bi,
        "_read_raw_cached",
        lambda p: (calls.__setitem__("cached", calls["cached"] + 1), real_cached(p))[1],
    )
    preprocess = {"l_freq": 1.0, "h_freq": 40.0, "reference": None}
    first = bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4, preprocess=preprocess)
    second = bi.read_window_signal(path, 2.0, 4.0, pick="mean", max_channels=4, preprocess=preprocess)
    replay = bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4, preprocess=preprocess)
    assert calls["cached"] == 0
    assert calls["fresh"] == 1, "second window must reuse the preprocessed recording"
    assert np.array_equal(first, replay)
    assert first.shape == second.shape
    assert not np.array_equal(first, second)


def test_preprocess_path_still_avoids_shared_raw_cache(one_recording, monkeypatch):
    import data.bids_ingest as bi

    path = one_recording[0].path
    bi.clear_raw_cache()
    seen = {"cached": 0, "fresh": 0}
    real_cached = bi._read_raw_cached
    real_fresh = bi._read_raw
    monkeypatch.setattr(
        bi,
        "_read_raw_cached",
        lambda p: (seen.__setitem__("cached", seen["cached"] + 1), real_cached(p))[1],
    )
    monkeypatch.setattr(
        bi, "_read_raw", lambda p: (seen.__setitem__("fresh", seen["fresh"] + 1), real_fresh(p))[1]
    )
    bi.read_window_signal(
        path, 0.0, 2.0, pick="mean", max_channels=4, preprocess={"l_freq": 1.0, "h_freq": 40.0}
    )
    assert seen["fresh"] >= 1 and seen["cached"] == 0


def test_raw_and_window_and_preprocess_caches_are_bounded(one_recording):
    import data.bids_ingest as bi

    bi.clear_raw_cache()
    paths = [rec.path for rec in one_recording]
    assert len(paths) >= 2
    for path in paths:
        for start in (0.0, 2.0, 4.0, 6.0):
            bi.read_window_signal(path, start, start + 2.0, pick="mean", max_channels=4)
        bi.read_window_signal(
            path,
            0.0,
            2.0,
            pick="mean",
            max_channels=4,
            preprocess={"l_freq": 1.0, "h_freq": 40.0, "reference": None},
        )
        assert len(bi._RAW_CACHE) <= bi._RAW_CACHE_MAXSIZE
        assert len(bi._WINDOW_CACHE) <= bi._WINDOW_CACHE_MAXSIZE
        assert len(bi._PREPROCESS_CACHE) <= bi._PREPROCESS_CACHE_MAXSIZE
    assert bi._RAW_CACHE_MAXSIZE == 4
    assert bi._WINDOW_CACHE_MAXSIZE == 64
    assert bi._PREPROCESS_CACHE_MAXSIZE == 1


def test_clear_and_release_drop_chunks_after_final_consumer(one_recording):
    import data.bids_ingest as bi

    path = one_recording[0].path
    other = one_recording[1].path
    bi.clear_raw_cache()
    bi.read_window_signal(path, 0.0, 2.0, pick="all", max_channels=4)
    bi.read_window_signal(
        other, 0.0, 2.0, pick="all", max_channels=4, preprocess={"l_freq": 1.0, "h_freq": 40.0}
    )
    assert len(bi._RAW_CACHE) >= 1
    assert len(bi._WINDOW_CACHE) >= 1
    bi.release_recording(path)
    assert all(key[0] != path for key in bi._RAW_CACHE)
    assert all(key[0] != path for key in bi._WINDOW_CACHE)
    bi.clear_raw_cache()
    assert len(bi._RAW_CACHE) == 0
    assert len(bi._WINDOW_CACHE) == 0
    assert len(bi._PREPROCESS_CACHE) == 0


def test_fallback_discovery_does_not_walk_every_file(tmp_path, monkeypatch):
    import data.bids_ingest as bi
    import mne_bids

    eeg_dir = tmp_path / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    edf = eeg_dir / "sub-01_task-x_eeg.edf"
    edf.write_bytes(b"0")
    for i in range(200):
        (tmp_path / f"noise_{i}.bin").write_bytes(b"x")

    walked = {"n": 0}
    real_rglob = Path.rglob

    def counting_rglob(self, pattern):
        walked["n"] += 1
        return real_rglob(self, pattern)

    monkeypatch.setattr(mne_bids, "find_matching_paths", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("force")))
    monkeypatch.setattr(Path, "rglob", counting_rglob)
    recs = bi.discover_bids_eeg(str(tmp_path))
    assert len(recs) == 1
    assert recs[0].task_label == "x"
    assert walked["n"] == 0, "BIDS eeg/ dirs must short-circuit the unbounded rglob"
