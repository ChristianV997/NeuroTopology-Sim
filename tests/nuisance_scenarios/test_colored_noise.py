"""Tests for colored noise generation, DC handling, and spectral slope estimation."""
from __future__ import annotations

import numpy as np
import pytest

from sim.nuisance_scenarios.colored_noise import (
    SpectralSlopeFit,
    estimate_spectral_slope,
    generate_colored_noise,
)


def test_dc_component_is_zero() -> None:
    """Verifies that the DC frequency component X(0) is strictly zero."""
    for n_samples in (200, 201):  # even and odd
        noise = generate_colored_noise(n_samples=n_samples, chi=1.0, n_channels=2, seed=42)
        fft_vals = np.fft.rfft(noise, axis=-1)
        # DC bin at index 0 must be 0 + 0j before standardization
        # In time domain, mean must be zero within floating point precision
        for ch in range(2):
            assert np.mean(noise[ch]) == pytest.approx(0.0, abs=1e-10)


def test_even_and_odd_sample_counts() -> None:
    """Verifies valid generation for both even and odd sample counts without error."""
    for n in (128, 129, 500, 501):
        noise = generate_colored_noise(n_samples=n, chi=1.5, n_channels=3, seed=10)
        assert noise.shape == (3, n)
        assert np.all(np.isfinite(noise))


def test_unit_variance_standardization() -> None:
    """Verifies that each channel is standardized to approximately unit variance."""
    noise = generate_colored_noise(n_samples=2000, chi=1.0, n_channels=4, seed=100)
    for ch in range(4):
        std_val = float(np.std(noise[ch], ddof=1))
        assert std_val == pytest.approx(1.0, rel=1e-3)


@pytest.mark.parametrize("chi", [0.0, 1.0, 1.5, 2.0])
def test_spectral_slope_estimation(chi: float) -> None:
    """Verifies that empirical spectral slope recovers nominal chi within statistical tolerance."""
    # Use longer signal (8000 samples) and 16 channels to average out periodogram variance
    noise = generate_colored_noise(
        n_samples=8000,
        chi=chi,
        n_channels=16,
        sfreq_hz=500.0,
        seed=123,
    )
    slope_fit = estimate_spectral_slope(noise, sfreq_hz=500.0, f_min=2.0, f_max=150.0)
    assert isinstance(slope_fit, SpectralSlopeFit)
    assert np.isfinite(slope_fit.estimated_chi)

    # For white noise (chi=0), slope should be around 0.0 (+- 0.25)
    # For colored noise (chi=1.0, 1.5, 2.0), estimated chi should match within +- 0.35
    assert slope_fit.estimated_chi == pytest.approx(chi, abs=0.35)

    if chi >= 1.0:
        # High slope should have strong linear fit in log-log domain
        assert slope_fit.fit_r2 > 0.65


def test_invalid_parameters_raise_value_error() -> None:
    """Verifies that invalid generation arguments fail fast with ValueError."""
    with pytest.raises(ValueError, match="n_samples"):
        generate_colored_noise(n_samples=3, chi=1.0)

    with pytest.raises(ValueError, match="n_channels"):
        generate_colored_noise(n_samples=100, chi=1.0, n_channels=0)

    with pytest.raises(ValueError, match="chi"):
        generate_colored_noise(n_samples=100, chi=-0.5)

    with pytest.raises(ValueError, match="sfreq_hz"):
        generate_colored_noise(n_samples=100, chi=1.0, sfreq_hz=-10.0)


def test_sampling_rate_alias_conflict_fails_closed() -> None:
    with pytest.raises(ValueError, match="conflict"):
        generate_colored_noise(
            n_samples=100,
            chi=1.0,
            sfreq_hz=100.0,
            sampling_rate_hz=200.0,
        )


def test_seed_and_rng_aliases_cannot_both_be_supplied() -> None:
    with pytest.raises(ValueError, match="seed.*rng"):
        generate_colored_noise(n_samples=100, chi=1.0, seed=42, rng=43)


def test_generator_rejects_boolean_numeric_inputs() -> None:
    with pytest.raises(ValueError, match="n_channels"):
        generate_colored_noise(n_samples=100, chi=1.0, n_channels=True)
    with pytest.raises(ValueError, match="chi"):
        generate_colored_noise(n_samples=100, chi=True)
    with pytest.raises(ValueError, match="sfreq_hz"):
        generate_colored_noise(n_samples=100, chi=1.0, sfreq_hz=True)
    with pytest.raises(ValueError, match="chi"):
        generate_colored_noise(n_samples=100, chi=10**400)


def test_extreme_exponent_fails_closed_when_spectrum_underflows() -> None:
    with pytest.raises(ValueError, match="chi"):
        generate_colored_noise(
            n_samples=100,
            chi=1000.0,
            n_channels=2,
            sfreq_hz=1000.0,
        )


def test_estimate_spectral_slope_edge_cases() -> None:
    """Verifies error handling on invalid signals in estimate_spectral_slope."""
    with pytest.raises(ValueError, match="too short"):
        estimate_spectral_slope(np.zeros((1, 5)), sfreq_hz=100.0)

    with pytest.raises(ValueError, match="non-finite"):
        bad_sig = np.ones((2, 100))
        bad_sig[0, 10] = np.nan
        estimate_spectral_slope(bad_sig, sfreq_hz=100.0)

    # Signal where all valid frequencies are masked
    short_band = estimate_spectral_slope(np.ones((1, 20)), sfreq_hz=100.0, f_min=45.0, f_max=46.0)
    assert np.isnan(short_band.estimated_chi)


def test_estimate_spectral_slope_rejects_invalid_sampling_rate() -> None:
    with pytest.raises(ValueError, match="sfreq_hz"):
        estimate_spectral_slope(np.ones(20), sfreq_hz=0.0)
