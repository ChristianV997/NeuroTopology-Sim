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
