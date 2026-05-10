"""Deterministic null-control transforms for EEG topology proxies.

These utilities produce surrogate signals whose first-order statistics resemble
the observed data while destroying specific structure (channel coupling, time
arrow, or phase content). Comparing observed metrics against these nulls is a
prerequisite for any claim of meaningful structure.

All functions:

* preserve input shape
* are deterministic given a seed (where applicable)
* perform no I/O and no network calls
"""
from __future__ import annotations

from typing import Dict, Iterable

import numpy as np


def channel_shuffle(data: np.ndarray, seed: int = 0) -> np.ndarray:
    """Permute channel order with a seeded RNG.

    Destroys spatial / inter-channel coupling while keeping each channel's
    temporal content intact.
    """
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D (channels x samples), got {arr.shape}")
    rng = np.random.default_rng(seed)
    perm = rng.permutation(arr.shape[0])
    return arr[perm].copy()


def time_reverse(data: np.ndarray) -> np.ndarray:
    """Reverse samples along the time axis.

    Destroys causal structure while preserving spectral content.
    """
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D (channels x samples), got {arr.shape}")
    return arr[:, ::-1].copy()


def phase_randomize_time(data: np.ndarray, seed: int = 0) -> np.ndarray:
    """Per-channel phase randomization preserving the amplitude spectrum.

    Replaces each Fourier-component's phase with a uniform draw on (-pi, pi]
    while keeping the magnitude spectrum and DC component unchanged. The
    inverse FFT yields a real-valued surrogate with the same per-channel power
    spectrum as the input.
    """
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D (channels x samples), got {arr.shape}")
    rng = np.random.default_rng(seed)
    n_channels, n_samples = arr.shape
    spec = np.fft.rfft(arr, axis=-1)
    mag = np.abs(spec)
    rand_phase = rng.uniform(-np.pi, np.pi, size=spec.shape)
    rand_phase[:, 0] = 0.0  # preserve DC component
    if n_samples % 2 == 0 and spec.shape[1] > 1:
        # Nyquist bin must be real for an even-length real signal.
        rand_phase[:, -1] = 0.0
    new_spec = mag * np.exp(1j * rand_phase)
    out = np.fft.irfft(new_spec, n=n_samples, axis=-1)
    return out.astype(arr.dtype, copy=False)


def compute_null_summary(
    observed: float,
    null_values: Iterable[float],
) -> Dict[str, float]:
    """Summarise an observed scalar against an iterable of null-generated scalars.

    Returns ``{"observed", "null_mean", "null_std", "z", "n_nulls"}``.
    ``z`` falls back to ``nan`` when ``null_std`` is zero.
    """
    nulls = np.asarray(list(null_values), dtype=float)
    if nulls.size == 0:
        return {
            "observed": float(observed),
            "null_mean": float("nan"),
            "null_std": float("nan"),
            "z": float("nan"),
            "n_nulls": 0,
        }
    mean = float(np.mean(nulls))
    std = float(np.std(nulls, ddof=0))
    if std > 0.0 and np.isfinite(std):
        z = float((observed - mean) / std)
    else:
        z = float("nan")
    return {
        "observed": float(observed),
        "null_mean": mean,
        "null_std": std,
        "z": z,
        "n_nulls": int(nulls.size),
    }
