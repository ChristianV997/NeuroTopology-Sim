"""Memory-bounded Monte-Carlo wave-function trajectories for PITNN excitons."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class MCWFConfig:
    """Trajectory controls; times are seconds and rates are s^-1."""
    trajectories: int = 64
    seed: int = 0
    store_density: bool = False


class MCWFTrajectoryEngine:
    """Evolve O(N) wavefunctions and optionally stream an ensemble density."""

    def __init__(self, hamiltonian_J: np.ndarray, jump_rates_s: np.ndarray):
        hamiltonian = np.asarray(hamiltonian_J, dtype=complex)
        rates = np.asarray(jump_rates_s, dtype=float)
        if hamiltonian.ndim != 2 or hamiltonian.shape[0] != hamiltonian.shape[1] or rates.shape != (hamiltonian.shape[0],):
            raise ValueError("Hamiltonian must be square and jump rates must have shape (N,)")
        if np.any(rates < 0) or not np.all(np.isfinite(hamiltonian)):
            raise ValueError("Hamiltonian/rates must be finite with non-negative rates")
        self.hamiltonian_J, self.jump_rates_s = hamiltonian, rates
        self.hbar = 1.054571817e-34

    def evolve(self, psi0: np.ndarray, times_s: np.ndarray, config: MCWFConfig = MCWFConfig()) -> dict:
        """Run seeded trajectories; retains only current vectors unless requested."""
        psi_initial = np.asarray(psi0, dtype=complex)
        times = np.asarray(times_s, dtype=float); n = len(self.jump_rates_s)
        if psi_initial.shape != (n,) or len(times) < 1 or np.any(np.diff(times) <= 0) or config.trajectories < 1:
            raise ValueError("invalid initial state, times, or trajectory count")
        norm = np.linalg.norm(psi_initial)
        if norm == 0:
            raise ValueError("psi0 must be non-zero")
        psi_initial = psi_initial / norm
        rng = np.random.default_rng(config.seed)
        density = np.zeros((len(times), n, n), dtype=complex) if config.store_density else None
        survival = np.zeros(len(times), dtype=float)
        effective = self.hamiltonian_J - 0.5j * self.hbar * np.diag(self.jump_rates_s)
        for _ in range(config.trajectories):
            psi = psi_initial.copy(); alive = True
            for index, time in enumerate(times):
                if alive:
                    if density is not None:
                        density[index] += np.outer(psi, psi.conj())
                    survival[index] += 1.0
                if index == len(times) - 1 or not alive:
                    continue
                dt = times[index + 1] - time
                proposed = psi - 1j * dt * (effective @ psi) / self.hbar
                loss_probability = float(np.clip(1.0 - np.vdot(proposed, proposed).real, 0.0, 1.0))
                if rng.random() < loss_probability:
                    alive = False
                    psi.fill(0.0)
                else:
                    proposed_norm = np.linalg.norm(proposed)
                    psi = proposed / proposed_norm if proposed_norm else proposed
        result = {"survival_probability": survival / config.trajectories,
                  "trajectories": config.trajectories, "seed": config.seed}
        if density is not None:
            result["density_estimate"] = density / config.trajectories
        return result
