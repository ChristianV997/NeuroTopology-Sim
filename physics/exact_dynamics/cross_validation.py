"""DM1 telemetry validation and second-order Suzuki convergence metrics."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.linalg import expm
from .lindblad_reference import validate_density_trajectory


@dataclass(frozen=True)
class TrajectoryComparison:
    max_frobenius_error: float
    mean_frobenius_error: float
    valid: bool


def density_from_telemetry(records: list[dict[str, object]]) -> np.ndarray:
    """Decode DM1 real/imaginary payload and reject unphysical telemetry."""
    states = []
    for record in records:
        real = np.asarray(record["matrix_real"], float); imaginary = np.asarray(record["matrix_imag"], float)
        if real.shape != imaginary.shape: raise ValueError("DM1 real/imaginary density shapes differ")
        states.append(real + 1j * imaginary)
    trajectory = np.asarray(states, complex); validate_density_trajectory(trajectory); return trajectory


def compare_density_trajectories(reference: np.ndarray, cloud: np.ndarray, *, tolerance: float = 1e-4) -> TrajectoryComparison:
    """Compare same-grid trajectories only after both satisfy physical checks."""
    validate_density_trajectory(reference); validate_density_trajectory(cloud)
    if reference.shape != cloud.shape: raise ValueError("reference/cloud trajectory shapes differ")
    errors = np.linalg.norm(reference - cloud, axis=(1, 2))
    return TrajectoryComparison(float(np.max(errors)), float(np.mean(errors)), bool(np.max(errors) < tolerance))


def second_order_step(components: tuple[np.ndarray, ...], delta_t_s: float, hbar_J_s: float) -> np.ndarray:
    """Symmetric second-order product for a supplied Hamiltonian decomposition."""
    if not components or delta_t_s <= 0 or hbar_J_s <= 0: raise ValueError("components, timestep, and hbar must be positive")
    dimension = components[0].shape[0]; unitary = np.eye(dimension, dtype=complex)
    for component in components: unitary = expm(-1j * component * delta_t_s / (2 * hbar_J_s)) @ unitary
    for component in reversed(components): unitary = expm(-1j * component * delta_t_s / (2 * hbar_J_s)) @ unitary
    return unitary


def second_order_local_error(components: tuple[np.ndarray, ...], delta_t_s: float, hbar_J_s: float) -> float:
    """Frobenius local error against exp(-i sum(H_j) dt/hbar)."""
    exact = expm(-1j * sum(components) * delta_t_s / hbar_J_s)
    return float(np.linalg.norm(second_order_step(components, delta_t_s, hbar_J_s) - exact))
