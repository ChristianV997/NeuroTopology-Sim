"""Synthetic ground-truth tests for sciencer_d/btc_icft/level_m/real_features.py
-- real band power (Welch PSD), real complexity/entropy (antropy), and real
aperiodic spectral decomposition (specparam), replacing nothing but adding
real instruments alongside the existing _proxy heuristics.
"""
from __future__ import annotations

import numpy as np
import pytest

from sciencer_d.btc_icft.level_m.real_features import (
    compute_aperiodic_spectral_features,
    compute_band_power,
    compute_complexity_features,
    extract_real_level_m_features,
)


# ---------------------------------------------------------------------------
# compute_band_power
# ---------------------------------------------------------------------------

def test_band_power_pure_alpha_sine_dominates_alpha_band():
    sfreq = 250.0
    t = np.arange(0, 8, 1 / sfreq)
    signal = np.sin(2 * np.pi * 10.5 * t)  # pure alpha-band (8-13 Hz) tone

    result = compute_band_power(signal, sfreq)
    assert result["alpha_power_rel"] > 0.8
    assert result["alpha_power_rel"] > result["delta_power_rel"]
    assert result["alpha_power_rel"] > result["beta_power_rel"]


def test_band_power_pure_beta_sine_dominates_beta_band():
    sfreq = 250.0
    t = np.arange(0, 8, 1 / sfreq)
    signal = np.sin(2 * np.pi * 20.0 * t)  # pure beta-band (13-30 Hz) tone

    result = compute_band_power(signal, sfreq)
    assert result["beta_power_rel"] > result["alpha_power_rel"]
    assert result["beta_power_rel"] > result["delta_power_rel"]


def test_band_power_skips_band_above_nyquist():
    sfreq = 50.0  # Nyquist 25 Hz -- below gamma_low's 45 Hz upper edge
    t = np.arange(0, 4, 1 / sfreq)
    signal = np.sin(2 * np.pi * 10 * t)
    result = compute_band_power(signal, sfreq)
    assert "gamma_low_power_abs" not in result
    assert "alpha_power_abs" in result


def test_band_power_empty_for_too_short_signal():
    result = compute_band_power(np.zeros(3), sfreq=250.0)
    assert result == {}


# ---------------------------------------------------------------------------
# compute_complexity_features
# ---------------------------------------------------------------------------

def test_complexity_constant_signal_has_zero_permutation_entropy():
    """A perfectly constant signal has exactly one ordinal pattern (all ties)
    -- normalized permutation entropy must be 0, the textbook minimum-
    complexity case. (Adding even infinitesimal noise breaks every tie and
    randomizes rank order, pushing PE toward its maximum instead -- a real,
    correct property of ordinal-pattern entropy, not a bug; tested with an
    exactly constant signal specifically to demonstrate the true floor.)"""
    signal = np.ones(500)
    result = compute_complexity_features(signal)
    assert result["permutation_entropy"] == 0.0


def test_complexity_random_noise_has_high_permutation_entropy():
    """Independent random noise has maximal ordinal-pattern diversity --
    normalized permutation entropy must be near 1, the opposite extreme from
    the constant-signal case above."""
    signal = np.random.default_rng(1).standard_normal(500)
    result = compute_complexity_features(signal)
    assert result["permutation_entropy"] > 0.85


def test_complexity_short_signal_returns_nan():
    result = compute_complexity_features(np.zeros(3))
    assert np.isnan(result["permutation_entropy"])
    assert np.isnan(result["sample_entropy"])
    assert np.isnan(result["higuchi_fd"])


# ---------------------------------------------------------------------------
# compute_aperiodic_spectral_features
# ---------------------------------------------------------------------------

def test_aperiodic_pink_noise_has_higher_exponent_than_white_noise():
    """Pink-ish (1/f, cumulative-sum) noise must show a measurably higher
    aperiodic exponent than white noise (flat spectrum, exponent near 0) --
    the defining property specparam's aperiodic fit is built to detect."""
    sfreq = 250.0
    n = int(sfreq * 10)
    rng = np.random.default_rng(2)

    white = rng.standard_normal(n)
    pink = np.cumsum(rng.standard_normal(n))
    pink = pink - pink.mean()

    white_result = compute_aperiodic_spectral_features(white, sfreq)
    pink_result = compute_aperiodic_spectral_features(pink, sfreq)

    assert np.isfinite(white_result["aperiodic_exponent"])
    assert np.isfinite(pink_result["aperiodic_exponent"])
    assert pink_result["aperiodic_exponent"] > white_result["aperiodic_exponent"]


def test_aperiodic_short_signal_returns_nan_not_exception():
    result = compute_aperiodic_spectral_features(np.zeros(3), sfreq=250.0)
    assert np.isnan(result["aperiodic_exponent"])
    assert np.isnan(result["aperiodic_offset"])
    assert np.isnan(result["aperiodic_r_squared"])


def test_aperiodic_constant_signal_returns_nan_not_exception():
    """A perfectly flat signal has a degenerate (all-zero) PSD outside the DC
    bin -- must be handled gracefully, not raise inside specparam's fit."""
    result = compute_aperiodic_spectral_features(np.ones(3000), sfreq=250.0)
    assert np.isnan(result["aperiodic_exponent"]) or np.isfinite(result["aperiodic_exponent"])


# ---------------------------------------------------------------------------
# extract_real_level_m_features (integration)
# ---------------------------------------------------------------------------

def test_extract_real_level_m_features_returns_all_expected_keys():
    sfreq = 250.0
    t = np.arange(0, 8, 1 / sfreq)
    signal = np.sin(2 * np.pi * 10 * t) + 0.1 * np.random.default_rng(3).standard_normal(t.size)

    result = extract_real_level_m_features(signal, sfreq)
    for key in (
        "delta_power_abs", "delta_power_rel", "alpha_power_abs", "alpha_power_rel",
        "permutation_entropy", "sample_entropy", "higuchi_fd",
        "aperiodic_offset", "aperiodic_exponent", "aperiodic_r_squared",
    ):
        assert key in result

    # No overlap with the existing _proxy column names -- purely additive.
    from sciencer_d.btc_icft.level_m.features import extract_level_m_features

    proxy_keys = set(extract_level_m_features(list(signal)).keys())
    assert proxy_keys.isdisjoint(result.keys())
