"""Signal-to-noise ratio mixer for combining synthetic signals and noise at explicit target SNR (dB).

Mathematical Formulation:
    Signal power P_s = (1 / (C * N)) * sum_{c, t} s_{c, t}^2
    Target noise power P_{n, target} = P_s * 10^(-SNR_dB / 10)
    Noise scaling alpha = sqrt(P_{n, target} / P_{n, raw})
    Combined signal x = s + alpha * n
    Realized SNR_dB = 10 * log10(P_s / P_{n, realized})
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class MixedSignalResult:
    """Container for mixed signal payload and realized power diagnostics."""

    combined_signal: np.ndarray
    scaled_noise: np.ndarray
    signal_power: float
    noise_power: float
    realized_snr_db: float
    scaling_factor: float
    noise_power_before_scaling: float = 0.0

    @property
    def noisy_signal(self) -> np.ndarray:
        """Alias for combined_signal."""
        return self.combined_signal

    @property
    def clean_signal_power(self) -> float:
        """Alias for signal_power."""
        return self.signal_power

    @property
    def noise_power_scaled(self) -> float:
        """Alias for noise_power."""
        return self.noise_power

    @property
    def noise_scale_factor(self) -> float:
        """Alias for scaling_factor."""
        return self.scaling_factor


def compute_signal_power(signal: np.ndarray) -> float:
    """Compute mean-squared power of an array across all channels and samples."""
    arr = np.asarray(signal, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise ValueError("signal array contains non-finite values (NaN or Inf)")
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr ** 2))


def mix_at_target_snr(
    signal: Optional[np.ndarray] = None,
    noise: Optional[np.ndarray] = None,
    target_snr_db: float = 0.0,
    *,
    clean_signal: Optional[np.ndarray] = None,
) -> MixedSignalResult:
    """Scale noise to achieve an exact target SNR (dB) relative to the clean signal.

    Parameters:
        signal: Clean signal array of shape (n_channels, n_samples).
        noise: Noise array of shape (n_channels, n_samples).
        target_snr_db: Requested SNR in decibels.
        clean_signal: Optional keyword alias for signal.

    Returns:
        MixedSignalResult with combined signal, scaled noise, and realized powers.
    """
    raw_s = clean_signal if clean_signal is not None else signal
    if raw_s is None:
        raise ValueError("A clean signal array must be provided via 'signal' or 'clean_signal'")
    if noise is None:
        raise ValueError("A noise array must be provided via 'noise'")

    s = np.asarray(raw_s, dtype=np.float64)
    n = np.asarray(noise, dtype=np.float64)

    if s.shape != n.shape:
        raise ValueError(
            f"Shape mismatch between signal {s.shape} and noise {n.shape}"
        )
    if not math.isfinite(target_snr_db):
        raise ValueError(f"target_snr_db must be a finite float, got {target_snr_db}")
    if not np.all(np.isfinite(s)):
        raise ValueError("Clean signal contains non-finite values (NaN or Inf)")
    if not np.all(np.isfinite(n)):
        raise ValueError("Noise contains non-finite values (NaN or Inf)")

    p_s = compute_signal_power(s)
    if p_s <= 1e-15:
        raise ValueError(
            f"Clean signal has near-zero or zero power ({p_s}); target SNR is undefined."
        )

    p_n_raw = compute_signal_power(n)
    if p_n_raw <= 1e-15:
        raise ValueError(
            f"Raw noise has near-zero or zero power ({p_n_raw}); cannot scale noise."
        )

    # Calculate desired noise power: P_n = P_s / (10^(SNR/10))
    snr_linear = 10.0 ** (target_snr_db / 10.0)
    p_n_target = p_s / snr_linear

    # Scaling factor for noise amplitude
    alpha = math.sqrt(p_n_target / p_n_raw)
    scaled_n = alpha * n

    combined = s + scaled_n
    p_n_realized = float(np.mean(scaled_n ** 2))

    # Realized SNR in dB
    realized_snr_db = 10.0 * math.log10(p_s / (p_n_realized + 1e-20))

    return MixedSignalResult(
        combined_signal=combined,
        scaled_noise=scaled_n,
        signal_power=p_s,
        noise_power=p_n_realized,
        realized_snr_db=realized_snr_db,
        scaling_factor=alpha,
        noise_power_before_scaling=p_n_raw,
    )
