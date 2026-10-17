"""Average-referenced CSD operator in two independent linear-algebra forms.

Operator (channels x channels), applied to channel-by-time data V as CSD = M @ V:

    M = H^T C / R^2

where G and H are the Legendre-series matrices evaluated on the cosines of the
angles between unit sensor vectors (MNE convention, see legendre.py), and C
is the coefficient matrix that solves, column by column,

    [[G + lambda2*I, 1], [1^T, 0]] [c; mu] = [Z; 0],   Z = I - (1/n) 1 1^T.

The zero-sum constraint 1^T c = 0 is the average-reference condition on the
coefficients. The projection form

    Gi = inv(G + lambda2*I),  TC = Gi 1,  sgi = 1^T Gi 1,
    C  = Gi Z - TC (1^T Gi Z) / sgi

is an algebraically equivalent second derivation. Both are kept so that tests
can compare them. R is the sphere radius in the same length unit as the sensor
positions, so M carries units of 1/length^2 (V -> V/m^2 for positions in m).
"""
from __future__ import annotations

import math
from typing import Literal, Sequence

import numpy as np

from .legendre import g_function, h_function

Method = Literal["kkt", "projection"]


class OperatorInputError(ValueError):
    """Positions, radius, or regularisation outside the reference's domain."""


def unit_vectors(positions, origin: Sequence[float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    pos = np.asarray(positions, dtype=float)
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise OperatorInputError("positions must have shape (n_channels, 3)")
    if pos.shape[0] < 2:
        raise OperatorInputError("at least two channels are required for an average reference")
    if not np.all(np.isfinite(pos)):
        raise OperatorInputError("positions must be finite")
    centred = pos - np.asarray(origin, dtype=float)
    norms = np.linalg.norm(centred, axis=1)
    if np.any(norms <= 0.0):
        raise OperatorInputError("a sensor position coincides with the sphere origin")
    return centred / norms[:, None]


def legendre_matrices(unit: np.ndarray, *, stiffness: float = 4.0, n_terms: int = 50) -> tuple[np.ndarray, np.ndarray]:
    cos = np.clip(unit @ unit.T, -1.0, 1.0)
    return g_function(cos, stiffness, n_terms), h_function(cos, stiffness, n_terms)


def regularise(G: np.ndarray, lambda2: float) -> np.ndarray:
    if not (0.0 <= lambda2 < 1.0):
        raise OperatorInputError("lambda2 must satisfy 0 <= lambda2 < 1")
    return G + lambda2 * np.eye(G.shape[0])


def centering_matrix(n: int) -> np.ndarray:
    return np.eye(n) - np.ones((n, n)) / n


def kkt_coefficients(G_reg: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    n = G_reg.shape[0]
    system = np.zeros((n + 1, n + 1))
    system[:n, :n] = G_reg
    system[:n, n] = 1.0
    system[n, :n] = 1.0
    extended = np.zeros((n + 1, rhs.shape[1]))
    extended[:n] = rhs
    solution = np.linalg.solve(system, extended)
    return solution[:n]


def projection_coefficients(G_reg: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    n = G_reg.shape[0]
    Gi = np.linalg.inv(G_reg)
    ones = np.ones(n)
    TC = Gi @ ones
    sgi = float(ones @ Gi @ ones)
    Cp = Gi @ rhs
    c0 = Cp.sum(axis=0) / sgi
    return Cp - np.outer(TC, c0)


def csd_operator(
    positions,
    *,
    radius: float,
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    lambda2: float = 1e-5,
    stiffness: float = 4.0,
    n_terms: int = 50,
    method: Method = "kkt",
) -> np.ndarray:
    if not (math.isfinite(radius) and radius > 0.0):
        raise OperatorInputError("radius must be finite and > 0")
    unit = unit_vectors(positions, origin)
    G, H = legendre_matrices(unit, stiffness=stiffness, n_terms=n_terms)
    G_reg = regularise(G, lambda2)
    Z = centering_matrix(G.shape[0])
    if method == "kkt":
        C = kkt_coefficients(G_reg, Z)
    elif method == "projection":
        C = projection_coefficients(G_reg, Z)
    else:
        raise OperatorInputError(f"unknown method {method!r}")
    return H.T @ C / radius**2


def apply_csd(M: np.ndarray, data: np.ndarray) -> np.ndarray:
    data = np.asarray(data, dtype=float)
    if data.shape[0] != M.shape[0]:
        raise OperatorInputError("data must have one row per channel")
    return M @ data


def csd_operator_regularised_after_inverse(
    positions, *, radius: float, origin: Sequence[float] = (0.0, 0.0, 0.0),
    lambda2: float = 1e-5, stiffness: float = 4.0, n_terms: int = 50,
) -> np.ndarray:
    """Discriminating variant: lambda2 added to inv(G) instead of G (not the reference)."""
    unit = unit_vectors(positions, origin)
    G, H = legendre_matrices(unit, stiffness=stiffness, n_terms=n_terms)
    Gi = np.linalg.inv(G) + lambda2 * np.eye(G.shape[0])
    n = G.shape[0]
    ones = np.ones(n)
    Z = centering_matrix(n)
    TC = Gi @ ones
    sgi = float(ones @ Gi @ ones)
    Cp = Gi @ Z
    C = Cp - np.outer(TC, Cp.sum(axis=0) / sgi)
    return H.T @ C / radius**2


def csd_operator_without_sum_constraint(
    positions, *, radius: float, origin: Sequence[float] = (0.0, 0.0, 0.0),
    lambda2: float = 1e-5, stiffness: float = 4.0, n_terms: int = 50,
) -> np.ndarray:
    """Discriminating variant: centring kept, zero-sum coefficient constraint dropped."""
    unit = unit_vectors(positions, origin)
    G, H = legendre_matrices(unit, stiffness=stiffness, n_terms=n_terms)
    G_reg = regularise(G, lambda2)
    C = np.linalg.inv(G_reg) @ centering_matrix(G.shape[0])
    return H.T @ C / radius**2
