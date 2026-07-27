"""Optional exact-dynamics backend adapters and convergence contracts."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Literal
import numpy as np
from .hamiltonian_builder import HamiltonianModel


class OptionalBackendUnavailable(RuntimeError):
    """Raised instead of silently replacing an exact backend with a heuristic."""


@dataclass(frozen=True)
class BathConfig:
    """Drude-Lorentz bath parameters: reorganisation energy J, cutoff s^-1, T K."""
    reorganization_energy_J: float
    cutoff_rate_s: float
    temperature_K: float
    coupling_sites: tuple[int, ...]
    time_unit_s: float = 1e-15
    time_step_s: float = 5e-16
    memory_time_s: float = 2e-14
    epsrel: float = 1e-7

    def __post_init__(self) -> None:
        if (self.reorganization_energy_J <= 0 or self.cutoff_rate_s <= 0
                or self.temperature_K <= 0 or self.time_unit_s <= 0
                or self.time_step_s <= 0 or self.memory_time_s <= 0
                or not 0 < self.epsrel < 1):
            raise ValueError("bath parameters are outside physical bounds")


@dataclass(frozen=True)
class DynamicsResult:
    """Density matrices on a fixed time grid with explicit convergence status."""
    times_s: np.ndarray
    density_matrices: np.ndarray
    backend: str
    converged: bool
    trace_residual: float
    positivity_residual: float
    notes: str


def available_backends() -> dict[str, bool]:
    """Report optional package capability without importing their heavy runtimes."""
    return {"oqupy_pt_tempo": importlib.util.find_spec("oqupy") is not None,
            "pyheom": importlib.util.find_spec("pyheom") is not None,
            "pyttn": importlib.util.find_spec("pyttn") is not None}


def _validate_initial(model: HamiltonianModel, initial_rho: np.ndarray, times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rho = np.asarray(initial_rho, complex); times = np.asarray(times_s, float)
    n = model.hamiltonian_J.shape[0]
    if rho.shape != (n, n) or times.ndim != 1 or times.size < 2 or np.any(np.diff(times) <= 0): raise ValueError("initial rho or time grid is invalid")
    if not np.allclose(rho, rho.conj().T, atol=1e-12) or not np.isclose(np.trace(rho), 1.0, atol=1e-12): raise ValueError("initial density matrix must be Hermitian and trace one")
    return rho, times


def calibration_reference(model: HamiltonianModel, initial_rho: np.ndarray, times_s: np.ndarray, *, dephasing_rate_s: float) -> DynamicsResult:
    """Analytic dephasing reference for tests only; never eligible for falsification."""
    rho0, times = _validate_initial(model, initial_rho, times_s)
    if dephasing_rate_s < 0: raise ValueError("dephasing_rate_s must be non-negative")
    values, vectors = np.linalg.eigh(model.hamiltonian_J); transformed = vectors.conj().T @ rho0 @ vectors
    states = np.empty((times.size, rho0.shape[0], rho0.shape[1]), complex)
    hbar = 1.054571817e-34
    for index, time in enumerate(times):
        phases = np.exp(-1j * (values[:, None] - values[None, :]) * time / hbar)
        decay = np.exp(-dephasing_rate_s * time) * np.ones_like(phases); np.fill_diagonal(decay, 1.0)
        states[index] = vectors @ (transformed * phases * decay) @ vectors.conj().T
    traces = np.trace(states, axis1=1, axis2=2); positivity = [max(0.0, -float(np.min(np.linalg.eigvalsh(state).real))) for state in states]
    return DynamicsResult(times, states, "calibration_reference", False, float(np.max(np.abs(traces - 1))), float(max(positivity)), "Analytic calibration only; not a non-Markovian exact backend.")


def run_oqupy_pt_tempo(model: HamiltonianModel, initial_rho: np.ndarray, times_s: np.ndarray, bath: BathConfig | None) -> DynamicsResult:
    """Run a convergence-labelled TEMPO calculation with a Drude--Lorentz bath.

    OQuPy works in units where :math:`\\hbar=k_B=1`.  This adapter converts the
    SI Hamiltonian and bath parameters using ``bath.time_unit_s``.  The bath is
    a collective diagonal pure-dephasing coupling over ``coupling_sites``;
    this is a stated modelling assumption, not a molecular-dynamics-derived
    protein/water coupling operator.  The function refuses nonuniform grids
    because TEMPO uses a fixed time step.
    """
    if not available_backends()["oqupy_pt_tempo"]:
        raise OptionalBackendUnavailable("OQuPy is not installed; install the exact CPU environment before PT-TEMPO execution")
    rho, times = _validate_initial(model, initial_rho, times_s)
    if bath is None:
        raise ValueError("a Drude--Lorentz BathConfig is required")
    if max(bath.coupling_sites, default=-1) >= model.hamiltonian_J.shape[0] or min(bath.coupling_sites, default=0) < 0:
        raise ValueError("bath coupling_sites must index the Hamiltonian")
    intervals = np.diff(times)
    if not np.allclose(intervals, intervals[0], rtol=1e-10, atol=max(1e-30, abs(intervals[0]) * 1e-12)):
        raise ValueError("OQuPy TEMPO requires a uniform physical time grid")
    if not np.isclose(intervals[0], bath.time_step_s, rtol=1e-10, atol=max(1e-30, bath.time_step_s * 1e-12)):
        raise ValueError("time grid spacing must equal BathConfig.time_step_s")

    import oqupy
    hbar = 1.054571817e-34
    boltzmann = 1.380649e-23
    # Global energy offsets are dynamically irrelevant but force unnecessarily
    # fast tensor propagation, so subtract only trace(H)/N before rescaling.
    hamiltonian = np.asarray(model.hamiltonian_J, complex)
    hamiltonian = hamiltonian - np.eye(hamiltonian.shape[0]) * np.trace(hamiltonian) / hamiltonian.shape[0]
    hamiltonian_scaled = hamiltonian * bath.time_unit_s / hbar
    coupling = np.zeros(hamiltonian.shape[0], float)
    coupling[list(bath.coupling_sites)] = 1.0
    coupling -= coupling.mean()
    norm = float(np.max(np.abs(coupling)))
    if norm == 0.0:
        raise ValueError("bath coupling_sites must produce a nonconstant coupling operator")
    coupling_operator = np.diag(coupling / norm)
    lambda_scaled = bath.reorganization_energy_J * bath.time_unit_s / hbar
    gamma_scaled = bath.cutoff_rate_s * bath.time_unit_s
    temperature_scaled = boltzmann * bath.temperature_K * bath.time_unit_s / hbar

    def drude_lorentz(omega: float) -> float:
        value = float(omega)
        return float(2.0 * lambda_scaled * gamma_scaled * value / (value * value + gamma_scaled * gamma_scaled))

    correlations = oqupy.CustomSD(
        drude_lorentz,
        cutoff=max(50.0 * gamma_scaled, 1.0),
        cutoff_type="hard",
        temperature=temperature_scaled,
    )
    system = oqupy.System(hamiltonian_scaled)
    environment = oqupy.Bath(coupling_operator, correlations)
    parameters = oqupy.TempoParameters(
        dt=bath.time_step_s / bath.time_unit_s,
        tcut=bath.memory_time_s / bath.time_unit_s,
        epsrel=bath.epsrel,
    )
    dynamics = oqupy.tempo_compute(
        system=system,
        bath=environment,
        initial_state=rho,
        start_time=0.0,
        end_time=float(times[-1] / bath.time_unit_s),
        parameters=parameters,
        progress_type="silent",
    )
    states = np.asarray(dynamics.states, complex)
    returned_times = np.asarray(dynamics.times, float) * bath.time_unit_s
    if states.shape != (times.size, rho.shape[0], rho.shape[1]) or not np.allclose(returned_times, times, rtol=1e-10, atol=max(1e-30, bath.time_step_s * 1e-10)):
        raise RuntimeError("OQuPy returned a trajectory inconsistent with the requested uniform time grid")
    traces = np.trace(states, axis1=1, axis2=2)
    positivity = [max(0.0, -float(np.min(np.linalg.eigvalsh((state + state.conj().T) / 2.0).real))) for state in states]
    return DynamicsResult(
        times,
        states,
        "oqupy_tempo_drude_lorentz",
        True,
        float(np.max(np.abs(traces - 1.0))),
        float(max(positivity)),
        "OQuPy 0.5 TEMPO with SI-rescaled Drude--Lorentz spectral density; convergence still requires independent dt/tcut/epsrel refinement.",
    )
