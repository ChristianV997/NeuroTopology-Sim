"""Synthetic fixtures for the Round 6 winding/charge oracle (no EEG / no downloads)."""

from __future__ import annotations

import math

import numpy as np

from tools.experimental_audits.winding_charge_round6.oracle import IndependentComplex


def single_triangle_complex() -> IndependentComplex:
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, math.sqrt(3) / 2.0]], dtype=float)
    return IndependentComplex(
        num_vertices=3,
        edges=((0, 1), (1, 2), (0, 2)),
        triangles=((0, 1, 2),),
        coordinates=coords,
    )


def dipole_complex(separation: float = 4.0) -> IndependentComplex:
    """Two disjoint triangles; barycenters separated by ``separation`` on x."""
    # Left triangle barycenter ~ (0.5, sqrt(3)/6); shift so barycenters at ±sep/2
    h = math.sqrt(3) / 2.0
    left = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, h]], dtype=float)
    right = left.copy()
    # Current barycenters
    b_left = left.mean(axis=0)
    b_right = right.mean(axis=0)
    target_left = np.array([-separation / 2.0, 0.0])
    target_right = np.array([separation / 2.0, 0.0])
    left = left + (target_left - b_left)
    right = right + (target_right - b_right)
    coords = np.vstack([left, right])
    edges = (
        (0, 1),
        (1, 2),
        (0, 2),
        (3, 4),
        (4, 5),
        (3, 5),
    )
    triangles = ((0, 1, 2), (3, 4, 5))
    return IndependentComplex(
        num_vertices=6,
        edges=edges,
        triangles=triangles,
        coordinates=coords,
    )


def vortex_phases_plus() -> np.ndarray:
    return np.array([0.0, 2.0 * np.pi / 3.0, -2.0 * np.pi / 3.0])


def vortex_phases_minus() -> np.ndarray:
    return np.array([0.0, -2.0 * np.pi / 3.0, 2.0 * np.pi / 3.0])


def phases_at_exact_pm_pi() -> dict[str, float]:
    """Exact and near-±π scalars for branch-cut fixtures."""
    return {
        "plus_pi": float(np.pi),
        "minus_pi": float(-np.pi),
        "near_plus_pi": float(np.pi - 1e-12),
        "near_minus_pi": float(-np.pi + 1e-12),
        "just_over_plus_pi": float(np.pi + 1e-12),
        "just_under_minus_pi": float(-np.pi - 1e-12),
    }


def malformed_phase_shapes() -> list[tuple[str, object]]:
    return [
        ("wrong_length", np.array([0.0, 1.0])),
        ("2d", np.zeros((3, 2))),
        ("empty", np.array([])),
    ]


def nonfinite_phase_vectors(n: int = 3) -> list[tuple[str, np.ndarray]]:
    base = np.zeros(n, dtype=float)
    cases = []
    for name, bad in (("nan", float("nan")), ("pos_inf", float("inf")), ("neg_inf", float("-inf"))):
        vec = base.copy()
        vec[0] = bad
        cases.append((name, vec))
    return cases
