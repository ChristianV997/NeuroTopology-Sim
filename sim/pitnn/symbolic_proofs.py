"""Closed-form reduced exceptional-point identities for PITNN tests.

These equations apply only to the stated two-mode and block-diagonal four-mode
surrogates. They are not a proof that a biological system realizes an EP.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

@dataclass(frozen=True)
class ReducedEPParameters:
    coupling_s: float
    detuning_s: float = 0.0
    loss_s: float = 0.0

def discriminant(coupling_s: float, detuning_s: float = 0.0) -> float:
    """Return V^2-Delta^2 in squared rate units."""
    if coupling_s < 0 or not np.isfinite(coupling_s) or not np.isfinite(detuning_s):
        raise ValueError("coupling and detuning must be finite with coupling non-negative")
    return float(coupling_s**2 - detuning_s**2)

def ep_pump_roots(loss_s: float, coupling_s: float, detuning_s: float = 0.0) -> tuple[float, float]:
    """Return gamma_EP = Gamma_loss +/- 2 sqrt(V^2-Delta^2)."""
    disc = discriminant(coupling_s, detuning_s)
    if loss_s < 0 or disc < 0:
        raise ValueError("real reduced EP roots require non-negative loss and V^2 >= Delta^2")
    offset = 2.0 * math.sqrt(disc)
    return float(loss_s - offset), float(loss_s + offset)

def reduced_hamiltonian_n2(gamma_pump_s: float, loss_s: float, coupling_s: float, detuning_s: float = 0.0) -> np.ndarray:
    """Return a two-mode non-Hermitian matrix in model rate units."""
    return np.array([[detuning_s - 0.5j*loss_s, coupling_s], [coupling_s, -detuning_s + 0.5j*gamma_pump_s]], dtype=complex)

def reduced_hamiltonian_n4(gamma_pump_s: float, loss_s: float, coupling_s: float, detuning_s: float = 0.0) -> np.ndarray:
    """Return two identical N=2 reduced sectors for symbolic N=4 validation."""
    h2 = reduced_hamiltonian_n2(gamma_pump_s, loss_s, coupling_s, detuning_s)
    return np.block([[h2, np.zeros_like(h2)], [np.zeros_like(h2), h2]])

def closed_form_residual(gamma_pump_s: float, loss_s: float, coupling_s: float, detuning_s: float = 0.0) -> float:
    """Return the exact reduced EP polynomial residual in rate^2 units."""
    return float((gamma_pump_s - loss_s)**2 - 4.0*discriminant(coupling_s, detuning_s))
