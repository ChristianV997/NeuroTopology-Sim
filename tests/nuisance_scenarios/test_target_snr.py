"""Tests for signal-to-noise ratio mixer, scaling precision, and error conditions."""
from __future__ import annotations

import numpy as np
import pytest

from sim.nuisance_scenarios.snr_mixer import (
    MixedSignalResult,
    compute_signal_power,
    mix_at_target_snr,
)


@pytest.mark.parametrize("target_snr", [-20.0, -10.0, -3.0, 0.0, 6.0, 15.0, 25.0])
def test_realized_snr_precision(target_snr: float) -> None:
    """Verifies that realized SNR matches requested target SNR within numerical tolerance."""
    rng = np.random.default_rng(42)
    clean = rng.standard_normal((4, 1000))
    raw_noise = rng.standard_normal((4, 1000))

    res = mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=target_snr)

    assert isinstance(res, MixedSignalResult)
    assert res.realized_snr_db == pytest.approx(target_snr, abs=1e-6)
    # Check manual ratio computation
    p_s = np.mean(clean ** 2)
    p_n = np.mean(res.scaled_noise ** 2)
    expected_snr = 10.0 * np.log10(p_s / p_n)
    assert res.realized_snr_db == pytest.approx(expected_snr, abs=1e-9)


def test_constant_non_zero_signal_mixing() -> None:
    """Verifies that a constant non-zero signal has defined power and mixes at target SNR."""
    clean = np.full((2, 500), fill_value=3.0)  # Power = 9.0
    rng = np.random.default_rng(123)
    raw_noise = rng.standard_normal((2, 500))

    res = mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=10.0)
    assert res.signal_power == pytest.approx(9.0, abs=1e-12)
    assert res.realized_snr_db == pytest.approx(10.0, abs=1e-6)


def test_zero_signal_raises_error() -> None:
    """Verifies that a zero-power signal raises ValueError (undefined SNR)."""
    clean = np.zeros((2, 100))
    raw_noise = np.ones((2, 100))

    with pytest.raises(ValueError, match="near-zero or zero power"):
        mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=0.0)


def test_zero_noise_raises_error() -> None:
    """Verifies that zero-power noise raises ValueError (cannot scale)."""
    clean = np.ones((2, 100))
    raw_noise = np.zeros((2, 100))

    with pytest.raises(ValueError, match="near-zero or zero power"):
        mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=0.0)


def test_shape_mismatch_raises_error() -> None:
    """Verifies that mismatched signal and noise shapes raise ValueError."""
    clean = np.ones((2, 100))
    raw_noise = np.ones((3, 100))

    with pytest.raises(ValueError, match="Shape mismatch"):
        mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=0.0)


def test_non_finite_inputs_raise_error() -> None:
    """Verifies that NaN or Inf in inputs raises ValueError."""
    clean = np.ones((2, 100))
    clean[0, 5] = np.nan
    raw_noise = np.ones((2, 100))

    with pytest.raises(ValueError, match="non-finite"):
        mix_at_target_snr(signal=clean, noise=raw_noise, target_snr_db=0.0)

    clean_ok = np.ones((2, 100))
    raw_noise_inf = np.ones((2, 100))
    raw_noise_inf[1, 10] = np.inf

    with pytest.raises(ValueError, match="non-finite"):
        mix_at_target_snr(signal=clean_ok, noise=raw_noise_inf, target_snr_db=0.0)
