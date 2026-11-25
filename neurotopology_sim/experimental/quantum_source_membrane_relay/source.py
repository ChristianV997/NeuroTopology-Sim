"""Minimal two-level open-quantum sink / event-flux source (NumPy only).

State space: excited |e⟩ and ground |g⟩ (ordered basis [e, g]).

Hamiltonian (joules if energies are in joules; here we use rad/s units with
ħ = 1 for the synthetic benchmark — declared in config):

    H / ħ = (ω/2) σ_z

Lindblad sink (population decay e → g):

    L = √γ |g⟩⟨e|

Event flux density (s⁻¹):

    φ(t) = γ ⟨e|ρ(t)|e⟩ = γ ρ_ee(t)

Integrated reaction yield over [0, T] (dimensionless expected jump count):

    Y = ∫_0^T φ(t) dt

This is a synthetic photophysics toy, not a microtubule or radical-pair claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

_HBAR_J_S = 1.054571817e-34


@dataclass(frozen=True)
class QuantumSourceConfig:
    """Parameters for the two-level sink source.

    ``omega_rad_s`` and ``gamma_s`` are in SI (rad/s and 1/s). Propagation uses
    ħ in joule-seconds so H = ħ ω σ_z / 2 has joule units.
    """

    omega_rad_s: float = 1.0e12
    gamma_s: float = 1.0e10
    duration_s: float = 5.0e-10
    n_steps: int = 200
    rho_ee_0: float = 1.0
    max_steps: int = 5000

    def __post_init__(self) -> None:
        if self.omega_rad_s < 0 or self.gamma_s <= 0:
            raise ValueError("omega_rad_s >= 0 and gamma_s > 0 required")
        if self.duration_s <= 0 or self.n_steps < 2:
            raise ValueError("duration_s > 0 and n_steps >= 2 required")
        if not 0.0 <= self.rho_ee_0 <= 1.0:
            raise ValueError("rho_ee_0 must lie in [0, 1]")
        if self.n_steps > self.max_steps:
            raise ValueError(f"n_steps exceeds max_steps={self.max_steps}")


@dataclass(frozen=True)
class QuantumSourceResult:
    times_s: np.ndarray
    rho_traj: np.ndarray
    event_flux_s: np.ndarray
    yield_dimensionless: float
    diagnostics: Dict[str, Any]


def _hamiltonian_J(omega_rad_s: float) -> np.ndarray:
    # H = ħ ω/2 σ_z on basis [e, g]
    half = 0.5 * _HBAR_J_S * float(omega_rad_s)
    return np.array([[half, 0.0], [0.0, -half]], dtype=np.complex128)


def _rhs(rho: np.ndarray, h: np.ndarray, gamma: float) -> np.ndarray:
    # unitary
    comm = h @ rho - rho @ h
    out = (-1j / _HBAR_J_S) * comm
    # Lindblad L = sqrt(gamma) |g><e| = sqrt(gamma) * [[0,0],[1,0]]
    # D[L]ρ = L ρ L† - 1/2 {L†L, ρ}
    # L†L = gamma |e><e|
    pee = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.complex128)
    l_rho_ld = np.zeros((2, 2), dtype=np.complex128)
    # L ρ L† = gamma * |g><e| ρ |e><g| = gamma * ρ_ee * |g><g|
    l_rho_ld[1, 1] = gamma * rho[0, 0]
    anticom = pee @ rho + rho @ pee
    out += l_rho_ld - 0.5 * gamma * anticom
    return out


def _hermitize(rho: np.ndarray) -> np.ndarray:
    return 0.5 * (rho + rho.conj().T)


def evolve_sink_source(config: QuantumSourceConfig | None = None) -> QuantumSourceResult:
    """Propagate ρ with RK4; return flux φ(t)=γ ρ_ee and yield Y=∫φ dt."""
    cfg = config or QuantumSourceConfig()
    times = np.linspace(0.0, cfg.duration_s, cfg.n_steps)
    dt = float(times[1] - times[0])
    h = _hamiltonian_J(cfg.omega_rad_s)
    rho = np.array(
        [[cfg.rho_ee_0, 0.0], [0.0, 1.0 - cfg.rho_ee_0]],
        dtype=np.complex128,
    )
    traj = np.empty((cfg.n_steps, 2, 2), dtype=np.complex128)
    flux = np.empty(cfg.n_steps, dtype=float)
    traj[0] = rho
    flux[0] = cfg.gamma_s * float(np.real(rho[0, 0]))

    for i in range(1, cfg.n_steps):
        k1 = _rhs(rho, h, cfg.gamma_s)
        k2 = _rhs(rho + 0.5 * dt * k1, h, cfg.gamma_s)
        k3 = _rhs(rho + 0.5 * dt * k2, h, cfg.gamma_s)
        k4 = _rhs(rho + dt * k3, h, cfg.gamma_s)
        rho = rho + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        rho = _hermitize(rho)
        traj[i] = rho
        flux[i] = cfg.gamma_s * float(np.real(rho[0, 0]))

    # trapezoid yield (np.trapezoid on NumPy ≥2; fall back for older runtimes)
    _trap = getattr(np, "trapezoid", None) or np.trapz
    yield_y = float(_trap(flux, times))
    pops = np.real(np.diagonal(traj, axis1=1, axis2=2))
    traces = np.real(np.trace(traj, axis1=1, axis2=2))
    herm = np.max(np.abs(traj - np.conjugate(np.transpose(traj, (0, 2, 1)))))
    evals = np.linalg.eigvalsh(_hermitize(traj[-1]))
    diagnostics = {
        "schema": "neurotopology_sim.quantum_source_membrane_relay.source.v1",
        "data_policy": "SYNTHETIC_MODEL_ONLY",
        "trace_mean": float(np.mean(traces)),
        "trace_max_abs_err": float(np.max(np.abs(traces - 1.0))),
        "population_sum_final": float(np.sum(pops[-1])),
        "min_eigenvalue_final": float(np.min(evals)),
        "hermiticity_residual": float(herm),
        "dt_s": dt,
        "n_steps": int(cfg.n_steps),
        "gamma_s": float(cfg.gamma_s),
        "omega_rad_s": float(cfg.omega_rad_s),
        "scientific_claim": False,
    }
    return QuantumSourceResult(
        times_s=times,
        rho_traj=traj,
        event_flux_s=flux,
        yield_dimensionless=yield_y,
        diagnostics=diagnostics,
    )
