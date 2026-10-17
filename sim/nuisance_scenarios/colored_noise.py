"""Pure NumPy colored noise generator and empirical spectral slope diagnostics.

PSD Convention:
    One-sided Power Spectral Density S(f) is proportional to 1 / f^chi for f > 0.
    In the discrete Fourier domain:
        |X(f_k)| = C * f_k^(-chi / 2) for k in {1, ..., floor(N / 2)}.

DC Handling Convention:
    The zero-frequency component X(f_0) = X(0) is explicitly set to 0.0 + 0.0j.
    The resulting generated colored noise sequence is strictly zero-mean in expectation.

Nyquist Convention:
    For even sample count N, the Nyquist bin f_{N/2} = f_s / 2 is constrained to be
    strictly real-valued (random phase chosen from {0.0, pi}) to maintain real-valued
    signal symmetry under the discrete inverse real FFT (irfft).
"""
from __future__ import annotations

import math
from typing import NamedTuple, Optional, Sequence, Tuple, Union

import numpy as np


class SpectralSlopeFit(NamedTuple):
    """Result of empirical spectral slope regression."""

    estimated_chi: float
    fit_r2: float


def generate_colored_noise(
    n_samples: int,
    chi: float,
    n_channels: int = 1,
    sfreq_hz: float = 250.0,
    seed: Optional[Union[int, np.random.Generator, np.random.SeedSequence]] = None,
    *,
    sampling_rate_hz: Optional[float] = None,
    rng: Optional[Union[int, np.random.Generator, np.random.SeedSequence]] = None,
) -> np.ndarray:
    """Generate 1D or 2D multichannel colored noise with explicit spectral exponent chi.

    Parameters:
        n_samples: Number of time samples (must be >= 4).
        chi: Spectral exponent chi in 1/f^chi (chi >= 0.0).
             chi=0.0: White noise (flat PSD).
             chi=1.0: Pink noise (1/f PSD).
             chi=2.0: Brown/red noise (1/f^2 PSD).
        n_channels: Number of distinct channels (default 1).
        sfreq_hz: Sampling frequency in Hz (must be > 0).
        seed: Master seed for reproducible generation.

    Returns:
        noise: NumPy array of shape (n_channels, n_samples) with zero mean and unit variance.
    """
    if not isinstance(n_samples, int) or n_samples < 4:
        raise ValueError(f"n_samples must be an integer >= 4, got {n_samples}")
    if not isinstance(n_channels, int) or n_channels < 1:
        raise ValueError(f"n_channels must be an integer >= 1, got {n_channels}")
    if not math.isfinite(chi) or chi < 0.0:
        raise ValueError(f"chi must be a non-negative finite float, got {chi}")
    effective_sfreq = sampling_rate_hz if sampling_rate_hz is not None else sfreq_hz
    if not math.isfinite(effective_sfreq) or effective_sfreq <= 0.0:
        raise ValueError(f"sfreq_hz must be a positive finite float, got {effective_sfreq}")

    effective_seed = rng if rng is not None else seed
    gen = np.random.default_rng(effective_seed)

    # One-sided discrete Fourier frequencies
    freqs = np.fft.rfftfreq(n_samples, d=1.0 / effective_sfreq)
    n_freqs = len(freqs)

    noise_out = np.zeros((n_channels, n_samples), dtype=np.float64)

    for ch in range(n_channels):
        # White complex noise components
        # Draw independent standard normals for real and imaginary parts
        real_part = gen.standard_normal(n_freqs)
        imag_part = gen.standard_normal(n_freqs)
        complex_spec = real_part + 1j * imag_part

        # Explicit DC Handling: f = 0 bin is strictly zero
        complex_spec[0] = 0.0 + 0.0j

        # Amplitude scaling: |X(f)| proportional to f^(-chi / 2)
        if chi > 0.0:
            # Positive frequency bins k >= 1
            amplitude_scaling = np.zeros(n_freqs, dtype=np.float64)
            amplitude_scaling[1:] = freqs[1:] ** (-chi / 2.0)
            complex_spec *= amplitude_scaling

        # Nyquist bin constraint for even N: imaginary part must be zero
        if n_samples % 2 == 0 and n_freqs > 1:
            complex_spec[-1] = complex_spec[-1].real + 0.0j

        # Synthesize time-domain sequence via inverse real FFT
        raw_signal = np.fft.irfft(complex_spec, n=n_samples)

        # Standardize to zero-mean and unit variance per channel
        std_val = float(np.std(raw_signal, ddof=1)) if n_samples > 1 else 1.0
        if std_val > 1e-12:
            raw_signal = (raw_signal - np.mean(raw_signal)) / std_val
        else:
            raw_signal = raw_signal - np.mean(raw_signal)

        noise_out[ch] = raw_signal

    return noise_out


def estimate_spectral_slope(
    signal: np.ndarray,
    sfreq_hz: float,
    f_min: float | None = None,
    f_max: float | None = None,
) -> Tuple[float, float]:
    """Estimate empirical spectral slope chi from signal PSD using pure NumPy log-log regression.

    Fits the linear model:
        ln(PSD(f)) = -chi * ln(f) + C

    Parameters:
        signal: 1D array of shape (n_samples,) or 2D array of shape (n_channels, n_samples).
        sfreq_hz: Sampling rate in Hz.
        f_min: Lower frequency bound in Hz (default: 2.0 Hz).
        f_max: Upper frequency bound in Hz (default: 0.4 * sfreq_hz).

    Returns:
        (estimated_chi, r_squared):
            estimated_chi: The empirical slope exponent (e.g. ~1.0 for pink noise).
            r_squared: Coefficient of determination of the log-log linear fit.
    """
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[None, :]
    elif arr.ndim != 2:
        raise ValueError(f"signal must be 1D or 2D, got shape {arr.shape}")

    n_channels, n_samples = arr.shape
    if n_samples < 8:
        raise ValueError(f"signal length ({n_samples}) is too short for spectral slope estimation")
    if not np.all(np.isfinite(arr)):
        raise ValueError("signal contains non-finite values (NaN or Inf)")

    freqs = np.fft.rfftfreq(n_samples, d=1.0 / sfreq_hz)
    # Compute periodogram power spectral density averaged across channels
    fft_vals = np.fft.rfft(arr, axis=-1)
    psd_channels = (np.abs(fft_vals) ** 2) / (sfreq_hz * n_samples)
    psd_mean = np.mean(psd_channels, axis=0)

    # Establish default frequency fit band
    f_low = f_min if f_min is not None else max(1.0, float(freqs[1]) if len(freqs) > 1 else 1.0)
    f_high = f_max if f_max is not None else float(0.4 * sfreq_hz)

    # Mask positive frequencies within [f_low, f_high]
    valid_mask = (freqs >= f_low) & (freqs <= f_high) & (freqs > 0.0) & (psd_mean > 1e-20)
    if np.count_nonzero(valid_mask) < 3:
        # Not enough frequency bins to reliably fit slope
        return SpectralSlopeFit(float("nan"), 0.0)

    fit_freqs = freqs[valid_mask]
    fit_psd = psd_mean[valid_mask]

    log_f = np.log(fit_freqs)
    log_p = np.log(fit_psd)

    # Pure NumPy linear regression: np.polyfit of degree 1
    poly = np.polyfit(log_f, log_p, 1)
    slope = float(poly[0])
    intercept = float(poly[1])

    estimated_chi = -slope

    # Compute R^2 of log-log fit
    predicted_log_p = slope * log_f + intercept
    ss_tot = float(np.sum((log_p - np.mean(log_p)) ** 2))
    ss_res = float(np.sum((log_p - predicted_log_p) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-12 else 0.0

    return SpectralSlopeFit(estimated_chi, max(0.0, float(r_squared)))
