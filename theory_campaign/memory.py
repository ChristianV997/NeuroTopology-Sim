"""Minimal exponential-memory augmented-mode reference model."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.linalg import expm


@dataclass(frozen=True)
class MemoryConfig:
    """Parameters for an exponentially correlated memory kernel."""

    decay_rate_s: float = 1e8
    memory_time_s: float = 1e-9
    memory_strength_s2: float = 1e16
    frequency_s: float = 0.0
    duration_s: float = 1e-7
    steps: int = 2000

    def validate(self) -> None:
        if any(not np.isfinite(x) or x < 0 for x in (self.decay_rate_s, self.memory_strength_s2, self.frequency_s)):
            raise ValueError("rates and frequency must be finite and non-negative")
        if not np.isfinite(self.memory_time_s) or self.memory_time_s <= 0 or self.duration_s <= 0 or self.steps < 2:
            raise ValueError("memory time, duration, and steps are invalid")


def simulate_memory_mode(config: MemoryConfig) -> dict[str, object]:
    """Integrate coherence plus one exponential memory auxiliary variable.

    The short-memory limit approaches a Markov model with additional decay
    ``memory_strength_s2 * memory_time_s``. This provides a controlled null
    and avoids claiming a full microscopic bath derivation.
    """
    config.validate()
    times = np.linspace(0.0, config.duration_s, config.steps)
    dt = float(times[1] - times[0])
    coherence = np.zeros(config.steps, dtype=complex)
    auxiliary = np.zeros(config.steps, dtype=complex)
    coherence[0] = 1.0
    system = np.array(
        [
            [-(config.decay_rate_s / 2.0 + 1j * config.frequency_s), -config.memory_strength_s2],
            [1.0 / config.memory_time_s, -1.0 / config.memory_time_s],
        ],
        dtype=complex,
    )
    transition = expm(system * dt)
    state = np.array([coherence[0], auxiliary[0]], dtype=complex)
    for index in range(1, config.steps):
        state = transition @ state
        coherence[index], auxiliary[index] = state
    population = np.abs(coherence) ** 2
    positive_changes = np.maximum(np.diff(population), 0.0)
    return {
        "schema": "NeuroTopologySim.ExponentialMemoryMode.v1",
        "config": {key: getattr(config, key) for key in config.__dataclass_fields__},
        "times_s": times.tolist(),
        "coherence_real": coherence.real.tolist(),
        "coherence_imag": coherence.imag.tolist(),
        "population": population.tolist(),
        "observables": {
            "initial_population": float(population[0]),
            "final_population": float(population[-1]),
            "integrated_population_s": float(np.trapezoid(population, times)),
            "blp_like_backflow": float(np.sum(positive_changes)),
            "revival_count": int(np.count_nonzero((np.diff(population[:-1]) < 0) & (np.diff(population[1:]) > 0))),
        },
    }
