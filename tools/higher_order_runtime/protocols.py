"""Protocol-compatible interfaces + deterministic local fixtures.

The higher-order feature implementations (triadic higher-order interactions,
spectral higher-order statistics, transition forecasting) live in other agents'
unmerged PRs and are treated as *read-only interfaces*. To benchmark bounded
runtime without importing them, we declare structural ``Protocol`` types and
provide small deterministic fixtures that satisfy them. Callers may pass any
conforming callable (the real implementation, once available) instead.

All fixtures are pure, deterministic, and synthetic -- performance scaffolding
only, never scientific/biological evidence.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class TriadStatFn(Protocol):
    """Scalar statistic for a channel triad given a covariance matrix.

    Must be a pure function of ``(cov, i, j, k)`` so the bounded and full paths
    yield identical values for identical covariance input.
    """

    def __call__(self, cov: np.ndarray, i: int, j: int, k: int) -> float: ...


class SpectralSegmentFn(Protocol):
    """Scalar summary of one ``(segment_len, n_channels)`` signal segment."""

    def __call__(self, segment: np.ndarray) -> float: ...


class SurrogateFn(Protocol):
    """Deterministic scalar statistic for surrogate index ``s`` and seed."""

    def __call__(self, signal: np.ndarray, s: int, seed: int) -> float: ...


def fixture_triad_stat(cov: np.ndarray, i: int, j: int, k: int) -> float:
    """Deterministic triad statistic: sum of the three pairwise covariances."""
    return float(cov[i, j] + cov[i, k] + cov[j, k])


def fixture_spectral_power(segment: np.ndarray) -> float:
    """Deterministic spectral summary: total real-FFT power over all channels."""
    seg = np.asarray(segment, dtype=np.float64)
    spectrum = np.fft.rfft(seg, axis=0)
    return float(np.sum((spectrum * np.conj(spectrum)).real))


def fixture_surrogate_stat(signal: np.ndarray, s: int, seed: int) -> float:
    """Deterministic surrogate statistic via per-surrogate seeded channel rolls.

    Rolls each channel by a seeded random shift and returns the summed lag-0
    cross-covariance between channel 0 and every other channel. Fully determined
    by ``(seed, s)``, so surrogate ``s`` is identical whether generated in a
    materialized batch or one-at-a-time.
    """
    x = np.asarray(signal, dtype=np.float64)
    n, c = x.shape
    rng = np.random.default_rng(seed + s)
    shifts = rng.integers(1, max(n, 2), size=c)
    ref = x[:, 0] - x[:, 0].mean()
    total = 0.0
    for ch in range(c):
        rolled = np.roll(x[:, ch], int(shifts[ch]))
        rolled = rolled - rolled.mean()
        total += float(np.dot(ref, rolled) / n)
    return total
