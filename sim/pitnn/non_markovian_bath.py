"""Drude-Lorentz colored bath and BLP information-backflow diagnostics."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class DrudeLorentzBath:
    """Bath parameters with SI energies and rates."""
    reorganization_energy_J: float = 100.0 * 1.239841984e-4 * 1.602176634e-19
    cutoff_rate_s: float = 50.0e12

    def spectral_density(self, omega_s: np.ndarray | float) -> np.ndarray:
        w = np.asarray(omega_s, dtype=float)
        if np.any(w < 0) or not np.all(np.isfinite(w)):
            raise ValueError("omega must be finite and non-negative")
        g = self.cutoff_rate_s
        return 2.0 * self.reorganization_energy_J * w * g / (w * w + g * g)

    def memory_kernel(self, lag_s: np.ndarray | float) -> np.ndarray:
        lag = np.asarray(lag_s, dtype=float)
        if not np.all(np.isfinite(lag)):
            raise ValueError("lag must be finite")
        return self.reorganization_energy_J * self.cutoff_rate_s * np.exp(-self.cutoff_rate_s * np.abs(lag))

    def colored_noise(self, n_steps: int, dt_s: float, channels: int = 1, seed: int = 0) -> np.ndarray:
        if n_steps < 1 or channels < 1 or dt_s <= 0:
            raise ValueError("n_steps, channels and dt_s must be positive")
        a = float(np.exp(-self.cutoff_rate_s * dt_s))
        variance = float(self.memory_kernel(0.0))
        rng = np.random.default_rng(seed)
        noise = np.zeros((n_steps, channels), dtype=float)
        noise[0] = rng.normal(scale=np.sqrt(variance), size=channels)
        innovation = np.sqrt(max(0.0, 1.0 - a * a) * variance)
        for i in range(1, n_steps):
            noise[i] = a * noise[i - 1] + rng.normal(scale=innovation, size=channels)
        return noise


@dataclass(frozen=True)
class MultiExponentialMemoryBath:
    """Finite sum of causal exponential memory channels."""

    amplitudes_s2: tuple[float, ...]
    memory_times_s: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.amplitudes_s2) != len(self.memory_times_s) or not self.amplitudes_s2:
            raise ValueError("amplitudes_s2 and memory_times_s must be non-empty and same length")
        if any((not np.isfinite(a)) or a < 0 for a in self.amplitudes_s2):
            raise ValueError("amplitudes_s2 must be finite and non-negative")
        if any((not np.isfinite(t)) or t <= 0 for t in self.memory_times_s):
            raise ValueError("memory_times_s must be finite and positive")

    def memory_kernel(self, lag_s: np.ndarray | float) -> np.ndarray:
        lag = np.asarray(lag_s, dtype=float)
        if not np.all(np.isfinite(lag)):
            raise ValueError("lag must be finite")
        kernel = np.zeros_like(lag, dtype=float)
        for amplitude, memory_time in zip(self.amplitudes_s2, self.memory_times_s):
            kernel = kernel + amplitude * np.exp(-np.abs(lag) / memory_time)
        return kernel


@dataclass(frozen=True)
class OscillatoryMemoryBath:
    """Exponentially damped oscillatory memory kernel."""

    amplitude_s2: float
    memory_time_s: float
    angular_frequency_s: float

    def __post_init__(self) -> None:
        if any((not np.isfinite(value)) for value in (self.amplitude_s2, self.memory_time_s, self.angular_frequency_s)):
            raise ValueError("bath parameters must be finite")
        if self.amplitude_s2 < 0 or self.memory_time_s <= 0:
            raise ValueError("amplitude_s2 must be non-negative and memory_time_s positive")

    def memory_kernel(self, lag_s: np.ndarray | float) -> np.ndarray:
        lag = np.asarray(lag_s, dtype=float)
        if not np.all(np.isfinite(lag)):
            raise ValueError("lag must be finite")
        return self.amplitude_s2 * np.exp(-np.abs(lag) / self.memory_time_s) * np.cos(self.angular_frequency_s * lag)


def integrated_kernel_strength(kernel: np.ndarray, times_s: np.ndarray) -> float:
    """Return the causal kernel area using trapezoidal integration."""
    k = np.asarray(kernel, dtype=float)
    t = np.asarray(times_s, dtype=float)
    if k.ndim != 1 or t.shape != k.shape or len(k) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError("kernel and strictly increasing times must align")
    return float(np.trapezoid(k, t))


def integrate_stable_observables(times_s: np.ndarray, decay_rate_s: float, memory_kernel_s2: np.ndarray,
                                 dephasing_rate_s: float = 0.0) -> dict[str, float]:
    """Integrate a stable two-observable surrogate: population and coherence retention."""
    t = np.asarray(times_s, dtype=float)
    kernel = np.asarray(memory_kernel_s2, dtype=float)
    if t.ndim != 1 or kernel.shape != t.shape or len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError("times_s and kernel must align on a strictly increasing grid")
    if decay_rate_s <= 0 or dephasing_rate_s < 0:
        raise ValueError("rates must be positive/finite")
    cumulative = np.zeros_like(t)
    dt = np.diff(t)
    cumulative[1:] = np.cumsum(0.5 * (kernel[1:] + kernel[:-1]) * dt)
    loss_population = decay_rate_s * t - cumulative
    loss_coherence = (0.5 * decay_rate_s + dephasing_rate_s) * t - 0.5 * cumulative
    integrated_population = float(np.trapezoid(np.exp(-np.clip(loss_population, 0.0, 700.0)), t))
    integrated_coherence = float(np.trapezoid(np.exp(-np.clip(loss_coherence, 0.0, 700.0)), t))
    return {
        "integrated_population": integrated_population,
        "integrated_coherence": integrated_coherence,
        "final_population": float(np.exp(-np.clip(loss_population[-1], 0.0, 700.0))),
        "final_coherence": float(np.exp(-np.clip(loss_coherence[-1], 0.0, 700.0))),
    }


def trace_distance(rho_a: np.ndarray, rho_b: np.ndarray) -> float:
    """Return quantum trace distance ``0.5*||rho_a-rho_b||_1``."""
    a, b = np.asarray(rho_a, dtype=complex), np.asarray(rho_b, dtype=complex)
    if a.shape != b.shape or a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("density matrices must be square and shape-matched")
    return float(0.5 * np.sum(np.abs(np.linalg.eigvalsh((a - b + (a - b).conj().T) / 2.0))))


def blp_measure(distances: np.ndarray, times_s: np.ndarray) -> float:
    """Integrate positive trace-distance changes in SI seconds."""
    d, t = np.asarray(distances, dtype=float), np.asarray(times_s, dtype=float)
    if d.ndim != 1 or t.shape != d.shape or len(d) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError("distances and strictly increasing times must align")
    return float(np.sum(np.maximum(np.diff(d), 0.0)))
