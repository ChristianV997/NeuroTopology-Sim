"""Tests for data/preprocessing.py -- real bandpass/notch filtering and
re-referencing, applied to the FULL recording before windowing. Every metric
this repo's dataset-report pipelines have computed so far was computed
without any of this; these tests prove the instrument actually removes what
it claims to remove on synthetic signals with a known, injected answer.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_HAVE_MNE = importlib.util.find_spec("mne") is not None
pytestmark = pytest.mark.skipif(not _HAVE_MNE, reason="requires mne")


def _make_raw(data: np.ndarray, sfreq: float = 250.0, ch_names=None):
    import mne

    n_ch = data.shape[0]
    ch_names = ch_names or [f"EEG{i:03d}" for i in range(n_ch)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    return mne.io.RawArray(data, info, verbose="ERROR")


def test_bandpass_removes_low_frequency_drift():
    """A slow linear drift (well below the 0.5 Hz high-pass edge) plus a
    10 Hz oscillation: after preprocess_raw's default bandpass, the drift's
    huge low-frequency energy must be gone, leaving a signal centered near
    zero rather than ramping."""
    from data.preprocessing import preprocess_raw

    sfreq = 250.0
    t = np.arange(0, 20, 1 / sfreq)
    drift = 50.0 * (t / t[-1])  # large slow ramp, 0 -> 50 over 20s (~0.05 Hz-scale trend)
    oscillation = 2.0 * np.sin(2 * np.pi * 10 * t)
    data = np.array([drift + oscillation, drift + oscillation * 0.8])

    raw = _make_raw(data.copy(), sfreq=sfreq)
    preprocess_raw(raw, l_freq=0.5, h_freq=45.0, notch_freq=None, reference=None)
    filtered = raw.get_data()

    # Drift dominates the raw signal's range; after high-pass it must not.
    raw_range = data[0].max() - data[0].min()
    filtered_range = filtered[0].max() - filtered[0].min()
    assert filtered_range < raw_range * 0.5

    # The first and second halves of the raw (drifting) signal have very
    # different means; after high-pass filtering they should not.
    raw_half_diff = abs(data[0][: len(t) // 2].mean() - data[0][len(t) // 2 :].mean())
    filtered_half_diff = abs(filtered[0][: len(t) // 2].mean() - filtered[0][len(t) // 2 :].mean())
    assert filtered_half_diff < raw_half_diff * 0.3


def test_notch_filter_removes_line_noise():
    """Inject real 50 Hz line noise into a broadband-ish base signal; after
    notch_freq=50.0, spectral power at 50 Hz must drop substantially
    (verified via a real Welch PSD, not just eyeballing the time series)."""
    from scipy.signal import welch

    from data.preprocessing import preprocess_raw

    sfreq = 250.0
    t = np.arange(0, 10, 1 / sfreq)
    rng = np.random.default_rng(0)
    base = rng.standard_normal(t.size) * 0.1
    line_noise = 3.0 * np.sin(2 * np.pi * 50.0 * t)
    data = np.array([base + line_noise])

    raw = _make_raw(data.copy(), sfreq=sfreq)
    preprocess_raw(raw, l_freq=None, h_freq=None, notch_freq=50.0, reference=None)
    filtered = raw.get_data()

    freqs_raw, psd_raw = welch(data[0], fs=sfreq, nperseg=512)
    freqs_filt, psd_filt = welch(filtered[0], fs=sfreq, nperseg=512)

    idx = np.argmin(np.abs(freqs_raw - 50.0))
    power_raw_50hz = psd_raw[idx]
    power_filt_50hz = psd_filt[idx]
    assert power_filt_50hz < power_raw_50hz * 0.1


def test_average_reference_zeroes_cross_channel_mean():
    """After common-average referencing, the mean across channels at every
    timepoint must be ~0 -- the defining property of average referencing."""
    from data.preprocessing import preprocess_raw

    sfreq = 250.0
    n_samples = 1000
    rng = np.random.default_rng(1)
    data = rng.standard_normal((4, n_samples)) + np.array([[5.0], [-3.0], [1.0], [2.0]])

    raw = _make_raw(data.copy(), sfreq=sfreq)
    preprocess_raw(raw, l_freq=None, h_freq=None, notch_freq=None, reference="average")
    referenced = raw.get_data()

    cross_channel_mean = referenced.mean(axis=0)
    assert np.allclose(cross_channel_mean, 0.0, atol=1e-10)


def test_reference_none_skips_rereferencing():
    from data.preprocessing import preprocess_raw

    sfreq = 250.0
    rng = np.random.default_rng(2)
    data = rng.standard_normal((3, 500)) + np.array([[5.0], [-3.0], [1.0]])

    raw = _make_raw(data.copy(), sfreq=sfreq)
    preprocess_raw(raw, l_freq=None, h_freq=None, notch_freq=None, reference=None)
    result = raw.get_data()
    assert np.allclose(result, data)


def test_no_filtering_when_both_edges_none():
    """l_freq=h_freq=None must skip filtering entirely (not raise), leaving
    only whatever notch/reference steps were requested."""
    from data.preprocessing import preprocess_raw

    sfreq = 250.0
    rng = np.random.default_rng(3)
    data = rng.standard_normal((2, 500))

    raw = _make_raw(data.copy(), sfreq=sfreq)
    preprocess_raw(raw, l_freq=None, h_freq=None, notch_freq=None, reference=None)
    assert np.allclose(raw.get_data(), data)
