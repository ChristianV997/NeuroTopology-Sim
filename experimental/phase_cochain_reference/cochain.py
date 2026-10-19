"""Simplicial phase cochains, wrapped phase differences, and topological charges.

Implements wrapped 1-cochains from vertex 0-cochains, exact integer topological
winding charges on 2-simplices, orientation covariance, confidence-weighted scores,
and spatial charge moments (centroids, signed moments, positive-to-negative separation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .complex import SimplicialComplex


def wrap_to_pi(phase: np.ndarray | float) -> np.ndarray | float:
    """Wrap angle to [-pi, pi).

    Uses the standard modulo definition:
        ((phase + pi) % (2 * pi)) - pi
    """
    arr = np.asarray(phase, dtype=float)
    wrapped = (arr + np.pi) % (2.0 * np.pi) - np.pi
    if np.isscalar(phase):
        return float(wrapped)
    return wrapped


@dataclass(frozen=True)
class Wrapped1Cochain:
    """Wrapped 1-cochain on edges derived from a vertex 0-cochain.

    Attributes:
        raw_difference: d0 @ theta (unwrapped phase differences along edges).
        branch_jumps: Integer jumps n_e with omega = raw_diff - 2pi * n_e.
        cochain: Wrapped 1-cochain omega = wrap_to_pi(raw_diff) in [-pi, pi).
    """

    raw_difference: np.ndarray
    branch_jumps: np.ndarray
    cochain: np.ndarray

    def __post_init__(self) -> None:
        if self.cochain.ndim != 1:
            raise ValueError(f"cochain must be 1D, got ndim={self.cochain.ndim}")


def compute_wrapped_1_cochain(
    complex_: SimplicialComplex,
    vertex_phases: np.ndarray | Sequence[float],
) -> Wrapped1Cochain:
    """Compute the wrapped 1-cochain omega on complex edges from vertex phases theta.

    Mathematical definition (principal branch):
        delta_theta = d0 @ theta
        omega = wrap_to_pi(delta_theta)  # in [-pi, pi)
        n = rint((delta_theta - omega) / (2 * pi))  # integer, omega = raw - 2π n

    Note: ``n = rint(raw / 2π)`` alone is insufficient at half-turns because
    NumPy banker's rounding maps ``rint(0.5) → 0``, leaving ``omega = +π``
    outside ``[-π, π)``. Defining omega via ``wrap_to_pi`` is equivalent to
    the floor branch ``n = floor((raw+π)/2π)`` used by production ``phase_winding``.

    Args:
        complex_: Simplicial complex.
        vertex_phases: Phase angles at vertices in radians, shape (|V|,).

    Returns:
        Wrapped1Cochain instance.
    """
    theta = np.asarray(vertex_phases, dtype=float)
    if theta.shape != (complex_.num_vertices,):
        raise ValueError(
            f"vertex_phases shape {theta.shape} does not match complex num_vertices {complex_.num_vertices}"
        )

    raw_diff = complex_.d0 @ theta
    # Principal-branch wrap first (fail-closed range), then recover integer n.
    omega = np.asarray(wrap_to_pi(raw_diff), dtype=float)
    branch_jumps = np.rint((raw_diff - omega) / (2.0 * np.pi)).astype(int)

    return Wrapped1Cochain(
        raw_difference=raw_diff,
        branch_jumps=branch_jumps,
        cochain=omega,
    )


def compute_topological_charges(
    complex_: SimplicialComplex,
    wrapped_cochain: Wrapped1Cochain,
) -> np.ndarray:
    """Compute exact integer topological charges (windings) on all triangles.

    Proof of integer exactness:
        Since omega = d0(theta) - 2 * pi * n,
        d1(omega) = d1(d0(theta)) - 2 * pi * d1(n).
        Because d1 @ d0 == 0 identically,
        d1(omega) = - 2 * pi * d1(n).
        Therefore:
        q = (1 / (2 * pi)) * d1(omega) = - d1(n) in Z.

    Returns:
        np.ndarray of shape (|T|,) with integer charges (dtype=np.int64).
    """
    if complex_.num_triangles == 0:
        return np.empty((0,), dtype=np.int64)

    # Exact integer calculation
    q_exact = - (complex_.d1 @ wrapped_cochain.branch_jumps).astype(np.int64)

    # Continuous circulation calculation for internal consistency assertion
    circulation = complex_.d1 @ wrapped_cochain.cochain
    q_circ = circulation / (2.0 * np.pi)

    max_err = float(np.max(np.abs(q_circ - q_exact)))
    if max_err > 1e-11:
        raise RuntimeError(
            f"Topological charge calculation discrepancy between circulation and integer coboundary: {max_err}"
        )

    return q_exact


def compute_triangle_loop_winding(
    vertex_phases: np.ndarray | Sequence[float],
    triangle: tuple[int, int, int] | Sequence[int],
) -> int:
    """Compute direct loop winding around an oriented triangle (a -> b -> c -> a).

    For an ordered sequence (a, b, c):
        circulation = wrap(theta_b - theta_a) + wrap(theta_c - theta_b) + wrap(theta_a - theta_c)
        winding = round(circulation / (2 * pi))

    Orientation Covariance:
        - Cyclic (even) permutations preserve the winding: (b, c, a) == (c, a, b) == (a, b, c).
        - Odd permutations (reversals) invert the winding: (a, c, b) == - (a, b, c).
    """
    if len(triangle) != 3:
        raise ValueError(f"Triangle must have 3 vertices, got {triangle}")
    a, b, c = int(triangle[0]), int(triangle[1]), int(triangle[2])
    theta = np.asarray(vertex_phases, dtype=float)

    diff_ab = wrap_to_pi(theta[b] - theta[a])
    diff_bc = wrap_to_pi(theta[c] - theta[b])
    diff_ca = wrap_to_pi(theta[a] - theta[c])

    circ = diff_ab + diff_bc + diff_ca
    winding = int(np.rint(circ / (2.0 * np.pi)))
    return winding


def compute_confidence_weighted_scores(
    charges: np.ndarray,
    weights: np.ndarray | Sequence[float] | None = None,
) -> np.ndarray:
    """Compute confidence-weighted scores s_t = w_t * q_t.

    Note: The raw integer charges q_t remain unweighted and unaltered.
    Weights w_t represent confidence/signal quality in (0, 1].

    Args:
        charges: Integer array of topological charges (|T|,).
        weights: Optional positive weights (|T|,). Defaults to 1.0.

    Returns:
        np.ndarray of weighted scores (|T|,), dtype=float.
    """
    q = np.asarray(charges, dtype=float)
    if weights is None:
        return q.copy()

    w = np.asarray(weights, dtype=float)
    if w.shape != q.shape:
        raise ValueError(f"weights shape {w.shape} does not match charges shape {q.shape}")
    if np.any(w <= 0.0) or not np.all(np.isfinite(w)):
        raise ValueError("Confidence weights must be strictly positive and finite.")

    return w * q


@dataclass(frozen=True)
class ChargeMomentSummary:
    """Spatial moments and statistics of a discrete charge distribution.

    Attributes:
        net_charge: Sum of signed integer charges Q_net = sum(q_t).
        abs_charge: Sum of absolute charges Q_abs = sum(|q_t|).
        positive_charge_count: Number of positive charges sum(q_t > 0).
        negative_charge_count: Number of negative charges sum(q_t < 0).
        magnitude_centroid: Centroid weighted by |q_t|, or None if Q_abs == 0.
        positive_centroid: Centroid of positive charges, or None if no positive charges.
        negative_centroid: Centroid of negative charges, or None if no negative charges.
        signed_first_moment: First moment sum(q_t * r_t), or None if no coordinates.
        positive_negative_separation: Euclidean distance ||r_+ - r_-||, or None if monopolar/absent.
        is_dipole_separated: True if both positive and negative charges exist.
    """

    net_charge: int
    abs_charge: int
    positive_charge_count: int
    negative_charge_count: int
    magnitude_centroid: np.ndarray | None
    positive_centroid: np.ndarray | None
    negative_centroid: np.ndarray | None
    signed_first_moment: np.ndarray | None
    positive_negative_separation: float | None
    is_dipole_separated: bool


def compute_charge_moments(
    complex_: SimplicialComplex,
    charges: np.ndarray | Sequence[int],
) -> ChargeMomentSummary:
    """Compute spatial moments, centroids, and positive-negative separation for charges.

    Guardrail:
        If positive or negative charges are absent, positive_negative_separation
        returns None. It is NEVER imputed as 0.0, which would falsely imply
        co-located opposite charges.

    Args:
        complex_: Simplicial complex containing coordinates.
        charges: Integer charges on triangles (|T|,).

    Returns:
        ChargeMomentSummary instance.
    """
    q = np.asarray(charges, dtype=int)
    if q.shape != (complex_.num_triangles,):
        raise ValueError(f"charges shape {q.shape} does not match num_triangles {complex_.num_triangles}")

    net_charge = int(np.sum(q))
    abs_charge = int(np.sum(np.abs(q)))

    pos_mask = q > 0
    neg_mask = q < 0
    pos_count = int(np.sum(pos_mask))
    neg_count = int(np.sum(neg_mask))

    if complex_.coordinates is None or complex_.num_triangles == 0:
        return ChargeMomentSummary(
            net_charge=net_charge,
            abs_charge=abs_charge,
            positive_charge_count=pos_count,
            negative_charge_count=neg_count,
            magnitude_centroid=None,
            positive_centroid=None,
            negative_centroid=None,
            signed_first_moment=None,
            positive_negative_separation=None,
            is_dipole_separated=False,
        )

    barycenters = complex_.triangle_barycenters()

    # Signed first moment: m = sum(q_t * r_t)
    signed_first_moment = np.sum(q[:, np.newaxis] * barycenters, axis=0)

    # Magnitude centroid: sum(|q_t| * r_t) / sum(|q_t|)
    if abs_charge > 0:
        magnitude_centroid = np.sum(np.abs(q)[:, np.newaxis] * barycenters, axis=0) / float(abs_charge)
    else:
        magnitude_centroid = None

    # Positive centroid
    if pos_count > 0:
        pos_weights = q[pos_mask]
        pos_bary = barycenters[pos_mask]
        pos_centroid = np.sum(pos_weights[:, np.newaxis] * pos_bary, axis=0) / float(np.sum(pos_weights))
    else:
        pos_centroid = None

    # Negative centroid
    if neg_count > 0:
        neg_weights = np.abs(q[neg_mask])
        neg_bary = barycenters[neg_mask]
        neg_centroid = np.sum(neg_weights[:, np.newaxis] * neg_bary, axis=0) / float(np.sum(neg_weights))
    else:
        neg_centroid = None

    # Positive-negative separation
    if pos_centroid is not None and neg_centroid is not None:
        separation = float(np.linalg.norm(pos_centroid - neg_centroid))
        is_separated = True
    else:
        separation = None
        is_separated = False

    return ChargeMomentSummary(
        net_charge=net_charge,
        abs_charge=abs_charge,
        positive_charge_count=pos_count,
        negative_charge_count=neg_count,
        magnitude_centroid=magnitude_centroid,
        positive_centroid=pos_centroid,
        negative_centroid=neg_centroid,
        signed_first_moment=signed_first_moment,
        positive_negative_separation=separation,
        is_dipole_separated=is_separated,
    )
