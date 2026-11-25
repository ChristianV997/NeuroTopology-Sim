"""Signal-processing semantics and documented edge-effect behaviour."""
from __future__ import annotations

import numpy as np
import pytest

from tests.performance.streaming_optimization.conftest import requires_mne

pytestmark = requires_mne


@pytest.fixture
def recording_path(tmp_path):
    from tests.fixtures.make_synthetic_bids import build
    from data.bids_ingest import clear_raw_cache, discover_bids_eeg

    root = build(str(tmp_path / "bids"), subjects=("01",), states=("awake",))
    path = discover_bids_eeg(str(root))[0].path
    clear_raw_cache()
    return path


def test_default_preprocess_none_is_byte_identical(recording_path):
    from data.bids_ingest import read_window_signal

    a = read_window_signal(recording_path, 0.0, 2.0, pick="all", max_channels=4)
    b = read_window_signal(recording_path, 0.0, 2.0, pick="all", max_channels=4, preprocess=None)
    assert np.array_equal(a, b)


def test_preprocess_opt_in_changes_samples_but_not_shape(recording_path):
    from data.bids_ingest import read_window_signal

    raw = read_window_signal(recording_path, 0.0, 4.0, pick="all", max_channels=4)
    filtered = read_window_signal(
        recording_path,
        0.0,
        4.0,
        pick="all",
        max_channels=4,
        preprocess={"l_freq": 0.5, "h_freq": 45.0, "reference": "average"},
    )
    assert raw.shape == filtered.shape
    assert not np.array_equal(raw, filtered)


def test_full_recording_filter_differs_from_per_window_filter(recording_path):
    """Edge-effect contract: filter the continuous recording, then slice.

    Per-window filtering is cheaper but injects filter transients at every
    window boundary. This test records that those two procedures are not
    interchangeable; the ingest path must keep the full-recording order.
    """
    import mne
    from data.bids_ingest import _read_raw, read_window_signal
    from data.preprocessing import preprocess_raw

    kwargs = {"l_freq": 1.0, "h_freq": 40.0, "reference": None}
    ingest = read_window_signal(
        recording_path, 2.0, 4.0, pick="all", max_channels=4, preprocess=kwargs
    )

    raw = _read_raw(recording_path)
    preprocess_raw(raw, **kwargs)
    picks = mne.pick_types(raw.info, eeg=True)[:4]
    sfreq = float(raw.info["sfreq"])
    start = int(round(2.0 * sfreq))
    stop = int(round(4.0 * sfreq))
    full_then_slice = np.asarray(raw.get_data(picks=picks, start=start, stop=stop), dtype=float)
    assert np.allclose(ingest, full_then_slice, rtol=0, atol=0)

    sliced = _read_raw(recording_path)
    data = sliced.get_data(picks=picks, start=start, stop=stop)
    info = mne.create_info(
        ch_names=[sliced.ch_names[i] for i in picks],
        sfreq=sfreq,
        ch_types="eeg",
    )
    window_raw = mne.io.RawArray(data, info, verbose="ERROR")
    preprocess_raw(window_raw, **kwargs)
    per_window = np.asarray(window_raw.get_data(), dtype=float)
    assert ingest.shape == per_window.shape
    assert not np.allclose(ingest, per_window, rtol=0, atol=1e-12)


def test_cached_non_preprocess_read_matches_fresh_get_data(recording_path):
    import mne
    from data.bids_ingest import _read_raw, clear_raw_cache, read_window_signal

    clear_raw_cache()
    cached = read_window_signal(recording_path, 0.0, 2.0, pick="all", max_channels=4)
    raw = _read_raw(recording_path)
    picks = mne.pick_types(raw.info, eeg=True)[:4]
    sfreq = float(raw.info["sfreq"])
    fresh = raw.get_data(picks=picks, start=0, stop=int(round(2.0 * sfreq)))
    assert np.array_equal(cached, fresh)
