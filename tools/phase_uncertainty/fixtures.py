"""Deterministic synthetic complex narrowband fixtures for phase-uncertainty calibration.

Provides signals with exact analytical ground-truth phase, frequency, and amplitude:
1. Stationary narrowband signal with additive white Gaussian noise (AWGN)
2. Amplitude-modulated signal (envelope variation, SNR dips)
3. Frequency drift signal (linear chirp, non-stationary carrier)
4. Near-zero amplitude periods (phase singularities / zero-crossings)
5. Colored noise signal (autoregressive AR(1) noise violating i.i.d. second-difference assumption)
6. Short window / transient burst (small-sample edge effects)

Guardrail: Pure NumPy only. Zero SciPy, external datasets, or EEG data.
All random generation uses explicit deterministic numpy.random.Generator seeds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .candidate_estimator import wrap_phase


@dataclass(frozen=True)
class NarrowbandFixture:
    """A synthetic narrowband signal bundle with ground-truth phase and amplitude."""
    fixture_id: str
    description: str
    signal: np.ndarray             # Complex analytic signal Z[n]
    true_phase: np.ndarray         # Ground-truth unwrapped or wrapped phase theta_true[n]
    true_amplitude: np.ndarray     # Ground-truth noise-free amplitude A_true[n]
    true_frequency: np.ndarray     # Ground-truth instantaneous frequency in Hz
    fs: float                      # Sampling frequency in Hz
    snr_db: float | None           # Nominal signal-to-noise ratio in dB
    noise_type: str                # "awgn", "colored", "none", etc.
    seed: int


def make_stationary_narrowband(
    n_samples: int = 1000,
    fs: float = 1000.0,
    f0: float = 10.0,
    snr_db: float = 10.0,
    seed: int = 42,
) -> NarrowbandFixture:
    """Fixture 1: Stationary narrowband sinusoid with complex AWGN."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64) / fs
    true_phase = wrap_phase(2.0 * np.pi * f0 * t)
    true_amp = np.ones(n_samples, dtype=np.float64)
    true_freq = np.full(n_samples, f0, dtype=np.float64)

    clean_z = true_amp * np.exp(1j * true_phase)

    # Noise calculation from SNR: SNR = 10^(snr_db / 10) = P_signal / P_noise
    # Signal power = 1.0 (unit amplitude complex exponential)
    snr_linear = 10.0 ** (snr_db / 10.0)
    total_noise_power = 1.0 / snr_linear
    sigma_per_component = math.sqrt(total_noise_power / 2.0)

    noise_z = rng.normal(0.0, sigma_per_component, n_samples) + 1j * rng.normal(0.0, sigma_per_component, n_samples)
    noisy_z = clean_z + noise_z

    return NarrowbandFixture(
        fixture_id=f"stationary_narrowband_{snr_db}db_s{seed}",
        description=f"Stationary {f0} Hz complex sinusoid with AWGN at {snr_db} dB SNR",
        signal=noisy_z,
        true_phase=true_phase,
        true_amplitude=true_amp,
        true_frequency=true_freq,
        fs=fs,
        snr_db=snr_db,
        noise_type="awgn",
        seed=seed,
    )


def make_amplitude_modulated_signal(
    n_samples: int = 1000,
    fs: float = 1000.0,
    f0: float = 10.0,
    f_mod: float = 1.0,
    depth: float = 0.7,
    snr_db: float = 12.0,
    seed: int = 43,
) -> NarrowbandFixture:
    """Fixture 2: Amplitude-modulated narrowband signal.

    A(t) = 1.0 + depth * cos(2*pi*f_mod*t).
    Envelope fluctuates slowly, driving local SNR variations.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64) / fs
    true_phase = wrap_phase(2.0 * np.pi * f0 * t)
    true_amp = 1.0 + depth * np.cos(2.0 * np.pi * f_mod * t)
    true_freq = np.full(n_samples, f0, dtype=np.float64)

    clean_z = true_amp * np.exp(1j * true_phase)
    signal_power = float(np.mean(true_amp ** 2))
    snr_linear = 10.0 ** (snr_db / 10.0)
    noise_power = signal_power / snr_linear
    sigma_per_component = math.sqrt(noise_power / 2.0)

    noise_z = rng.normal(0.0, sigma_per_component, n_samples) + 1j * rng.normal(0.0, sigma_per_component, n_samples)
    noisy_z = clean_z + noise_z

    return NarrowbandFixture(
        fixture_id=f"amplitude_modulated_d{depth}_s{seed}",
        description=f"AM narrowband signal (f0={f0} Hz, f_mod={f_mod} Hz, depth={depth}) with AWGN",
        signal=noisy_z,
        true_phase=true_phase,
        true_amplitude=true_amp,
        true_frequency=true_freq,
        fs=fs,
        snr_db=snr_db,
        noise_type="awgn",
        seed=seed,
    )


def make_frequency_drift_signal(
    n_samples: int = 1000,
    fs: float = 1000.0,
    f_start: float = 8.0,
    f_end: float = 14.0,
    snr_db: float = 15.0,
    seed: int = 44,
) -> NarrowbandFixture:
    """Fixture 3: Linear frequency drift (chirp).

    Carrier frequency sweeps from f_start to f_end.
    Tests median frequency demodulation under nonstationary frequency.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64) / fs
    duration = n_samples / fs
    alpha = (f_end - f_start) / duration  # Hz / s

    # Phase phi(t) = 2*pi * (f_start * t + 0.5 * alpha * t^2)
    inst_freq = f_start + alpha * t
    true_phase = wrap_phase(2.0 * np.pi * (f_start * t + 0.5 * alpha * t ** 2))
    true_amp = np.ones(n_samples, dtype=np.float64)

    clean_z = true_amp * np.exp(1j * true_phase)
    snr_linear = 10.0 ** (snr_db / 10.0)
    noise_power = 1.0 / snr_linear
    sigma_per_component = math.sqrt(noise_power / 2.0)

    noise_z = rng.normal(0.0, sigma_per_component, n_samples) + 1j * rng.normal(0.0, sigma_per_component, n_samples)
    noisy_z = clean_z + noise_z

    return NarrowbandFixture(
        fixture_id=f"frequency_drift_{f_start}_{f_end}hz_s{seed}",
        description=f"Frequency chirp ({f_start}->{f_end} Hz) with AWGN at {snr_db} dB",
        signal=noisy_z,
        true_phase=true_phase,
        true_amplitude=true_amp,
        true_frequency=inst_freq,
        fs=fs,
        snr_db=snr_db,
        noise_type="awgn",
        seed=seed,
    )


def make_near_zero_amplitude_signal(
    n_samples: int = 1000,
    fs: float = 1000.0,
    f0: float = 10.0,
    dip_start: int = 400,
    dip_len: int = 200,
    snr_db: float = 15.0,
    seed: int = 45,
) -> NarrowbandFixture:
    """Fixture 4: Signal with near-zero amplitude period (phase singularity).

    Amplitude drops into the noise floor between dip_start and dip_start + dip_len.
    Phase is undefined / uniformly distributed in the noise floor during the dip.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64) / fs
    true_phase = wrap_phase(2.0 * np.pi * f0 * t)
    true_amp = np.ones(n_samples, dtype=np.float64)

    # Create dip to 1e-4
    dip_end = min(n_samples, dip_start + dip_len)
    true_amp[dip_start:dip_end] = 1e-4

    clean_z = true_amp * np.exp(1j * true_phase)
    snr_linear = 10.0 ** (snr_db / 10.0)
    noise_power = 1.0 / snr_linear
    sigma_per_component = math.sqrt(noise_power / 2.0)

    noise_z = rng.normal(0.0, sigma_per_component, n_samples) + 1j * rng.normal(0.0, sigma_per_component, n_samples)
    noisy_z = clean_z + noise_z

    return NarrowbandFixture(
        fixture_id=f"near_zero_amplitude_dip_{dip_start}_{dip_end}_s{seed}",
        description=f"Narrowband signal with deep amplitude notch (samples {dip_start}:{dip_end})",
        signal=noisy_z,
        true_phase=true_phase,
        true_amplitude=true_amp,
        true_frequency=np.full(n_samples, f0, dtype=np.float64),
        fs=fs,
        snr_db=snr_db,
        noise_type="awgn",
        seed=seed,
    )


def make_colored_noise_signal(
    n_samples: int = 1000,
    fs: float = 1000.0,
    f0: float = 10.0,
    ar_coef: float = 0.85,
    snr_db: float = 8.0,
    seed: int = 46,
) -> NarrowbandFixture:
    """Fixture 5: Narrowband signal with autoregressive AR(1) colored noise.

    Noise w[n] = ar_coef * w[n-1] + e[n].
    Positively correlated noise severely violates the i.i.d. assumption
    of the second-difference factor sqrt(6).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64) / fs
    true_phase = wrap_phase(2.0 * np.pi * f0 * t)
    true_amp = np.ones(n_samples, dtype=np.float64)
    clean_z = true_amp * np.exp(1j * true_phase)

    # Generate AR(1) colored noise in pure NumPy
    snr_linear = 10.0 ** (snr_db / 10.0)
    desired_total_var = 1.0 / snr_linear
    # AR(1) asymptotic variance = var(e) / (1 - rho^2) -> var(e) = var_desired * (1 - rho^2)
    var_innov = (desired_total_var / 2.0) * (1.0 - ar_coef ** 2)
    sigma_innov = math.sqrt(max(1e-12, var_innov))

    noise_real = np.zeros(n_samples, dtype=np.float64)
    noise_imag = np.zeros(n_samples, dtype=np.float64)
    e_r = rng.normal(0.0, sigma_innov, n_samples)
    e_i = rng.normal(0.0, sigma_innov, n_samples)

    for i in range(1, n_samples):
        noise_real[i] = ar_coef * noise_real[i - 1] + e_r[i]
        noise_imag[i] = ar_coef * noise_imag[i - 1] + e_i[i]

    noise_z = noise_real + 1j * noise_imag
    noisy_z = clean_z + noise_z

    return NarrowbandFixture(
        fixture_id=f"colored_noise_ar{ar_coef}_s{seed}",
        description=f"Narrowband signal with AR(1) colored noise (rho={ar_coef}) at {snr_db} dB",
        signal=noisy_z,
        true_phase=true_phase,
        true_amplitude=true_amp,
        true_frequency=np.full(n_samples, f0, dtype=np.float64),
        fs=fs,
        snr_db=snr_db,
        noise_type="colored_ar1",
        seed=seed,
    )


def make_short_window_burst(
    n_samples: int = 64,
    fs: float = 1000.0,
    f0: float = 10.0,
    snr_db: float = 15.0,
    seed: int = 47,
) -> NarrowbandFixture:
    """Fixture 6: Short window / transient burst (N=64).

    Tests small sample size, edge padding, and boundary effects on MAD and jitter.
    """
    return make_stationary_narrowband(
        n_samples=n_samples,
        fs=fs,
        f0=f0,
        snr_db=snr_db,
        seed=seed,
    )


def get_all_calibration_fixtures() -> list[NarrowbandFixture]:
    """Return comprehensive suite of synthetic calibration fixtures."""
    return [
        make_stationary_narrowband(n_samples=1000, snr_db=20.0, seed=101),
        make_stationary_narrowband(n_samples=1000, snr_db=6.0, seed=102),
        make_stationary_narrowband(n_samples=1000, snr_db=-3.0, seed=103),
        make_amplitude_modulated_signal(n_samples=1000, depth=0.8, snr_db=10.0, seed=104),
        make_frequency_drift_signal(n_samples=1000, f_start=8.0, f_end=15.0, snr_db=12.0, seed=105),
        make_near_zero_amplitude_signal(n_samples=1000, dip_start=350, dip_len=250, snr_db=15.0, seed=106),
        make_colored_noise_signal(n_samples=1000, ar_coef=0.85, snr_db=8.0, seed=107),
        make_short_window_burst(n_samples=64, snr_db=12.0, seed=108),
    ]
