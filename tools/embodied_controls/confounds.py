"""Confound controls for embodied-control alignment.

Implements circular shifts, block shifts, matched-variance controls,
and condition-preserving permutations.
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from tools.embodied_controls.types import (
    ConfoundControlResult,
    ConfoundControlType,
)


def generate_circular_shift(
    signal: np.ndarray | Sequence[float],
    shift_samples: int,
) -> np.ndarray:
    """Cyclically rotate signal by shift_samples.
    
    Preserves exact marginal distribution, amplitude spectrum, and periodicity
    while completely disrupting instantaneous phase alignment with paired modalities.
    """
    arr = np.asarray(signal, dtype=float)
    if len(arr) == 0 or shift_samples == 0:
        return arr.copy()
    shift = shift_samples % len(arr)
    return np.roll(arr, shift)


def generate_block_shift(
    signal: np.ndarray | Sequence[float],
    block_size: int,
    shift_blocks: int = 1,
) -> np.ndarray:
    """Cyclically shift signal in contiguous blocks.
    
    Preserves local autocorrelation and short-time nonstationarities
    within blocks while breaking cross-modal coupling across block boundaries.
    """
    arr = np.asarray(signal, dtype=float)
    n = len(arr)
    if n == 0 or block_size <= 0 or block_size >= n or shift_blocks == 0:
        return arr.copy()

    n_full_blocks = n // block_size
    if n_full_blocks <= 1:
        return generate_circular_shift(arr, block_size)

    blocks: list[np.ndarray] = [
        arr[i * block_size : (i + 1) * block_size] for i in range(n_full_blocks)
    ]
    remainder = arr[n_full_blocks * block_size :]

    shift = shift_blocks % n_full_blocks
    shifted_blocks = blocks[shift:] + blocks[:shift]

    reconstructed = np.concatenate(shifted_blocks)
    if len(remainder) > 0:
        reconstructed = np.concatenate([reconstructed, remainder])
    return reconstructed


def generate_matched_variance_control(
    signal: np.ndarray | Sequence[float],
    seed: int = 42,
) -> np.ndarray:
    """Generate phase-randomized surrogate matching exact power spectrum and variance.
    
    Constructs an amplitude-preserving Fourier surrogate with randomized phase
    distributed uniformly on [-pi, pi], destroying physiological event dynamics
    while strictly preserving linear autocorrelation, variance, and spectral shape.
    """
    arr = np.asarray(signal, dtype=float)
    n = len(arr)
    if n < 4:
        rng = np.random.default_rng(seed)
        return arr + rng.normal(0.0, 1e-4, size=n)

    # FFT phase randomization
    fft_coeffs = np.fft.rfft(arr)
    amplitudes = np.abs(fft_coeffs)

    rng = np.random.default_rng(seed)
    # Random phases on intermediate frequencies (leave DC and Nyquist real)
    random_phases = rng.uniform(-np.pi, np.pi, size=len(fft_coeffs))
    random_phases[0] = 0.0
    if n % 2 == 0 and len(random_phases) > 1:
        random_phases[-1] = 0.0

    surrogate_fft = amplitudes * np.exp(1j * random_phases)
    surrogate = np.fft.irfft(surrogate_fft, n=n)

    # Scale to match original mean and variance exactly
    orig_std = float(np.std(arr))
    surr_std = float(np.std(surrogate))
    if surr_std > 1e-9:
        surrogate = (surrogate - np.mean(surrogate)) * (orig_std / surr_std) + np.mean(arr)

    return surrogate


def generate_condition_preserving_permutation(
    feature_series: Sequence[float],
    conditions: Sequence[str],
    seed: int = 42,
) -> list[float]:
    """Permute feature values strictly within identical condition groups.
    
    Preserves condition-level marginal distributions and between-condition
    mean shifts, while destroying window-specific temporal alignment with EEG.
    """
    if len(feature_series) != len(conditions):
        raise ValueError("feature_series and conditions must have identical length")

    n = len(feature_series)
    if n <= 1:
        return list(feature_series)

    rng = np.random.default_rng(seed)
    permuted = list(feature_series)

    # Group indices by condition
    condition_indices: dict[str, list[int]] = {}
    for idx, cond in enumerate(conditions):
        condition_indices.setdefault(cond, []).append(idx)

    for cond, indices in condition_indices.items():
        if len(indices) > 1:
            vals = [feature_series[i] for i in indices]
            perm_order = rng.permutation(len(indices))
            for i, p_idx in enumerate(perm_order):
                permuted[indices[i]] = vals[p_idx]

    return permuted


def evaluate_coupling_attenuation(
    original_coupling: float,
    perturbed_coupling: float,
    control_type: ConfoundControlType,
    parameter_description: str,
    offset_s: float | None = None,
) -> ConfoundControlResult:
    """Evaluate whether confound control successfully attenuates cross-modal coupling."""
    orig_abs = abs(original_coupling)
    pert_abs = abs(perturbed_coupling)

    if orig_abs > 1e-6:
        attenuation = float((orig_abs - pert_abs) / orig_abs)
    else:
        attenuation = 0.0

    # Control passes if perturbation reduces coupling
    passed = bool(pert_abs < orig_abs) or (orig_abs < 1e-3)

    return ConfoundControlResult(
        control_type=control_type.value,
        parameter_description=parameter_description,
        perturbation_offset_s=offset_s,
        coupling_metric_name="cross_correlation",
        original_coupling=float(original_coupling),
        perturbed_coupling=float(perturbed_coupling),
        attenuation_ratio=attenuation,
        retains_autocorrelation=True,
        surrogate_passed=passed,
    )
