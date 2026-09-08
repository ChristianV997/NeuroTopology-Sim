"""Null / surrogate generators for adversarial validation (engineering only)."""
from __future__ import annotations

from typing import Optional

import numpy as np


def phase_shuffle_null(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """Independent per-channel Fourier phase randomization (FT surrogate)."""
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError("x must be (n_channels, n_samples)")
    rng = np.random.default_rng(seed)
    n_ch, n_t = arr.shape
    X = np.fft.rfft(arr, axis=1)
    mag = np.abs(X)
    n_freq = X.shape[1]
    hi = n_freq - 1 if (n_t % 2 == 0) else n_freq
    new_phase = rng.uniform(0, 2 * np.pi, size=(n_ch, n_freq))
    new_phase[:, 0] = 0.0
    if n_t % 2 == 0:
        new_phase[:, hi] = 0.0
    return np.fft.irfft(mag * np.exp(1j * new_phase), n=n_t, axis=1)


def block_shuffle_null(x: np.ndarray, seed: int = 0, block_size: Optional[int] = None) -> np.ndarray:
    """Block-shuffle along time independently per channel (destroys long-range sync)."""
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError("x must be (n_channels, n_samples)")
    rng = np.random.default_rng(seed)
    n_ch, n_t = arr.shape
    if block_size is None:
        block_size = max(8, n_t // 16)
    block_size = max(1, min(int(block_size), n_t))
    out = np.empty_like(arr)
    n_blocks = int(np.ceil(n_t / block_size))
    for c in range(n_ch):
        blocks = [arr[c, i * block_size : (i + 1) * block_size] for i in range(n_blocks)]
        order = rng.permutation(len(blocks))
        out[c] = np.concatenate([blocks[i] for i in order])[:n_t]
    return out


def matched_variance_null(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """IID Gaussian matching per-channel variance (destroys dependence + spectrum shape)."""
    arr = np.asarray(x, dtype=np.float64)
    rng = np.random.default_rng(seed)
    std = arr.std(axis=1, keepdims=True)
    std = np.where(std > 0, std, 1.0)
    return (rng.standard_normal(arr.shape) * std).astype(np.float64)


def matched_autocorrelation_null(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """AR(1) surrogate matching per-channel lag-1 autocorrelation and variance."""
    arr = np.asarray(x, dtype=np.float64)
    rng = np.random.default_rng(seed)
    n_ch, n_t = arr.shape
    out = np.zeros_like(arr)
    for c in range(n_ch):
        xc = arr[c]
        xc = xc - xc.mean()
        var = float(np.dot(xc, xc) / max(n_t, 1))
        if var <= 0:
            out[c] = rng.standard_normal(n_t)
            continue
        lag1 = float(np.dot(xc[1:], xc[:-1]) / max(n_t - 1, 1))
        phi = float(np.clip(lag1 / var, -0.99, 0.99))
        sigma = float(np.sqrt(max(var * (1.0 - phi**2), 1e-12)))
        innov = rng.standard_normal(n_t) * sigma
        y = np.zeros(n_t)
        for t in range(1, n_t):
            y[t] = phi * y[t - 1] + innov[t]
        # Rescale to matched variance
        y_std = y.std()
        if y_std > 0:
            y = y * (np.sqrt(var) / y_std)
        out[c] = y
    return out.astype(np.float64)


NULL_REGISTRY = {
    "phase_shuffle_null": phase_shuffle_null,
    "block_shuffle_null": block_shuffle_null,
    "matched_variance_null": matched_variance_null,
    "matched_autocorrelation_null": matched_autocorrelation_null,
}
