"""Legendre-series spherical-spline functions, evaluated without MNE.

Formulas (stated mathematically; not transcribed from any implementation):

    g_m(x) = sum_{n=1..N} (2n+1) / ((n(n+1))^m * 4*pi) * P_n(x)
    h_m(x) = sum_{n=1..N} (2n+1) / ((n(n+1))^(m-1) * 4*pi) * P_n(x)

with stiffness m, N = n_legendre_terms (inclusive), P_n the Legendre
polynomials, and no P_0 term and no leading minus sign. These are the
conventions the pinned MNE release uses; see pin.py for the verified source.
P_n is evaluated with the three-term recurrence (Bonnet), independently of
numpy.polynomial, so the two can be cross-checked.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def legendre_polynomials(n_max: int, x: np.ndarray) -> list[np.ndarray]:
    """Return [P_0(x), ..., P_{n_max}(x)] for an array ``x`` in [-1, 1]."""
    if n_max < 1:
        raise ValueError("n_max must be >= 1")
    x = np.asarray(x, dtype=float)
    if np.any(~np.isfinite(x)) or np.any(np.abs(x) > 1.0 + 1e-12):
        raise ValueError("Legendre arguments must be finite and in [-1, 1]")
    polys = [np.ones_like(x), x.copy()]
    for n in range(1, n_max):
        polys.append(((2 * n + 1) * x * polys[n] - n * polys[n - 1]) / (n + 1))
    return polys[: n_max + 1]


def _series(x: np.ndarray, stiffness: float, n_terms: int, exponent_shift: int) -> np.ndarray:
    if n_terms < 1:
        raise ValueError("n_legendre_terms must be >= 1")
    polys = legendre_polynomials(n_terms, x)
    total = np.zeros_like(np.asarray(x, dtype=float))
    for n in range(1, n_terms + 1):
        denominator = (n * (n + 1)) ** (stiffness - exponent_shift) * 4.0 * math.pi
        total = total + (2 * n + 1) / denominator * polys[n]
    return total


def g_function(x, stiffness: float = 4.0, n_terms: int = 50) -> np.ndarray:
    return _series(np.asarray(x, dtype=float), stiffness, n_terms, exponent_shift=0)


def h_function(x, stiffness: float = 4.0, n_terms: int = 50) -> np.ndarray:
    return _series(np.asarray(x, dtype=float), stiffness, n_terms, exponent_shift=1)


def numpy_crosscheck_coefficients(stiffness: float, n_terms: int, shift: int) -> Sequence[float]:
    """Coefficient list (c_0 = 0, c_n for n = 1..N) for numpy.polynomial.legendre.legval."""
    return [0.0] + [
        (2 * n + 1) / ((n * (n + 1)) ** (stiffness - shift) * 4.0 * math.pi)
        for n in range(1, n_terms + 1)
    ]


# Values exactly as stated in the Round 6 brief. The brief is the only source for
# them: no branch or file in the repository contains them (see the report).
PROPOSAL_CONSTANTS: dict[str, tuple[float, int, float]] = {
    "G(1)": (1.0, 0, 0.0152607616970611),
    "G(0)": (0.0, 0, -0.000151919699050514),
    "H(1)": (1.0, 1, 0.0321583490430606),
    "H(0)": (0.0, 1, -0.000891062383022325),
}
