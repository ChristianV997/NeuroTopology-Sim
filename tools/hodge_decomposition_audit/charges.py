"""Separate raw integer face charges from phase-confidence / Hodge weights.

Raw integer charges are algebraic functions of the unweighted coboundary d1
applied to a phase-like 1-form. Changing the diagonal Hodge edge weights W1
must not alter those integers, while the weighted 1-form decomposition may change.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

import numpy as np

from tools.hodge_decomposition_audit.incidence import OrientedComplex


TWO_PI = 2.0 * np.pi


def phase_like_omega_from_vertex_potential(
    complex_: OrientedComplex,
    theta: Sequence[float],
) -> np.ndarray:
    """omega = wrap(d0 @ theta) into (-pi, pi]."""
    d0 = complex_.d0()
    raw = d0 @ np.asarray(theta, dtype=float)
    return (raw + np.pi) % TWO_PI - np.pi


def raw_integer_face_charges(complex_: OrientedComplex, omega: Sequence[float]) -> np.ndarray:
    """Integer face charges q = round((d1 @ omega) / 2π).

    Algebraic / combinatorial identity once omega is fixed: independent of W1.
    """
    if complex_.num_triangles == 0:
        return np.zeros(0, dtype=np.int64)
    d1 = complex_.d1()
    face_phase = d1 @ np.asarray(omega, dtype=float)
    return np.rint(face_phase / TWO_PI).astype(np.int64)


def confidence_weighted_scores(
    charges: Sequence[int],
    face_confidence: Sequence[float],
) -> np.ndarray:
    """Weighted scores s_t = w_t * q_t (not integer charges)."""
    q = np.asarray(charges, dtype=float)
    w = np.asarray(face_confidence, dtype=float)
    if q.shape != w.shape:
        raise ValueError("charge/confidence shape mismatch")
    return w * q


def compare_charges_under_weight_change(
    complex_: OrientedComplex,
    omega: Sequence[float],
    weights_a: Sequence[float],
    weights_b: Sequence[float],
) -> Dict[str, object]:
    """Show integer charges invariant while documenting that W1 differs."""
    q_a = raw_integer_face_charges(complex_, omega)
    q_b = raw_integer_face_charges(complex_, omega)
    # Charges do not take weights; compare identical inputs under two weight plans.
    return {
        "charges_a": [int(x) for x in q_a],
        "charges_b": [int(x) for x in q_b],
        "charges_identical": bool(np.array_equal(q_a, q_b)),
        "weights_a": [float(x) for x in weights_a],
        "weights_b": [float(x) for x in weights_b],
        "weights_differ": not np.allclose(np.asarray(weights_a, float), np.asarray(weights_b, float)),
        "identity_class": "algebraic_charge_independence_from_W1",
    }


def circulatory_integer_omega(complex_: OrientedComplex, strength: int = 1) -> Tuple[np.ndarray, str]:
    """Build a circulatory phase-like 1-form on a 3-cycle when present.

    Uses edges (0,1),(1,2),(0,2) when they exist. Returns (omega, note).
    """
    omega = np.zeros(complex_.num_edges, dtype=float)
    emap = complex_.edge_index
    needed = ((0, 1), (1, 2), (0, 2))
    if not all(e in emap for e in needed):
        return omega, "cycle_edges_absent"
    # Circulation corresponding to +strength winding around the triangle/cycle.
    omega[emap[(0, 1)]] = strength * TWO_PI / 3.0
    omega[emap[(1, 2)]] = strength * TWO_PI / 3.0
    omega[emap[(0, 2)]] = -strength * TWO_PI / 3.0
    return omega, "c3_circulation"
