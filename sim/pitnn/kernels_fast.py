"""Optional high-throughput kernels for local os-LLG evolution.

The NumPy implementation is deterministic and allocation-conscious. Numba is
used only when installed; no GPU library is required. Arrays use `(N,3)`
float64 spin states and all fields are in the caller's model units.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import numpy as np

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    NUMBA_AVAILABLE = False
    def njit(*args: object, **kwargs: object):
        return lambda function: function


@njit(cache=True, fastmath=True)
def _heun_step_numba(spins: np.ndarray, noise_a: np.ndarray, noise_b: np.ndarray, dt: float,
                     exchange: float, dmi: float, damping: float, ciss_torque: float) -> np.ndarray:
    """Compiled normalized local Heun update; arrays are `(N,3)` float64."""
    n = spins.shape[0]
    field_a = np.zeros((n, 3)); k1 = np.zeros((n, 3)); predictor = np.empty((n, 3))
    for i in range(n):
        if i == 0:
            left0 = left1 = left2 = 0.0; right0, right1, right2 = spins[1, 0], spins[1, 1], spins[1, 2]
        elif i == n - 1:
            left0, left1, left2 = spins[n-2, 0], spins[n-2, 1], spins[n-2, 2]; right0 = right1 = right2 = 0.0
        else:
            left0, left1, left2 = spins[i-1, 0], spins[i-1, 1], spins[i-1, 2]
            right0, right1, right2 = spins[i+1, 0], spins[i+1, 1], spins[i+1, 2]
        field_a[i, 0] = exchange * (left0 + right0) + noise_a[i, 0]
        field_a[i, 1] = exchange * (left1 + right1) + noise_a[i, 1]
        field_a[i, 2] = exchange * (left2 + right2) + noise_a[i, 2]
        if i > 0 and i < n-1:
            field_a[i, 1] += dmi * (right2 - left2); field_a[i, 2] -= dmi * (right1 - left1)
        sx, sy, sz = spins[i, 0], spins[i, 1], spins[i, 2]; fx, fy, fz = field_a[i, 0], field_a[i, 1], field_a[i, 2]
        px, py, pz = sy*fz-sz*fy, sz*fx-sx*fz, sx*fy-sy*fx
        dx, dy, dz = sy*pz-sz*py, sz*px-sx*pz, sx*py-sy*px
        k1[i, 0] = -px - damping*dx + ciss_torque*sy
        k1[i, 1] = -py - damping*dy - ciss_torque*sx
        k1[i, 2] = -pz - damping*dz
        predictor[i, 0] = sx + dt*k1[i, 0]; predictor[i, 1] = sy + dt*k1[i, 1]; predictor[i, 2] = sz + dt*k1[i, 2]
        norm = np.sqrt(predictor[i,0]**2 + predictor[i,1]**2 + predictor[i,2]**2)
        predictor[i] /= norm
    output = np.empty_like(spins)
    for i in range(n):
        if i == 0:
            left0 = left1 = left2 = 0.0; right0, right1, right2 = predictor[1, 0], predictor[1, 1], predictor[1, 2]
        elif i == n-1:
            left0, left1, left2 = predictor[n-2, 0], predictor[n-2, 1], predictor[n-2, 2]; right0 = right1 = right2 = 0.0
        else:
            left0, left1, left2 = predictor[i-1, 0], predictor[i-1, 1], predictor[i-1, 2]
            right0, right1, right2 = predictor[i+1, 0], predictor[i+1, 1], predictor[i+1, 2]
        fx = exchange*(left0+right0)+noise_b[i,0]; fy = exchange*(left1+right1)+noise_b[i,1]; fz = exchange*(left2+right2)+noise_b[i,2]
        if i > 0 and i < n-1:
            fy += dmi*(right2-left2); fz -= dmi*(right1-left1)
        sx, sy, sz = predictor[i,0], predictor[i,1], predictor[i,2]
        px, py, pz = sy*fz-sz*fy, sz*fx-sx*fz, sx*fy-sy*fx
        dx, dy, dz = sy*pz-sz*py, sz*px-sx*pz, sx*py-sy*px
        k2x, k2y, k2z = -px-damping*dx+ciss_torque*sy, -py-damping*dy-ciss_torque*sx, -pz-damping*dz
        output[i,0] = spins[i,0] + 0.5*dt*(k1[i,0]+k2x)
        output[i,1] = spins[i,1] + 0.5*dt*(k1[i,1]+k2y)
        output[i,2] = spins[i,2] + 0.5*dt*(k1[i,2]+k2z)
        norm = np.sqrt(output[i,0]**2 + output[i,1]**2 + output[i,2]**2)
        output[i] /= norm
    return output


Backend = Literal["numpy", "numba", "auto"]


@dataclass
class LLGWorkspace:
    """Preallocated `(N,3)` buffers for repeated local LLG operations."""
    field: np.ndarray
    predictor: np.ndarray
    derivative: np.ndarray
    k1: np.ndarray

    @classmethod
    def create(cls, n_spins: int) -> "LLGWorkspace":
        if n_spins < 3:
            raise ValueError("n_spins must be at least 3")
        return cls(*(np.empty((n_spins, 3), dtype=float) for _ in range(4)))


def active_cell_indices(mask: np.ndarray) -> np.ndarray:
    """Return compact active-cell indices for a boolean geometry mask."""
    values = np.asarray(mask, dtype=bool)
    if values.ndim < 1:
        raise ValueError("mask must have at least one dimension")
    return np.flatnonzero(values.ravel())


def exchange_dmi_field(spins: np.ndarray, exchange: float, dmi: float,
                       out: np.ndarray | None = None) -> np.ndarray:
    """Compute nearest-neighbour exchange/DMI field in O(N) memory and time."""
    state = np.asarray(spins, dtype=float)
    if state.ndim != 2 or state.shape[1] != 3 or state.shape[0] < 3 or not np.all(np.isfinite(state)):
        raise ValueError("spins must be finite with shape (N>=3,3)")
    field = np.zeros_like(state) if out is None else out
    if field.shape != state.shape:
        raise ValueError("out must match spins shape")
    field.fill(0.0)
    field[1:-1] = exchange * (state[:-2] + state[2:])
    field[0] = exchange * state[1]; field[-1] = exchange * state[-2]
    field[1:-1, 1] += dmi * (state[2:, 2] - state[:-2, 2])
    field[1:-1, 2] -= dmi * (state[2:, 1] - state[:-2, 1])
    return field


def heun_step(spins: np.ndarray, noise_a: np.ndarray, noise_b: np.ndarray, *, dt: float,
              exchange: float, dmi: float, damping: float, ciss_torque: float,
              workspace: LLGWorkspace | None = None) -> np.ndarray:
    """Advance one normalized Heun step without storing a trajectory history."""
    state = np.asarray(spins, dtype=float)
    if dt <= 0 or noise_a.shape != state.shape or noise_b.shape != state.shape:
        raise ValueError("positive dt and matching noise arrays are required")
    if NUMBA_AVAILABLE:
        return _heun_step_numba(state, np.asarray(noise_a, dtype=float), np.asarray(noise_b, dtype=float),
                                dt, exchange, dmi, damping, ciss_torque)
    ws = workspace or LLGWorkspace.create(state.shape[0])
    def derivative(values: np.ndarray, noise: np.ndarray, out: np.ndarray) -> np.ndarray:
        field = exchange_dmi_field(values, exchange, dmi, ws.field)
        field += noise
        precession = np.cross(values, field)
        damping_term = np.cross(values, precession)
        torque = ciss_torque * np.cross(values, np.array([0.0, 0.0, 1.0]))
        out[:] = -precession - damping * damping_term + torque
        return out
    derivative(state, noise_a, ws.k1)
    ws.predictor[:] = state + dt * ws.k1
    ws.predictor /= np.linalg.norm(ws.predictor, axis=1, keepdims=True)
    k2 = derivative(ws.predictor, noise_b, ws.derivative)
    state = state + 0.5 * dt * (ws.k1 + k2)
    state /= np.linalg.norm(state, axis=1, keepdims=True)
    return state


def resolve_backend(requested: Backend = "auto") -> str:
    """Return the installed deterministic backend name without importing GPUs."""
    if requested not in {"numpy", "numba", "auto"}:
        raise ValueError("backend must be numpy, numba, or auto")
    return "numba" if requested in {"numba", "auto"} and NUMBA_AVAILABLE else "numpy"
