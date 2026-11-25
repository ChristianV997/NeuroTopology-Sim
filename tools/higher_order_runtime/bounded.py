"""Bounded-memory wrappers for higher-order signal processing steps.

Each helper processes a long multichannel signal without materializing large
intermediates, and is numerically equivalent (within floating tolerance) to the
corresponding full-array computation:

* :func:`iter_signal_windows` -- fixed-size chunk windows (zero-copy views);
* :class:`RollingCovariance` -- streaming covariance (Chan parallel combine),
  equivalent to ``np.cov(X, rowvar=False)``;
* :func:`iter_triad_candidates` -- bounded triad candidate iteration;
* :func:`iter_spectral_segments` -- spectral segment iteration;
* :func:`one_at_a_time_surrogates` -- surrogate generation without storing all;
* :class:`IncrementalSummary` -- streaming mean/variance/extrema/checksum.

Pure NumPy; deterministic; no import of streaming/kernel/forecasting code.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

import numpy as np

from .protocols import SpectralSegmentFn, SurrogateFn, TriadStatFn


def _as_2d(signal: np.ndarray) -> np.ndarray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim == 1:
        return arr.reshape(-1, 1)
    if arr.ndim == 2:
        return arr
    raise ValueError("signal must be 1-D (samples,) or 2-D (samples, channels)")


def iter_signal_windows(signal: np.ndarray, chunk_size: int) -> Iterator[np.ndarray]:
    """Yield consecutive non-overlapping chunk views along the sample axis."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    data = _as_2d(signal)
    n = data.shape[0]
    for start in range(0, n, chunk_size):
        yield data[start:start + chunk_size]


@dataclass
class RollingCovariance:
    """Streaming covariance via the Chan-Golub-LeVeque parallel combine.

    ``.matrix()`` returns the sample covariance (ddof=1), matching
    ``np.cov(X, rowvar=False)`` within floating tolerance for a fixed chunk order.
    """
    n_channels: int
    count: int = 0
    _mean: np.ndarray = field(default=None)  # type: ignore[assignment]
    _m2: np.ndarray = field(default=None)     # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._mean = np.zeros(self.n_channels, dtype=np.float64)
        self._m2 = np.zeros((self.n_channels, self.n_channels), dtype=np.float64)

    def update(self, chunk: np.ndarray) -> None:
        block = np.asarray(chunk, dtype=np.float64)
        if block.ndim != 2 or block.shape[1] != self.n_channels:
            raise ValueError("chunk must be (m, n_channels)")
        nb = block.shape[0]
        if nb == 0:
            return
        b_mean = block.mean(axis=0)
        centered = block - b_mean
        b_m2 = centered.T @ centered
        if self.count == 0:
            self._mean = b_mean.copy()
            self._m2 = b_m2.copy()
            self.count = nb
        else:
            total = self.count + nb
            delta = b_mean - self._mean
            self._mean = self._mean + delta * (nb / total)
            self._m2 = self._m2 + b_m2 + np.outer(delta, delta) * (self.count * nb / total)
            self.count = total

    def matrix(self, ddof: int = 1) -> np.ndarray:
        if self.count - ddof <= 0:
            return np.full((self.n_channels, self.n_channels), np.nan)
        return self._m2 / (self.count - ddof)


def iter_triad_candidates(n_channels: int, candidate_limit: Optional[int] = None
                          ) -> Iterator[Tuple[int, int, int]]:
    """Yield channel triads ``(i<j<k)`` deterministically, bounded by the limit."""
    if n_channels < 3:
        return
    gen = itertools.combinations(range(n_channels), 3)
    if candidate_limit is None:
        yield from gen
    else:
        if candidate_limit < 0:
            raise ValueError("candidate_limit must be >= 0")
        yield from itertools.islice(gen, candidate_limit)


def evaluate_triads(cov: np.ndarray, triad_fn: TriadStatFn,
                    candidate_limit: Optional[int] = None) -> Tuple[float, int]:
    """Return ``(checksum, count)`` over bounded triad candidates for ``cov``."""
    checksum = 0.0
    count = 0
    n = cov.shape[0]
    for i, j, k in iter_triad_candidates(n, candidate_limit):
        checksum += float(triad_fn(cov, i, j, k))
        count += 1
    return checksum, count


def iter_spectral_segments(signal: np.ndarray, segment_len: int) -> Iterator[np.ndarray]:
    """Yield complete ``(segment_len, n_channels)`` segment views (tumbling)."""
    if segment_len < 1:
        raise ValueError("segment_len must be >= 1")
    data = _as_2d(signal)
    n = data.shape[0]
    for start in range(0, n - segment_len + 1, segment_len):
        yield data[start:start + segment_len]


def spectral_power_sum(signal: np.ndarray, segment_len: int,
                       segment_fn: SpectralSegmentFn) -> Tuple[float, int]:
    """Stream complete segments through ``segment_fn``; return ``(sum, count)``."""
    total = 0.0
    count = 0
    for segment in iter_spectral_segments(signal, segment_len):
        total += float(segment_fn(segment))
        count += 1
    return total, count


def one_at_a_time_surrogates(signal: np.ndarray, surrogate_fn: SurrogateFn, *,
                             surrogate_limit: int, seed: int) -> Tuple[float, List[float]]:
    """Generate surrogate statistics one at a time (bounded memory).

    Returns ``(mean_stat, per_surrogate_stats)``. Deterministic for a fixed
    ``(seed, surrogate_limit)``; no surrogate batch is materialized.
    """
    if surrogate_limit < 0:
        raise ValueError("surrogate_limit must be >= 0")
    data = _as_2d(signal)
    stats: List[float] = []
    for s in range(surrogate_limit):
        stats.append(float(surrogate_fn(data, s, seed)))
    mean_stat = float(np.mean(stats)) if stats else 0.0
    return mean_stat, stats


@dataclass
class IncrementalSummary:
    """Streaming per-channel mean/variance/min/max + a stable order checksum."""
    n_channels: int
    count: int = 0
    _mean: np.ndarray = field(default=None)  # type: ignore[assignment]
    _m2: np.ndarray = field(default=None)     # type: ignore[assignment]
    minimum: np.ndarray = field(default=None)  # type: ignore[assignment]
    maximum: np.ndarray = field(default=None)  # type: ignore[assignment]
    checksum: float = 0.0

    def __post_init__(self) -> None:
        self._mean = np.zeros(self.n_channels, dtype=np.float64)
        self._m2 = np.zeros(self.n_channels, dtype=np.float64)
        self.minimum = np.full(self.n_channels, np.inf, dtype=np.float64)
        self.maximum = np.full(self.n_channels, -np.inf, dtype=np.float64)

    def update(self, chunk: np.ndarray) -> None:
        block = np.asarray(chunk, dtype=np.float64)
        if block.ndim != 2 or block.shape[1] != self.n_channels:
            raise ValueError("chunk must be (m, n_channels)")
        nb = block.shape[0]
        if nb == 0:
            return
        b_mean = block.mean(axis=0)
        b_m2 = ((block - b_mean) ** 2).sum(axis=0)
        if self.count == 0:
            self._mean = b_mean.copy()
            self._m2 = b_m2.copy()
            self.count = nb
        else:
            total = self.count + nb
            delta = b_mean - self._mean
            self._mean = self._mean + delta * (nb / total)
            self._m2 = self._m2 + b_m2 + (delta ** 2) * (self.count * nb / total)
            self.count = total
        np.minimum(self.minimum, block.min(axis=0), out=self.minimum)
        np.maximum(self.maximum, block.max(axis=0), out=self.maximum)
        self.checksum += float(block.sum())

    @property
    def mean(self) -> np.ndarray:
        return self._mean if self.count else np.zeros(self.n_channels)

    @property
    def variance(self) -> np.ndarray:
        return self._m2 / self.count if self.count else np.zeros(self.n_channels)
