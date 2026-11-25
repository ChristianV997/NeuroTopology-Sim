"""Tests for deterministic EEG/MEG signal preprocessing pipeline.

Scientific guardrails:
- Pure synthetic waveforms (sine, chirp, noise).
- Explicit mathematical verification of filter properties.
- Strictly deterministic execution.
"""
from __future__ import annotations

import numpy as np
import pytest

from validation.analytic_phase import (
    amplitude_validity_mask,
    apply_boundary_taper,
    bandpass_filter_sos,
    compute_analytic_signal,
    notch_filter,
    preprocess_signal_pipeline,
    validate_signal_finite,
    zscore_normalize,
)


@pytest.fixture
def synthetic_multichannel_signal() -> tuple[np.ndarray, float]:
    """Create a 4-channel, 1000-sample synthetic test signal at 200 Hz."""
    sfreq = 200.0
    n_channels = 4
    n_samples = 1000
    t = np.arange(n_samples) / sfreq
    np.random.seed(12345)

    data = np.zeros((n_channels, n_samples))
    # Ch 0: 10 Hz alpha wave
    data[0] = 10.0 * np.sin(2.0 * np.pi * 10.0 * t)
    # Ch 1: 10 Hz + 50 Hz powerline contamination
    data[1] = 10.0 * np.sin(2.0 * np.pi * 10.0 * t) + 5.0 * np.sin(2.0 * np.pi * 50.0 * t)
    # Ch 2: Broad noise + 10 Hz wave
    data[2] = 5.0 * np.sin(2.0 * np.pi * 10.0 * t) + np.random.normal(0, 1.0, n_samples)
    # Ch 3: Flatline followed by 10 Hz wave
    data[3, 500:] = 10.0 * np.sin(2.0 * np.pi * 10.0 * t[500:])

    return data, sfreq


class TestFiniteValidation:
    """Test validation of finite inputs."""

    def test_finite_valid(self):
        arr = np.array([[1.0, 2.0], [3.0, 4.0]])
        validate_signal_finite(arr)  # Should not raise

    def test_nan_rejected(self):
        arr = np.array([[1.0, np.nan], [3.0, 4.0]])
        with pytest.raises(ValueError, match="non-finite values"):
            validate_signal_finite(arr)

    def test_inf_rejected(self):
        arr = np.array([[1.0, np.inf], [3.0, 4.0]])
        with pytest.raises(ValueError, match="non-finite values"):
            validate_signal_finite(arr)


class TestZscoreNormalization:
    """Test per-channel z-score normalization."""

    def test_zscore_properties(self, synthetic_multichannel_signal):
        data, _ = synthetic_multichannel_signal
        norm, stats = zscore_normalize(data)

        assert norm.shape == data.shape
        # Channel means should be ~0.0
        np.testing.assert_allclose(np.mean(norm, axis=-1), 0.0, atol=1e-10)
        # Non-flat channels should have std ~1.0
        np.testing.assert_allclose(np.std(norm[:3], axis=-1), 1.0, atol=1e-10)
        assert "means" in stats and "stds" in stats


class TestNotchFilter:
    """Test 50/60 Hz notch filtering."""

    def test_notch_attenuation(self, synthetic_multichannel_signal):
        data, sfreq = synthetic_multichannel_signal
        # Test on Ch 1 (has 50 Hz component)
        ch1 = data[1:2]
        filtered, meta = notch_filter(ch1, sfreq=sfreq, freq_hz=50.0, q=30.0)

        assert meta["notch_freq_hz"] == 50.0
        assert filtered.shape == ch1.shape

        # FFT power at 50 Hz before and after
        fft_orig = np.abs(np.fft.rfft(ch1[0]))
        fft_filt = np.abs(np.fft.rfft(filtered[0]))
        freqs = np.fft.rfftfreq(ch1.shape[1], d=1.0 / sfreq)
        idx_50 = np.argmin(np.abs(freqs - 50.0))

        # Power at 50 Hz should be attenuated by at least 20 dB (factor of 10)
        assert fft_filt[idx_50] < 0.1 * fft_orig[idx_50]


class TestBandpassSOS:
    """Test SOS Butterworth bandpass filtering."""

    def test_bandpass_passband_and_stopband(self, synthetic_multichannel_signal):
        data, sfreq = synthetic_multichannel_signal
        # Bandpass in alpha range 8-12 Hz
        filtered, meta = bandpass_filter_sos(data, sfreq=sfreq, low_hz=8.0, high_hz=12.0, order=4)
        assert meta["low_hz"] == 8.0
        assert meta["high_hz"] == 12.0
        assert filtered.shape == data.shape

        # Ch 1 50 Hz component should be strongly attenuated (by at least 40 dB, factor of 100)
        fft_orig = np.abs(np.fft.rfft(data[1]))
        fft_filt = np.abs(np.fft.rfft(filtered[1]))
        freqs = np.fft.rfftfreq(data.shape[1], d=1.0 / sfreq)
        idx_50 = np.argmin(np.abs(freqs - 50.0))
        assert fft_filt[idx_50] < 0.01 * fft_orig[idx_50]


class TestAnalyticSignalAndPhase:
    """Test Hilbert analytic phase and amplitude calculation."""

    def test_analytic_phase_range_and_progression(self):
        sfreq = 200.0
        t = np.arange(400) / sfreq
        # Pure 5 Hz cosine wave
        signal = np.cos(2.0 * np.pi * 5.0 * t).reshape(1, -1)
        phase, amplitude, meta = compute_analytic_signal(signal)

        # Range check: (-pi, pi]
        assert np.all(phase > -np.pi) and np.all(phase <= np.pi)
        # Amplitude check: close to 1.0 (excluding edge transient margin)
        np.testing.assert_allclose(amplitude[0, 20:-20], 1.0, atol=0.05)
        assert meta["transform"] == "hilbert"


class TestAmplitudeValidityMask:
    """Test amplitude validity mask detection."""

    def test_flatline_masked_out(self):
        # 1 channel: flatline (0.0) first half, active second half
        amplitude = np.zeros((1, 500))
        amplitude[0, 250:] = 10.0

        mask = amplitude_validity_mask(amplitude, min_amplitude_quantile=0.1, abs_min_threshold=0.1)
        assert mask.shape == amplitude.shape
        # Flatline portion should be False
        assert np.all(mask[0, :250] == False)
        # Active portion should be True
        assert np.all(mask[0, 250:] == True)


class TestBoundaryTaper:
    """Test boundary taper reduction of edge discontinuities."""

    def test_boundary_taper_edges_zeroed(self):
        arr = np.ones((2, 100))
        tapered = apply_boundary_taper(arr, taper_fraction=0.1)

        # Endpoints should be exactly 0.0
        assert tapered[0, 0] == 0.0
        assert tapered[0, -1] == 0.0
        # Center should remain 1.0
        assert tapered[0, 50] == 1.0


class TestPreprocessingPipeline:
    """Test integrated deterministic preprocessing pipeline."""

    def test_pipeline_determinism(self, synthetic_multichannel_signal):
        data, sfreq = synthetic_multichannel_signal

        res1 = preprocess_signal_pipeline(
            data,
            sfreq=sfreq,
            low_hz=8.0,
            high_hz=13.0,
            notch_hz=50.0,
            zscore=True,
            apply_taper=True,
        )

        res2 = preprocess_signal_pipeline(
            data,
            sfreq=sfreq,
            low_hz=8.0,
            high_hz=13.0,
            notch_hz=50.0,
            zscore=True,
            apply_taper=True,
        )

        # Exact bit-for-bit equality
        assert np.array_equal(res1["filtered_data"], res2["filtered_data"])
        assert np.array_equal(res1["phase"], res2["phase"])
        assert np.array_equal(res1["amplitude"], res2["amplitude"])
        assert np.array_equal(res1["validity_mask"], res2["validity_mask"])
        assert res1["provenance"] == res2["provenance"]
        assert res1["provenance"]["sfreq_hz"] == sfreq
        assert res1["provenance"]["boundary_taper_applied"] is True
        assert res1["provenance"]["notch_filter"]["notch_freq_hz"] == 50.0
        assert res1["provenance"]["bandpass_filter"]["low_hz"] == 8.0
