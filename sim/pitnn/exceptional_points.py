"""Deterministic two-mode non-Hermitian exceptional-point scanner."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EPScanConfig:
    pump_values: np.ndarray
    loss_values: np.ndarray
    coupling_s: float = 1.0
    epsilon_threshold: float = 1e-3
    delta_threshold: float = 1e-2


def two_mode_hamiltonian(gamma_pump_s: float, gamma_loss_s: float, coupling_s: float = 1.0) -> np.ndarray:
    """Return a dimensionless-rate 2x2 non-Hermitian Hamiltonian."""
    if min(gamma_pump_s, gamma_loss_s, coupling_s) < 0:
        raise ValueError("rates and coupling must be non-negative")
    return np.array([[-0.5j * gamma_loss_s, coupling_s],
                     [coupling_s, 0.5j * gamma_pump_s]], dtype=complex)


def scan_exceptional_points(config: EPScanConfig) -> dict:
    """Scan pump/loss space and report spectral-gap/fidelity EP candidates."""
    pumps, losses = np.asarray(config.pump_values, dtype=float), np.asarray(config.loss_values, dtype=float)
    if pumps.ndim != 1 or losses.ndim != 1 or len(pumps) == 0 or len(losses) == 0 or np.any(pumps < 0) or np.any(losses < 0):
        raise ValueError("pump/loss grids must be non-empty one-dimensional non-negative arrays")
    gaps = np.empty((len(pumps), len(losses))); fidelities = np.empty_like(gaps); spectra = np.empty((len(pumps), len(losses), 2), complex)
    for i, pump in enumerate(pumps):
        for j, loss in enumerate(losses):
            values, vectors = np.linalg.eig(two_mode_hamiltonian(float(pump), float(loss), config.coupling_s))
            order = np.argsort(values.real); values, vectors = values[order], vectors[:, order]
            spectra[i, j] = values
            gaps[i, j] = abs(values[0] - values[1])
            fidelities[i, j] = abs(np.vdot(vectors[:, 0], vectors[:, 1])) / (np.linalg.norm(vectors[:, 0]) * np.linalg.norm(vectors[:, 1]))
    candidates = np.argwhere((gaps < config.epsilon_threshold) & (fidelities > 1.0 - config.delta_threshold))
    best = np.unravel_index(np.argmin(gaps), gaps.shape)
    return {"pump_values": pumps.tolist(), "loss_values": losses.tolist(), "spectra": spectra,
            "gaps": gaps, "fidelities": fidelities, "candidates": candidates.tolist(),
            "best": {"pump_s": float(pumps[best[0]]), "loss_s": float(losses[best[1]]), "gap": float(gaps[best])},
            "curvature_proxy": float(gaps[best]), "thermodynamic_drag_proxy": float(gaps[best] + abs(pumps[best[0]] - losses[best[1]]) * 1e-3)}


def find_exceptional_point_fast() -> dict:
    """Use the bounded SciPy optimizer without changing grid-scan behaviour."""
    from .exceptional_points_fast import optimize_exceptional_point
    return optimize_exceptional_point()
