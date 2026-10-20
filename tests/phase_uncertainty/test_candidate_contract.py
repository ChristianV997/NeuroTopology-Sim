"""Tests for Round 6 candidate estimator contract, boundaries, and noise models.

Covers:
1. Shape validation (1D required)
2. Short signal rejection (length >= 4 required)
3. Non-finite value rejection (NaN / Inf)
4. Frame index boundary consistency (all output arrays match input length)
5. Phase wrapping constraint: phase in (-pi, pi]
6. Deterministic seed repeatability
7. Second-difference MAD noise model scaling (i.i.d. Gaussian vs colored noise)
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from tools.phase_uncertainty import (
    EstimatorConfig,
    UNIFORM_CIRCULAR_STD_CEILING,
    compute_analytic_signal,
    compute_mad,
    estimate_narrowband_phase_uncertainty,
    wrap_phase,
)


def test_shape_validation_rejects_multidimensional() -> None:
    """Estimator must reject 2D or 3D arrays with ValueError."""
    bad_2d = np.ones((10, 10), dtype=complex)
    with pytest.raises(ValueError, match="1D array"):
        estimate_narrowband_phase_uncertainty(bad_2d)

    bad_3d = np.ones((2, 5, 5), dtype=complex)
    with pytest.raises(ValueError, match="1D array"):
        estimate_narrowband_phase_uncertainty(bad_3d)


def test_short_signal_rejection() -> None:
    """Estimator requires at least 4 samples to compute second differences."""
    for n in (0, 1, 2, 3):
        short_sig = np.ones(n, dtype=complex)
        with pytest.raises(ValueError, match="length must be >= 4"):
            estimate_narrowband_phase_uncertainty(short_sig)


def test_nonfinite_rejection() -> None:
    """Estimator rejects NaN or Inf values immediately."""
    sig_nan = np.ones(50, dtype=complex)
    sig_nan[10] = np.nan + 1j * 0.0
    with pytest.raises(ValueError, match="NaN or infinite"):
        estimate_narrowband_phase_uncertainty(sig_nan)

    sig_inf = np.ones(50, dtype=complex)
    sig_inf[25] = np.inf + 1j * 1.0
    with pytest.raises(ValueError, match="NaN or infinite"):
        estimate_narrowband_phase_uncertainty(sig_inf)


def test_finite_input_that_overflows_derived_signal_fails_closed() -> None:
    """Finite samples that overflow intermediate math must not yield NaN outputs."""
    extreme_signal = np.full(8, 1e308, dtype=np.float64)

    with pytest.raises(ValueError, match="non-finite|finite"):
        estimate_narrowband_phase_uncertainty(extreme_signal)


def test_nonnumeric_signal_dtype_is_rejected_as_validation_error() -> None:
    with pytest.raises(ValueError, match="numeric"):
        estimate_narrowband_phase_uncertainty(np.array(["signal"] * 8))


def test_fs_must_be_positive_finite() -> None:
    """Sampling frequency must be finite and strictly positive (fail closed)."""
    z = np.exp(1j * np.linspace(0.0, 4.0 * np.pi, 64))
    for fs in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="fs"):
            estimate_narrowband_phase_uncertainty(z, fs=fs)


@pytest.mark.parametrize("fs", [True, "1000"], ids=["boolean", "numeric-string"])
def test_fs_rejects_coerced_non_numeric_scalars(fs: object) -> None:
    z = np.exp(1j * np.linspace(0.0, 4.0 * np.pi, 64))
    with pytest.raises(ValueError, match="fs"):
        estimate_narrowband_phase_uncertainty(z, fs=fs)


@pytest.mark.parametrize(
    "config_kwargs",
    [
        {"min_amplitude_floor": float("nan")},
        {"min_amplitude_floor": float("inf")},
        {"min_amplitude_floor": 0.0},
        {"mad_scale_factor": float("nan")},
        {"mad_scale_factor": 0.0},
        {"second_difference_factor": float("inf")},
        {"second_difference_factor": 0.0},
        {"jitter_window_len": 3.5},
        {"jitter_window_len": True},
        {"cap_at_uniform_std": 1},
    ],
    ids=[
        "nan-amplitude-floor", "infinite-amplitude-floor", "zero-amplitude-floor",
        "nan-mad-scale", "zero-mad-scale", "infinite-second-difference-factor",
        "zero-second-difference-factor", "fractional-window", "boolean-window",
        "non-boolean-cap",
    ],
)
def test_estimator_config_rejects_non_finite_or_invalid_values(config_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EstimatorConfig(**config_kwargs)


def test_wrap_phase_half_turn_matches_open_closed_interval() -> None:
    """Contract interval is (-π, π]: wrap(+π) must be +π, not -π."""
    assert float(wrap_phase(np.array([np.pi]))[0]) == pytest.approx(np.pi)
    assert float(wrap_phase(np.array([-np.pi]))[0]) == pytest.approx(np.pi)
    w = wrap_phase(np.array([-3.0 * np.pi, -np.pi, 0.0, np.pi, 3.0 * np.pi]))
    assert np.all(w > -np.pi)
    assert np.all(w <= np.pi)


def test_frame_index_boundary_consistency() -> None:
    """All output arrays must have identical length matching the input signal."""
    n = 250
    t = np.arange(n) / 1000.0
    z = np.exp(1j * 2.0 * np.pi * 10.0 * t)
    res = estimate_narrowband_phase_uncertainty(z, fs=1000.0)

    assert len(res.phase) == n
    assert len(res.phase_std) == n
    assert len(res.amplitude) == n
    assert len(res.instantaneous_freq) == n
    assert len(res.local_jitter) == n


def test_phase_wrapping_strict_bounds() -> None:
    """Output phase must lie strictly in (-pi, pi]."""
    rng = np.random.default_rng(123)
    n = 300
    z = rng.normal(size=n) + 1j * rng.normal(size=n)
    res = estimate_narrowband_phase_uncertainty(z, fs=1000.0)

    assert np.all(res.phase > -np.pi)
    assert np.all(res.phase <= np.pi)


def test_deterministic_seed_repeatability() -> None:
    """Estimator is strictly deterministic for identical inputs."""
    rng1 = np.random.default_rng(999)
    z1 = rng1.normal(size=200) + 1j * rng1.normal(size=200)

    rng2 = np.random.default_rng(999)
    z2 = rng2.normal(size=200) + 1j * rng2.normal(size=200)

    res1 = estimate_narrowband_phase_uncertainty(z1, fs=1000.0)
    res2 = estimate_narrowband_phase_uncertainty(z2, fs=1000.0)

    np.testing.assert_array_equal(res1.phase, res2.phase)
    np.testing.assert_array_equal(res1.phase_std, res2.phase_std)
    assert res1.median_freq == res2.median_freq
    assert res1.residual_noise_std == res2.residual_noise_std


def test_mad_second_difference_iid_scaling() -> None:
    """Under true i.i.d. Gaussian phase noise, second-difference MAD recovers sigma."""
    rng = np.random.default_rng(42)
    n = 10000
    true_sigma = 0.15
    noise = rng.normal(0.0, true_sigma, n)

    # Second difference: d2[n] = noise[n] - 2*noise[n-1] + noise[n-2]
    d2 = np.diff(np.diff(noise))
    mad_d2 = compute_mad(d2)

    # Theoretical relationship: sigma_hat = (1.4826 * MAD(d2)) / sqrt(6)
    sigma_hat = (1.482602218505602 * mad_d2) / math.sqrt(6.0)

    # Should recover true_sigma within ~5% for 10k samples
    assert sigma_hat == pytest.approx(true_sigma, rel=0.08)


def test_mad_second_difference_underestimates_colored_noise() -> None:
    """Positively correlated colored noise causes second-difference MAD to underestimate noise.

    This mathematically proves why the Round 6 candidate estimator is overconfident
    under colored / autoregressive noise.
    """
    rng = np.random.default_rng(42)
    n = 10000
    rho = 0.85
    # Generate AR(1) noise: e[n] ~ N(0, sigma_innov)
    target_sigma = 0.20
    var_innov = (target_sigma ** 2) * (1.0 - rho ** 2)
    sigma_innov = math.sqrt(var_innov)

    ar_noise = np.zeros(n)
    innov = rng.normal(0.0, sigma_innov, n)
    for i in range(1, n):
        ar_noise[i] = rho * ar_noise[i - 1] + innov[i]

    empirical_std = float(np.std(ar_noise))
    assert empirical_std == pytest.approx(target_sigma, rel=0.10)

    # Second difference of AR(1) noise
    d2 = np.diff(np.diff(ar_noise))
    mad_d2 = compute_mad(d2)
    sigma_hat_assumed_iid = (1.482602218505602 * mad_d2) / math.sqrt(6.0)

    # Because adjacent samples are positively correlated, Var(d2) < 6 * Var(noise).
    # The assumed i.i.d. formula severely underestimates the true noise:
    assert sigma_hat_assumed_iid < 0.70 * empirical_std
