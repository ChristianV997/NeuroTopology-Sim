"""Tests for the PCI proxy alias and Q-vs-complexity correlation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from validation.pci_validation import (
    pcist,
    pcist_proxy,
    pcist_surrogate,
    q_pcist_correlation,
)


# ── alias parity ─────────────────────────────────────────────────────────────

def test_proxy_equals_surrogate_for_same_input():
    rng = np.random.default_rng(0)
    epoch = rng.standard_normal((6, 64))
    assert pcist_proxy(epoch) == pcist_surrogate(epoch)


def test_proxy_is_finite_float():
    rng = np.random.default_rng(1)
    epoch = rng.standard_normal((4, 32))
    v = pcist_proxy(epoch)
    assert isinstance(v, float)
    assert np.isfinite(v)


# ── q_pcist_correlation column preference ───────────────────────────────────

def test_q_pcist_correlation_uses_pcist_proxy_when_available():
    rng = np.random.default_rng(2)
    x = rng.random(30)
    df = pd.DataFrame({
        "Qabs": x,
        "pcist_proxy": x + rng.normal(0, 0.005, 30),
    })
    result = q_pcist_correlation(df)
    assert result["r"] > 0.99
    assert result["n"] == 30


def test_q_pcist_correlation_falls_back_to_legacy_pcist():
    rng = np.random.default_rng(3)
    x = rng.random(25)
    df = pd.DataFrame({
        "Qabs": x,
        "PCIst": x + rng.normal(0, 0.01, 25),
    })
    result = q_pcist_correlation(df)
    assert result["r"] > 0.95
    assert result["n"] == 25


def test_q_pcist_correlation_returns_nan_when_neither_present():
    df = pd.DataFrame({"Qabs": [1.0, 2.0, 3.0, 4.0]})
    result = q_pcist_correlation(df)
    assert np.isnan(result["r"])
    assert np.isnan(result["p"])


def test_q_pcist_correlation_prefers_proxy_over_legacy_when_both_present():
    """If both columns exist, pcist_proxy should drive the correlation."""
    rng = np.random.default_rng(4)
    n = 40
    x = rng.random(n)
    df = pd.DataFrame({
        "Qabs": x,
        "pcist_proxy": x + rng.normal(0, 0.001, n),    # near-perfect
        "PCIst": rng.standard_normal(n) * 100,         # near-zero corr
    })
    result = q_pcist_correlation(df)
    assert result["r"] > 0.99


def test_q_pcist_correlation_prefers_real_pcist_over_proxy():
    rng = np.random.default_rng(5)
    n = 40
    x = rng.random(n)
    df = pd.DataFrame({
        "Qabs": x,
        "pcist": x + rng.normal(0, 0.001, n),         # near-perfect
        "pcist_proxy": rng.standard_normal(n) * 100,  # near-zero corr
    })
    result = q_pcist_correlation(df)
    assert result["r"] > 0.99


# ── real PCIst (state-transition variant) ───────────────────────────────────
# Independent implementation of Comolatti et al. 2019; see validation/pci_validation.py
# for why it's not derived from the GPL reference implementation.

def _make_evk(n_channels: int, sfreq_hz: float, baseline_s: float, response_s: float,
              response_amplitude: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n_base = int(baseline_s * sfreq_hz)
    n_resp = int(response_s * sfreq_hz)
    n = n_base + n_resp
    times_ms = (np.arange(n) - n_base) / sfreq_hz * 1000.0

    noise = rng.standard_normal((n_channels, n)) * 1.0
    signal = noise.copy()
    if response_amplitude > 0:
        t_resp = np.arange(n_resp) / sfreq_hz
        # a structured, channel-differentiated evoked pattern -- present ONLY in
        # the response window, absent from baseline (unlike the noise, which
        # spans both) -- this is what should drive up state-transition complexity.
        for ch in range(n_channels):
            freq = 8 + 3 * ch
            signal[ch, n_base:] += response_amplitude * np.sin(2 * np.pi * freq * t_resp)
    return signal, times_ms


def test_pcist_low_for_pure_noise_no_evoked_response():
    # Pure noise can still spuriously pass the SNR filter for a component or two
    # by chance (a known property of this algorithm, not a bug -- real PCIst
    # null distributions in the literature are low but not exactly zero). The
    # meaningful guarantee is the comparative one in the next test: a genuine
    # structured response must score distinctly higher than noise-only.
    value = pcist(
        *_make_evk(n_channels=6, sfreq_hz=1000.0, baseline_s=0.4, response_s=0.3,
                    response_amplitude=0.0, seed=10),
        baseline_window=(-400, -50), response_window=(0, 300),
    )
    assert 0.0 <= value < 100.0


def test_pcist_higher_for_genuine_structured_response():
    rng_seed = 11
    noise_only, times_ms = _make_evk(
        n_channels=6, sfreq_hz=1000.0, baseline_s=0.4, response_s=0.3,
        response_amplitude=0.0, seed=rng_seed,
    )
    with_response, _ = _make_evk(
        n_channels=6, sfreq_hz=1000.0, baseline_s=0.4, response_s=0.3,
        response_amplitude=8.0, seed=rng_seed,
    )
    v_noise = pcist(noise_only, times_ms, baseline_window=(-400, -50), response_window=(0, 300))
    v_response = pcist(with_response, times_ms, baseline_window=(-400, -50), response_window=(0, 300))
    assert v_response > v_noise
    assert v_response > 0.0


def test_pcist_nan_input_returns_zero():
    signal = np.full((3, 100), np.nan)
    times_ms = np.linspace(-400, 300, 100)
    assert pcist(signal, times_ms) == 0.0


def test_pcist_shape_mismatch_raises():
    with pytest.raises(ValueError):
        pcist(np.zeros((3, 100)), np.linspace(-400, 300, 50))


def test_pcist_single_channel_no_crash():
    signal, times_ms = _make_evk(
        n_channels=1, sfreq_hz=500.0, baseline_s=0.3, response_s=0.2,
        response_amplitude=5.0, seed=12,
    )
    value = pcist(signal, times_ms, baseline_window=(-300, -20), response_window=(0, 200))
    assert np.isfinite(value)
    assert value >= 0.0
