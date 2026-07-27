"""FitzHugh-Nagumo membrane field, Stark shift, and CISS coupling utilities."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class FHNConfig:
    duration_s: float = 0.02
    dt_s: float = 1e-5
    input_current: float = 1.2
    resting_potential_V: float = -0.070
    spike_scale_V: float = 0.100


def simulate_fhn(config: FHNConfig = FHNConfig(), input_current_offset: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Integrate FHN dynamics with optional dimensionless current offsets.

    ``input_current_offset`` has shape ``(time,)`` and represents a local
    mesoscale current perturbation; returned membrane voltage is in volts.
    """
    if config.duration_s <= 0 or config.dt_s <= 0 or config.duration_s / config.dt_s > 2e6:
        raise ValueError("invalid FHN duration or timestep")
    times = np.arange(0.0, config.duration_s + config.dt_s / 2, config.dt_s)
    offset = np.zeros(times.size) if input_current_offset is None else np.asarray(input_current_offset, dtype=float).reshape(-1)
    if offset.shape != times.shape or not np.all(np.isfinite(offset)):
        raise ValueError("input_current_offset must be finite with one value per integration time")
    state = np.array([-1.0, -0.6], dtype=float); trajectory = np.empty((len(times), 2))
    def rhs(value: np.ndarray, current_offset: float) -> np.ndarray:
        v, w = value
        return np.array([v - v**3 / 3.0 - w + config.input_current + current_offset, 0.08 * (v + 0.7 - 0.8 * w)])
    for i in range(len(times)):
        trajectory[i] = state
        k1 = rhs(state, offset[i]); k2 = rhs(state + config.dt_s * k1 / 2, offset[i]); k3 = rhs(state + config.dt_s * k2 / 2, offset[i]); k4 = rhs(state + config.dt_s * k3, offset[i])
        state += config.dt_s * (k1 + 2*k2 + 2*k3 + k4) / 6.0
    normalized = (trajectory[:, 0] - np.min(trajectory[:, 0])) / max(np.ptp(trajectory[:, 0]), 1e-15)
    voltage = config.resting_potential_V + config.spike_scale_V * normalized
    return times, voltage, trajectory[:, 1]


def cytosolic_field(voltage_V: np.ndarray, membrane_thickness_m: float = 7e-9,
                    radial_axis: np.ndarray | None = None) -> np.ndarray:
    """Compute ``E=-V/d*r_hat`` in V/m, returning shape ``(time,3)``."""
    voltage = np.asarray(voltage_V, dtype=float).reshape(-1)
    if membrane_thickness_m <= 0 or not np.all(np.isfinite(voltage)):
        raise ValueError("finite voltage and positive membrane thickness required")
    axis = np.array([1.0, 0.0, 0.0]) if radial_axis is None else np.asarray(radial_axis, dtype=float)
    if axis.shape != (3,) or not np.all(np.isfinite(axis)) or np.linalg.norm(axis) == 0:
        raise ValueError("radial_axis must be a finite non-zero vector")
    axis = axis / np.linalg.norm(axis)
    return -(voltage / membrane_thickness_m)[:, None] * axis[None, :]


def stark_shift(delta_dipoles_Cm: np.ndarray, electric_field_Vm: np.ndarray) -> np.ndarray:
    """Return ``-Δμ·E`` in joules for aligned `(sites,3)` arrays."""
    mu, field = np.asarray(delta_dipoles_Cm, dtype=float), np.asarray(electric_field_Vm, dtype=float)
    if mu.ndim != 2 or mu.shape[1] != 3 or field.ndim != 2 or field.shape[1] != 3:
        raise ValueError("dipoles and fields must have shape (N,3)")
    return -np.einsum("ij,ij->i", mu, field) if mu.shape == field.shape else -np.einsum("ij,tj->ti", mu, field)


def ciss_torque(tau0: float, chi_E: float, electric_field_Vm: np.ndarray) -> np.ndarray:
    """Return voltage-gated torque in configured torque units."""
    field = np.asarray(electric_field_Vm, dtype=float)
    if tau0 < 0 or chi_E < 0 or field.shape[-1] != 3 or not np.all(np.isfinite(field)):
        raise ValueError("tau0/chi_E must be non-negative and field shape (...,3)")
    return tau0 * (1.0 + chi_E * np.linalg.norm(field, axis=-1))
