"""Subject-blocked topology signal-to-noise summaries."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def phase_randomize_timeseries(timeseries: Sequence[Sequence[float]], *, seed: int) -> np.ndarray:
    """Preserve each channel's power spectrum while randomizing Fourier phase."""
    values = np.asarray(timeseries, dtype=float)
    if values.ndim != 2 or values.shape[1] < 4 or not np.all(np.isfinite(values)):
        raise ValueError("timeseries must be a finite channels-by-time matrix")
    spectrum = np.fft.rfft(values, axis=1)
    rng = np.random.default_rng(seed)
    if spectrum.shape[1] > 2:
        phases = rng.uniform(0.0, 2.0 * np.pi, size=(values.shape[0], spectrum.shape[1] - 2))
        spectrum[:, 1:-1] *= np.exp(1j * phases)
    return np.fft.irfft(spectrum, n=values.shape[1], axis=1)


def phase_randomized_effects(timeseries_windows: Sequence[Sequence[Sequence[float]]], effect_fn, *, draws: int, seed: int) -> np.ndarray:
    """Evaluate a fixed effect function on paired phase-randomized windows."""
    if draws < 1:
        raise ValueError("draws must be positive")
    rng = np.random.default_rng(seed)
    effects = []
    for _ in range(draws):
        randomized = [phase_randomize_timeseries(window, seed=int(rng.integers(2**32))) for window in timeseries_windows]
        value = float(effect_fn(randomized))
        if not np.isfinite(value):
            raise ValueError("effect function returned a non-finite value")
        effects.append(value)
    return np.asarray(effects, dtype=float)


def paired_effect(first: Sequence[float], second: Sequence[float], *, seed: int = 0, permutations: int = 5000) -> dict[str, float | int]:
    """Return a paired standardized effect and reproducible sign-flip p-value."""
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.ndim != 1 or b.shape != a.shape or len(a) < 2 or not np.all(np.isfinite([a, b])):
        raise ValueError("paired inputs must be aligned finite vectors with at least two subjects")
    if permutations < 1:
        raise ValueError("permutations must be positive")
    difference = a - b
    sd = float(np.std(difference, ddof=1))
    dz = float(np.mean(difference) / sd) if sd > 0 else 0.0
    observed = abs(float(np.mean(difference)))
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(permutations, len(difference)))
    null = np.abs(np.mean(signs * difference[None, :], axis=1))
    p_value = float((1 + np.count_nonzero(null >= observed)) / (permutations + 1))
    return {"effect_dz": dz, "mean_difference": float(np.mean(difference)), "p_value": p_value, "n_subjects": int(len(a)), "permutations": int(permutations)}


def bootstrap_mean(values: Sequence[float], *, seed: int = 0, draws: int = 5000) -> tuple[float, float]:
    """Return a percentile bootstrap interval for a subject-level vector."""
    arr = np.sort(np.asarray(values, dtype=float))
    if arr.ndim != 1 or len(arr) < 2 or not np.all(np.isfinite(arr)):
        raise ValueError("values must be a finite vector with at least two entries")
    if draws < 1:
        raise ValueError("draws must be positive")
    rng = np.random.default_rng(seed)
    samples = rng.choice(arr, size=(draws, len(arr)), replace=True).mean(axis=1)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def compute_tsnr(real_effect: float, surrogate_effects: Sequence[float], *, seed: int = 0, draws: int = 5000) -> dict[str, float | int]:
    """Compute absolute real/surrogate effect ratio and a bootstrap lower bound."""
    surrogates = np.asarray(surrogate_effects, dtype=float)
    if not np.isfinite(real_effect) or surrogates.ndim != 1 or len(surrogates) < 2 or not np.all(np.isfinite(surrogates)):
        raise ValueError("real effect and surrogate effects must be finite")
    denominator = float(np.median(np.abs(surrogates)))
    if denominator <= np.finfo(float).eps:
        raise ValueError("surrogate effect distribution has zero scale")
    ratios = abs(float(real_effect)) / np.maximum(np.abs(surrogates), np.finfo(float).eps)
    lower, upper = bootstrap_mean(ratios, seed=seed, draws=draws)
    return {"tsnr": float(abs(real_effect) / denominator), "tsnr_bootstrap_lower": lower, "tsnr_bootstrap_upper": upper, "surrogate_median_abs_effect": denominator, "n_surrogates": int(len(surrogates))}
