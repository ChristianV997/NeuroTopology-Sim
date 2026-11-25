"""Synthetic fixtures for surrogate audit tests (no participant data)."""
from __future__ import annotations

import numpy as np


def gaussian_linear(n_ch: int = 4, n_t: int = 128, seed: int = 0) -> np.ndarray:
    """Gaussian channels with a shared latent (linear mixing)."""
    rng = np.random.default_rng(seed)
    latent = rng.standard_normal(n_t)
    noise = rng.standard_normal((n_ch, n_t))
    return (0.8 * latent[None, :] + 0.2 * noise).astype(np.float64)


def non_gaussian_skewed(n_ch: int = 3, n_t: int = 128, seed: int = 1) -> np.ndarray:
    """Non-Gaussian / skewed amplitudes with shared broadband driver."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_t, dtype=np.float64)
    driver = np.sin(2 * np.pi * 3 * t / n_t) + 0.3 * rng.standard_normal(n_t)
    rows = []
    for c in range(n_ch):
        skew = rng.exponential(scale=1.0, size=n_t) - 1.0
        rows.append(driver + 0.5 * skew + 0.1 * c)
    return np.asarray(rows, dtype=np.float64)


def constant_channel_mix(n_t: int = 64, seed: int = 2) -> np.ndarray:
    """One constant channel + one active channel (zero-power edge case)."""
    rng = np.random.default_rng(seed)
    active = np.sin(2 * np.pi * np.arange(n_t) / 16.0) + 0.05 * rng.standard_normal(n_t)
    const = np.full(n_t, 2.5, dtype=np.float64)
    return np.vstack([active, const])
