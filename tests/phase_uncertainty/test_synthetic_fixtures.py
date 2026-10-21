"""Tests for synthetic narrowband signal fixtures.

Verifies mathematical properties of synthetic signal generators:
1. Stationary narrowband signals
2. Amplitude-modulated signals
3. Frequency drift signals
4. Near-zero amplitude notches
5. Colored noise signals
6. Short window bursts
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.phase_uncertainty import (
    get_all_calibration_fixtures,
    make_amplitude_modulated_signal,
    make_colored_noise_signal,
    make_frequency_drift_signal,
    make_near_zero_amplitude_signal,
    make_short_window_burst,
    make_stationary_narrowband,
)


def test_stationary_narrowband_properties() -> None:
    """Stationary narrowband fixture produces valid complex signal and ground-truth phase."""
    fix = make_stationary_narrowband(n_samples=500, fs=1000.0, f0=12.0, snr_db=15.0, seed=10)
    assert fix.signal.shape == (500,)
    assert np.iscomplexobj(fix.signal)
    assert fix.true_phase.shape == (500,)
    assert fix.true_amplitude.shape == (500,)
    assert fix.true_frequency.shape == (500,)
    assert np.all(fix.true_frequency == 12.0)


def test_amplitude_modulated_envelope_bounds() -> None:
    """Amplitude modulated fixture has envelope varying between 1 - depth and 1 + depth."""
    depth = 0.6
    fix = make_amplitude_modulated_signal(n_samples=1000, f0=10.0, f_mod=2.0, depth=depth, seed=11)
    min_amp = float(np.min(fix.true_amplitude))
    max_amp = float(np.max(fix.true_amplitude))

    assert min_amp == pytest.approx(1.0 - depth, abs=1e-3)
    assert max_amp == pytest.approx(1.0 + depth, abs=1e-3)


def test_frequency_drift_monotonicity() -> None:
    """Frequency drift fixture has monotonically increasing carrier frequency."""
    fix = make_frequency_drift_signal(n_samples=800, f_start=8.0, f_end=16.0, seed=12)
    assert fix.true_frequency[0] == pytest.approx(8.0, abs=1e-3)
    assert fix.true_frequency[-1] == pytest.approx(16.0, abs=0.1)
    assert np.all(np.diff(fix.true_frequency) > 0.0)


def test_near_zero_amplitude_notch() -> None:
    """Near-zero amplitude fixture has notch where amplitude drops below 1e-3."""
    fix = make_near_zero_amplitude_signal(n_samples=600, dip_start=200, dip_len=150, seed=13)
    assert np.all(fix.true_amplitude[200:350] <= 1e-3)
    assert np.all(fix.true_amplitude[:190] == 1.0)
    assert np.all(fix.true_amplitude[360:] == 1.0)


def test_colored_noise_lag1_autocorrelation() -> None:
    """Colored noise fixture produces positively correlated noise."""
    ar_coef = 0.8
    fix = make_colored_noise_signal(n_samples=2000, ar_coef=ar_coef, snr_db=6.0, seed=14)
    # Extract noise component
    clean_z = fix.true_amplitude * np.exp(1j * fix.true_phase)
    noise_z = fix.signal - clean_z
    noise_real = np.real(noise_z)

    # Compute lag-1 empirical autocorrelation
    c0 = np.mean(noise_real ** 2)
    c1 = np.mean(noise_real[:-1] * noise_real[1:])
    r1 = c1 / c0

    # For AR(1) with rho=0.8, theoretical lag-1 correlation is ~0.8
    assert r1 > 0.65


def test_short_window_burst() -> None:
    """Short burst fixture has exactly 64 samples."""
    fix = make_short_window_burst(n_samples=64, seed=15)
    assert len(fix.signal) == 64
    assert len(fix.true_phase) == 64


def test_get_all_calibration_fixtures_completeness() -> None:
    """Standard calibration battery contains all 8 required fixtures."""
    fixtures = get_all_calibration_fixtures()
    assert len(fixtures) == 8
    for fix in fixtures:
        assert len(fix.signal) > 0
        assert np.all(np.isfinite(fix.signal))
        assert np.all(np.isfinite(fix.true_phase))
