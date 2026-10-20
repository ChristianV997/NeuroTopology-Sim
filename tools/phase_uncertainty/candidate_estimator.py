"""Narrowband instantaneous phase and uncertainty estimator (Round 6 Candidate Contract).

Audit Note:
The Round 6 candidate estimator was absent from the repository default branch.
This module implements the exact contract specified in the Round 6 proposal for
calibration, verification, and empirical audit. The candidate was not executed
from a pre-existing codebase; this is an independent evaluation harness.

Mathematical Contract:
1. Instantaneous phase increment estimation:
   theta[n] = angle(Z[n]) in (-pi, pi]
   Delta theta[n] = wrap(theta[n] - theta[n-1])
2. Median frequency demodulation:
   Delta omega_0 = median(Delta theta)
   delta[n] = wrap(Delta theta[n] - Delta omega_0)
3. Residual noise from second differences using MAD:
   Delta^2 theta[n] = wrap(delta[n] - delta[n-1])
   sigma_MAD = 1.4826 * MAD(Delta^2 theta) / sqrt(6)
4. SNR-derived uncertainty and circular phase jitter:
   sigma_SNR[n] ~ sigma_noise / (sqrt(2) * |Z[n]|)
   sigma_jitter[n] = sqrt(2 * (1 - R_local[n]))
5. Combined uncertainty capped at pi / sqrt(3):
   phase_std[n] = min(sqrt(sigma_SNR[n]^2 + sigma_jitter[n]^2), pi / sqrt(3))

Guardrail: Pure NumPy implementation. No SciPy, external dependencies, or clinical data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence
import numpy as np


# Theoretical maximum standard deviation of a continuous uniform distribution on [-pi, pi]
UNIFORM_CIRCULAR_STD_CEILING: float = math.pi / math.sqrt(3.0)  # ~1.813799371299107


def wrap_phase(angles: np.ndarray) -> np.ndarray:
    """Wrap angles to the interval (-pi, pi]. Pure NumPy, zero dependencies.

    The modulo form ``((a+π) mod 2π) - π`` alone yields ``[-π, π)`` and maps
    ``+π → -π``. Remap the closed lower endpoint ``-π`` to ``+π`` so the
    documented open-closed interval ``(-π, π]`` is honored.
    """
    a = np.asarray(angles, dtype=np.float64)
    wrapped = (a + np.pi) % (2.0 * np.pi) - np.pi
    return np.where(wrapped <= -np.pi, np.pi, wrapped)


def compute_analytic_signal(real_signal: np.ndarray) -> np.ndarray:
    """Compute analytic signal Z = x + i * H[x] in pure NumPy via FFT.

    Avoids scipy.signal.hilbert dependency while preserving exact mathematical definition.
    """
    x = np.asarray(real_signal, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError(f"real_signal must be 1D, got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("real_signal contains NaN or infinite values")
    n = x.shape[0]
    if n == 0:
        return np.empty(0, dtype=np.complex128)

    with np.errstate(over="ignore", invalid="ignore"):
        X = np.fft.fft(x)
    if not np.all(np.isfinite(X)):
        raise ValueError("analytic transform produced non-finite intermediate values")
    h = np.zeros(n, dtype=np.float64)
    if n % 2 == 0:
        h[0] = 1.0
        h[n // 2] = 1.0
        h[1 : n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1 : (n + 1) // 2] = 2.0

    with np.errstate(over="ignore", invalid="ignore"):
        analytic = np.fft.ifft(X * h)
    if not np.all(np.isfinite(analytic)):
        raise ValueError("analytic transform produced non-finite derived values")
    return analytic


def compute_mad(data: np.ndarray) -> float:
    """Compute Median Absolute Deviation (MAD) in pure NumPy."""
    d = np.asarray(data, dtype=np.float64)
    if d.size == 0:
        return 0.0
    med = float(np.median(d))
    return float(np.median(np.abs(d - med)))


@dataclass(frozen=True)
class EstimatorConfig:
    """Configuration for Round 6 Narrowband Phase-Uncertainty Estimator."""
    jitter_window_len: int = 15
    min_amplitude_floor: float = 1e-6
    cap_at_uniform_std: bool = True
    mad_scale_factor: float = 1.482602218505602
    second_difference_factor: float = math.sqrt(6.0)

    def __post_init__(self) -> None:
        if isinstance(self.jitter_window_len, (bool, np.bool_)) or not isinstance(
            self.jitter_window_len, (int, np.integer)
        ):
            raise ValueError("jitter_window_len must be an integer")
        if self.jitter_window_len < 3 or self.jitter_window_len % 2 == 0:
            raise ValueError(f"jitter_window_len must be an odd integer >= 3, got {self.jitter_window_len}")
        if not isinstance(self.cap_at_uniform_std, (bool, np.bool_)):
            raise ValueError("cap_at_uniform_std must be a boolean")

        positive_numeric_fields = (
            ("min_amplitude_floor", self.min_amplitude_floor),
            ("mad_scale_factor", self.mad_scale_factor),
            ("second_difference_factor", self.second_difference_factor),
        )
        for name, value in positive_numeric_fields:
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, float, np.integer, np.floating)
            ):
                raise ValueError(f"{name} must be a numeric scalar")
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass
class PhaseUncertaintyResult:
    """Output bundle of the narrowband phase-uncertainty estimator."""
    phase: np.ndarray
    phase_std: np.ndarray
    amplitude: np.ndarray
    instantaneous_freq: np.ndarray
    median_freq: float
    residual_noise_std: float
    local_jitter: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_samples": int(len(self.phase)),
            "median_freq": float(self.median_freq),
            "residual_noise_std": float(self.residual_noise_std),
            "mean_phase_std": float(np.mean(self.phase_std)) if len(self.phase_std) else 0.0,
            "min_phase_std": float(np.min(self.phase_std)) if len(self.phase_std) else 0.0,
            "max_phase_std": float(np.max(self.phase_std)) if len(self.phase_std) else 0.0,
            "metadata": dict(self.metadata),
        }


def estimate_narrowband_phase_uncertainty(
    signal: np.ndarray,
    fs: float = 1000.0,
    config: EstimatorConfig | None = None,
) -> PhaseUncertaintyResult:
    """Estimate instantaneous phase and reported phase_std from complex or real narrowband signal.

    Parameters
    ----------
    signal : np.ndarray
        1D array. Complex narrowband analytic signal Z[n] or real signal x[n].
    fs : float
        Sampling frequency in Hz.
    config : EstimatorConfig, optional
        Estimator hyperparameters.

    Returns
    -------
    PhaseUncertaintyResult
        Contains estimated phase, reported phase_std, amplitude, and diagnostic terms.
    """
    cfg = config or EstimatorConfig()

    if isinstance(fs, (bool, np.bool_)) or not isinstance(
        fs, (int, float, np.integer, np.floating)
    ):
        raise ValueError("fs must be a finite positive numeric scalar in Hz")
    fs_val = float(fs)
    if not math.isfinite(fs_val) or fs_val <= 0.0:
        raise ValueError(f"fs must be a finite positive sampling frequency in Hz, got {fs!r}")

    arr = np.asarray(signal)
    if arr.ndim != 1:
        raise ValueError(f"signal must be a 1D array, got shape {arr.shape}")
    if not np.issubdtype(arr.dtype, np.number) or np.issubdtype(arr.dtype, np.timedelta64):
        raise ValueError("signal must have a numeric NumPy dtype")
    n = arr.shape[0]
    if n < 4:
        raise ValueError(f"signal length must be >= 4 to compute second differences, got {n}")

    # Validate numeric, finite values before either FFT or complex conversion.
    try:
        input_is_finite = np.all(np.isfinite(arr))
    except TypeError as exc:
        raise ValueError("signal must contain numeric values") from exc
    if not input_is_finite:
        raise ValueError("signal contains NaN or infinite values")

    # If real, construct discrete analytic signal
    if np.isrealobj(arr):
        z = compute_analytic_signal(arr)
    else:
        z = np.asarray(arr, dtype=np.complex128)

    with np.errstate(over="ignore", invalid="ignore"):
        amp = np.abs(z)
        phase = wrap_phase(np.angle(z))
    if not np.all(np.isfinite(amp)) or not np.all(np.isfinite(phase)):
        raise ValueError("estimator produced non-finite amplitude or phase values")

    # 1. Instantaneous phase increments
    d_theta = wrap_phase(np.diff(phase))

    # 2. Median frequency demodulation
    # Median increment across time gives the central carrier frequency step
    median_d_theta = float(np.median(d_theta))
    median_freq_hz = float(median_d_theta * fs_val / (2.0 * np.pi))

    # Demodulated phase increments
    delta = wrap_phase(d_theta - median_d_theta)

    # 3. Residual noise from second differences using MAD
    d2 = wrap_phase(np.diff(delta))  # length n - 2
    mad_d2 = compute_mad(d2)

    # Under i.i.d. Gaussian phase noise, Var(d2) = 6 * Var(noise)
    # sigma_noise_est = (1.4826 * MAD(d2)) / sqrt(6)
    sigma_noise_est = (cfg.mad_scale_factor * mad_d2) / cfg.second_difference_factor
    sigma_noise_est = max(1e-12, float(sigma_noise_est))

    # 4. Instantaneous SNR-derived term
    # At high SNR, phase noise variance ~ sigma_noise^2 / (2 * A^2)
    safe_amp = np.maximum(amp, cfg.min_amplitude_floor)
    sigma_snr = sigma_noise_est / (np.sqrt(2.0) * (safe_amp / np.median(safe_amp)))

    # 5. Local circular phase jitter over sliding window
    w = cfg.jitter_window_len
    half_w = w // 2
    local_jitter = np.zeros(n, dtype=np.float64)

    # Pad delta circularly or with edge repeat for sliding window
    padded_delta = np.pad(delta, (half_w, half_w + 1), mode="edge")

    for i in range(n):
        # Window over padded delta
        win_delta = padded_delta[i : i + w]
        # Mean resultant vector length R = |mean(exp(i * delta))|
        r_val = float(np.abs(np.mean(np.exp(1j * win_delta))))
        r_val = min(1.0, max(1e-12, r_val))
        # Circular standard deviation approximation: sqrt(2 * (1 - R))
        local_jitter[i] = math.sqrt(2.0 * max(0.0, 1.0 - r_val))

    # 6. Combined uncertainty
    phase_std_raw = np.sqrt(sigma_snr ** 2 + local_jitter ** 2)

    # Cap at pi / sqrt(3) if configured
    if cfg.cap_at_uniform_std:
        phase_std = np.minimum(phase_std_raw, UNIFORM_CIRCULAR_STD_CEILING)
    else:
        phase_std = phase_std_raw

    # Instantaneous frequency in Hz
    inst_freq = np.zeros(n, dtype=np.float64)
    inst_freq[1:] = d_theta * fs_val / (2.0 * np.pi)
    inst_freq[0] = inst_freq[1] if n > 1 else median_freq_hz

    derived_arrays = {
        "phase increments": d_theta,
        "demodulated increments": delta,
        "second differences": d2,
        "SNR uncertainty": sigma_snr,
        "local jitter": local_jitter,
        "reported uncertainty": phase_std,
        "instantaneous frequency": inst_freq,
    }
    derived_scalars = {
        "median frequency": median_freq_hz,
        "MAD second difference": mad_d2,
        "residual noise standard deviation": sigma_noise_est,
    }
    if any(not np.all(np.isfinite(values)) for values in derived_arrays.values()) or any(
        not math.isfinite(value) for value in derived_scalars.values()
    ):
        raise ValueError("estimator produced non-finite derived values")

    return PhaseUncertaintyResult(
        phase=phase,
        phase_std=phase_std,
        amplitude=amp,
        instantaneous_freq=inst_freq,
        median_freq=median_freq_hz,
        residual_noise_std=sigma_noise_est,
        local_jitter=local_jitter,
        metadata={
            "estimator_name": "round6_narrowband_phase_uncertainty",
            "candidate_status": "reconstructed_from_contract_not_previously_executed",
            "fs_hz": fs_val,
            "mad_second_diff": float(mad_d2),
            "uniform_ceiling_applied": bool(cfg.cap_at_uniform_std),
            "uniform_ceiling_value": UNIFORM_CIRCULAR_STD_CEILING,
        },
    )
