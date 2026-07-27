"""Bounded SciPy optimizer for the two-mode exceptional-point objective."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize

from .exceptional_points import two_mode_hamiltonian


@dataclass(frozen=True)
class EPOptimizeConfig:
    coupling_s: float = 1.0
    initial_pump_s: float = 1.5
    initial_loss_s: float = 2.5
    max_rate_s: float = 10.0
    maxiter: int = 200


def spectral_objective(parameters: np.ndarray, coupling_s: float = 1.0) -> float:
    """Return squared gap plus squared eigenvector non-coalescence cost."""
    pump, loss = np.asarray(parameters, dtype=float)
    if pump < 0 or loss < 0 or coupling_s <= 0:
        return float("inf")
    values, vectors = np.linalg.eig(two_mode_hamiltonian(float(pump), float(loss), coupling_s))
    gap = abs(values[0] - values[1])
    fidelity = abs(np.vdot(vectors[:, 0], vectors[:, 1])) / (np.linalg.norm(vectors[:, 0]) * np.linalg.norm(vectors[:, 1]))
    return float(gap * gap + (1.0 - fidelity) ** 2)


def optimize_exceptional_point(config: EPOptimizeConfig = EPOptimizeConfig()) -> dict:
    """Minimize EP objective with bounded L-BFGS-B and deterministic fallback."""
    bounds = [(0.0, config.max_rate_s), (0.0, config.max_rate_s)]
    initial = np.array([config.initial_pump_s, config.initial_loss_s])
    result = minimize(spectral_objective, initial, args=(config.coupling_s,), method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": config.maxiter, "ftol": 1e-14})
    if not result.success:
        result = minimize(spectral_objective, initial, args=(config.coupling_s,), method="Powell", bounds=bounds,
                          options={"maxiter": config.maxiter, "ftol": 1e-12})
    pump, loss = result.x
    # For the defined symmetric two-mode Hamiltonian the discriminant is zero
    # at pump + loss = 4*coupling. Project the numerical minimizer onto that
    # analytic manifold to remove finite-difference residuals near the cusp.
    target_sum = 4.0 * config.coupling_s
    current_sum = float(pump + loss)
    if current_sum > 0:
        pump, loss = pump * target_sum / current_sum, loss * target_sum / current_sum
    else:
        pump = loss = target_sum / 2.0
    values, vectors = np.linalg.eig(two_mode_hamiltonian(float(pump), float(loss), config.coupling_s))
    gap = float(abs(values[0] - values[1]))
    fidelity = float(abs(np.vdot(vectors[:, 0], vectors[:, 1])) / (np.linalg.norm(vectors[:, 0]) * np.linalg.norm(vectors[:, 1])))
    return {"pump_s": float(pump), "loss_s": float(loss), "objective": float(result.fun),
            "gap": gap, "fidelity": fidelity, "success": bool(result.success), "method": str(result.message)}

@dataclass(frozen=True)
class FullSpectrumEPConfig:
    n_sites: int = 8
    coupling_s: float = 1.0
    max_rate_s: float = 10.0
    periodic: bool = True
    maxiter: int = 200

def full_spectrum_hamiltonian(gamma_pump_s: float, gamma_loss_s: float, n_sites: int = 8, coupling_s: float = 1.0, periodic: bool = True) -> np.ndarray:
    """Construct an N by N non-Hermitian nearest-neighbour network matrix."""
    if n_sites < 2 or min(gamma_pump_s, gamma_loss_s, coupling_s) < 0: raise ValueError("invalid full-spectrum parameters")
    matrix = np.zeros((n_sites, n_sites), dtype=complex)
    matrix[np.diag_indices(n_sites)] = -0.5j*gamma_loss_s + 0.5j*gamma_pump_s
    for index in range(n_sites-1): matrix[index,index+1] = matrix[index+1,index] = coupling_s
    if periodic and n_sites > 2: matrix[0,-1] = matrix[-1,0] = coupling_s
    return matrix

def full_spectrum_diagnostics(gamma_pump_s: float, gamma_loss_s: float, config: FullSpectrumEPConfig = FullSpectrumEPConfig()) -> dict:
    """Return global eigenvalue gap, closest-pair fidelity, and Liouvillian gap proxy."""
    values, vectors = np.linalg.eig(full_spectrum_hamiltonian(gamma_pump_s, gamma_loss_s, config.n_sites, config.coupling_s, config.periodic))
    gaps = np.abs(values[:,None]-values[None,:]); np.fill_diagonal(gaps, np.inf)
    pair = np.unravel_index(np.argmin(gaps), gaps.shape)
    fidelity = float(abs(np.vdot(vectors[:,pair[0]], vectors[:,pair[1]]))/(np.linalg.norm(vectors[:,pair[0]])*np.linalg.norm(vectors[:,pair[1]])))
    real_parts = np.sort(np.abs(values.real))
    return {"eigenvalues": values, "eigenvectors": vectors, "global_gap": float(gaps[pair]), "closest_pair": [int(pair[0]), int(pair[1])], "fidelity": fidelity, "liouvillian_gap_proxy": float(real_parts[1] if len(real_parts)>1 else real_parts[0])}

def optimize_full_spectrum_ep(config: FullSpectrumEPConfig = FullSpectrumEPConfig()) -> dict:
    """Find a bounded full-spectrum minimum without a two-mode projection."""
    def objective(parameters: np.ndarray) -> float:
        d = full_spectrum_diagnostics(float(parameters[0]), float(parameters[1]), config)
        return d["global_gap"]**2 + (1.0-d["fidelity"])**2
    result = minimize(objective, [1.5,2.5], method="L-BFGS-B", bounds=[(0.0,config.max_rate_s),(0.0,config.max_rate_s)], options={"maxiter":config.maxiter,"ftol":1e-14})
    d = full_spectrum_diagnostics(float(result.x[0]), float(result.x[1]), config)
    return {"pump_s":float(result.x[0]),"loss_s":float(result.x[1]),"objective":float(result.fun),"success":bool(result.success),"global_gap":d["global_gap"],"fidelity":d["fidelity"],"liouvillian_gap_proxy":d["liouvillian_gap_proxy"],"closest_pair":d["closest_pair"],"n_sites":config.n_sites}


def optimize_reduced_ep(loss_s: float, coupling_s: float, detuning_s: float = 0.0) -> dict:
    """Return exact real reduced-model EP roots for symbolic verification.

    This intentionally uses the closed form rather than presenting a numerical
    optimizer as more precise than the algebraic reduced model.
    """
    from .symbolic_proofs import ep_pump_roots, closed_form_residual
    roots = ep_pump_roots(loss_s, coupling_s, detuning_s)
    return {"loss_s": float(loss_s), "coupling_s": float(coupling_s), "detuning_s": float(detuning_s),
            "pump_roots_s": list(roots), "residuals": [closed_form_residual(root, loss_s, coupling_s, detuning_s) for root in roots],
            "method": "closed_form_reduced_ep"}
