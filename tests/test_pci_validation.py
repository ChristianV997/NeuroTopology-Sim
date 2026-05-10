"""Tests for the PCI proxy alias and Q-vs-complexity correlation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from validation.pci_validation import (
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
