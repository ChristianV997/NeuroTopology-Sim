"""Independent specification oracle for Round 6 winding / charge-moment claims.

Does not import ``experimental.phase_cochain_reference`` or any candidate engine.
Synthetic numerics only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from tools.experimental_audits.winding_charge_round6.conventions import (
    BRANCH_AT_PLUS_PI,
    WRAP_INTERVAL,
)

TWO_PI = 2.0 * np.pi
_CHARGE_VALIDATION_ERROR = "charges must be finite integer-valued int64 values"


def wrap_principal(phase: np.ndarray | float) -> np.ndarray | float:
    """Wrap to ``[-π, π)`` with exact ``+π → −π``.

    Convention (explicit):
    - ``WRAP_INTERVAL = [-pi, pi)``
    - ``BRANCH_AT_PLUS_PI = maps_to_minus_pi``
    - ``−π`` stays ``−π``
    """
    arr = np.asarray(phase, dtype=float)
    wrapped = np.mod(arr + np.pi, TWO_PI) - np.pi
    # Guard float edge where mod lands on +π
    wrapped = np.where(np.isclose(wrapped, np.pi, atol=0.0, rtol=0.0), -np.pi, wrapped)
    wrapped = np.where(wrapped >= np.pi, wrapped - TWO_PI, wrapped)
    if np.isscalar(phase):
        return float(np.asarray(wrapped).reshape(()))
    return wrapped


def branch_index_and_wrapped(delta: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(n, ω)`` with ``Δ = ω + 2π n``, ``ω ∈ [-π, π)``, ``n ∈ ℤ``.

    Recovers ``n`` from the wrap rather than ``rint(Δ/2π)`` alone, so exact
    ``±π`` differences are unambiguous under the stated branch convention.
    """
    delta_arr = np.asarray(delta, dtype=float)
    if not np.all(np.isfinite(delta_arr)):
        raise ValueError("nonfinite phase difference")
    omega = np.asarray(wrap_principal(delta_arr), dtype=float)
    n = np.rint((delta_arr - omega) / TWO_PI).astype(np.int64)
    return n, omega


@dataclass(frozen=True)
class IndependentComplex:
    """Minimal oriented 2-complex used only by this independent oracle."""

    num_vertices: int
    edges: tuple[tuple[int, int], ...]
    triangles: tuple[tuple[int, int, int], ...]
    coordinates: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.num_vertices < 0:
            raise ValueError("num_vertices must be non-negative")
        for u, v in self.edges:
            if not (0 <= u < self.num_vertices and 0 <= v < self.num_vertices):
                raise ValueError(f"edge {(u, v)} out of range")
            if u >= v:
                raise ValueError(f"edges must be canonically ordered u < v; got {(u, v)}")
        edge_set = set(self.edges)
        for tri in self.triangles:
            if len(tri) != 3:
                raise ValueError(f"triangle must have 3 indices; got {tri}")
            i, j, k = tri
            if not (i < j < k):
                raise ValueError(f"triangles must be canonically ordered i<j<k; got {tri}")
            for e in ((i, j), (j, k), (i, k)):
                if e not in edge_set:
                    raise ValueError(f"triangle {tri} missing edge {e}")
        if self.coordinates is not None:
            coords = np.asarray(self.coordinates, dtype=float)
            if coords.ndim != 2 or coords.shape[0] != self.num_vertices:
                raise ValueError("coordinates must have shape (num_vertices, D)")
            object.__setattr__(self, "coordinates", coords)

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    @property
    def num_triangles(self) -> int:
        return len(self.triangles)

    def d0_matrix(self) -> np.ndarray:
        d0 = np.zeros((self.num_edges, self.num_vertices), dtype=float)
        for e_idx, (u, v) in enumerate(self.edges):
            d0[e_idx, v] = 1.0
            d0[e_idx, u] = -1.0
        return d0

    def d1_matrix(self) -> np.ndarray:
        # (d1 ω)_t = ω_(j,k) − ω_(i,k) + ω_(i,j) for t=(i,j,k)
        edge_index = {e: idx for idx, e in enumerate(self.edges)}
        d1 = np.zeros((self.num_triangles, self.num_edges), dtype=float)
        for t_idx, (i, j, k) in enumerate(self.triangles):
            d1[t_idx, edge_index[(j, k)]] = 1.0
            d1[t_idx, edge_index[(i, k)]] = -1.0
            d1[t_idx, edge_index[(i, j)]] = 1.0
        return d1

    def triangle_barycenters(self) -> np.ndarray:
        if self.coordinates is None:
            raise ValueError("coordinates required for barycenters")
        out = []
        for i, j, k in self.triangles:
            out.append((self.coordinates[i] + self.coordinates[j] + self.coordinates[k]) / 3.0)
        return np.asarray(out, dtype=float)


def triangle_loop_winding(
    vertex_phases: Sequence[float] | np.ndarray,
    triangle: Sequence[int],
) -> int:
    """Integer winding of oriented loop a→b→c→a via principal wrapped diffs."""
    if len(triangle) != 3:
        raise ValueError("triangle must have three indices")
    theta = np.asarray(vertex_phases, dtype=float)
    if not np.all(np.isfinite(theta)):
        raise ValueError("nonfinite phase")
    a, b, c = (int(x) for x in triangle)
    circ = (
        float(wrap_principal(theta[b] - theta[a]))
        + float(wrap_principal(theta[c] - theta[b]))
        + float(wrap_principal(theta[a] - theta[c]))
    )
    return int(np.rint(circ / TWO_PI))


def topological_charges_from_phases(
    complex_: IndependentComplex,
    vertex_phases: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Exact integer charges ``q = −d1 n`` with ``n`` from wrapped edge diffs."""
    theta = np.asarray(vertex_phases, dtype=float)
    if theta.shape != (complex_.num_vertices,):
        raise ValueError(
            f"vertex_phases shape {theta.shape} != ({complex_.num_vertices},)"
        )
    if not np.all(np.isfinite(theta)):
        raise ValueError("nonfinite phase")
    if complex_.num_triangles == 0:
        return np.empty((0,), dtype=np.int64)

    raw = complex_.d0_matrix() @ theta
    n, omega = branch_index_and_wrapped(raw)
    # Consistency: omega must match raw - 2π n
    if np.max(np.abs(raw - (omega + TWO_PI * n))) > 1e-10:
        raise RuntimeError("branch recovery inconsistency")

    q = (-(complex_.d1_matrix() @ n.astype(float))).astype(np.int64)
    circ = complex_.d1_matrix() @ omega
    q_circ = circ / TWO_PI
    if np.max(np.abs(q_circ - q.astype(float))) > 1e-10:
        raise RuntimeError("circulation vs integer charge mismatch")
    return q


def _as_int64_charges(charges: Sequence[int] | np.ndarray) -> np.ndarray:
    """Validate charge inputs before conversion, rejecting lossy NumPy casts."""
    raw = np.asarray(charges)
    if raw.dtype.kind == "i":
        return raw.astype(np.int64, copy=True)
    if raw.dtype.kind == "u":
        if np.any(raw > np.iinfo(np.int64).max):
            raise ValueError(_CHARGE_VALIDATION_ERROR)
        return raw.astype(np.int64, copy=True)
    if raw.dtype.kind == "f":
        if not np.all(np.isfinite(raw)):
            raise ValueError(_CHARGE_VALIDATION_ERROR)
        if not np.all(raw == np.rint(raw)):
            raise ValueError(_CHARGE_VALIDATION_ERROR)
        if np.any(raw < np.iinfo(np.int64).min) or np.any(raw >= 2**63):
            raise ValueError(_CHARGE_VALIDATION_ERROR)
        return raw.astype(np.int64)
    raise ValueError(_CHARGE_VALIDATION_ERROR)


def net_charge(charges: Sequence[int] | np.ndarray) -> int:
    q = _as_int64_charges(charges)
    return sum(int(value) for value in q.flat)


def apply_confidence_weights(
    charges: Sequence[int] | np.ndarray,
    weights: Sequence[float] | np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(scores, integer_charges_copy)``. Weights never mutate ``q``."""
    q = _as_int64_charges(charges)
    if weights is None:
        return q.astype(float), q
    w = np.asarray(weights, dtype=float)
    if w.shape != q.shape:
        raise ValueError("weights shape must match charges")
    if not np.all(np.isfinite(w)) or np.any(w <= 0.0):
        raise ValueError("confidence weights must be finite and strictly positive")
    return w * q.astype(float), q


@dataclass(frozen=True)
class ChargeMomentResult:
    """Signed charge moments with fail-closed missing-sign separation."""

    net_charge: int
    abs_charge: int
    positive_count: int
    negative_count: int
    signed_first_moment: np.ndarray | None
    magnitude_centroid: np.ndarray | None
    positive_centroid: np.ndarray | None
    negative_centroid: np.ndarray | None
    # Explicitly undefined when either sign is absent: NaNs + False.
    charge_separation: float
    charge_separation_defined: bool
    status: str  # "ok" | "undefined_separation" | "no_coordinates" | "empty"


def charge_moments(
    complex_: IndependentComplex,
    charges: Sequence[int] | np.ndarray,
) -> ChargeMomentResult:
    """Compute moments; missing-sign separation is NaN + defined=False (never 0)."""
    q = _as_int64_charges(charges)
    if q.shape != (complex_.num_triangles,):
        raise ValueError("charges length must match triangle count")
    if not np.all(np.isfinite(q.astype(float))):
        raise ValueError("nonfinite charge values")

    q_net = sum(int(value) for value in q.flat)
    q_abs = sum(abs(int(value)) for value in q.flat)
    pos = q > 0
    neg = q < 0
    pos_count = int(np.count_nonzero(pos))
    neg_count = int(np.count_nonzero(neg))

    nan = float("nan")
    if complex_.coordinates is None or complex_.num_triangles == 0:
        return ChargeMomentResult(
            net_charge=q_net,
            abs_charge=q_abs,
            positive_count=pos_count,
            negative_count=neg_count,
            signed_first_moment=None,
            magnitude_centroid=None,
            positive_centroid=None,
            negative_centroid=None,
            charge_separation=nan,
            charge_separation_defined=False,
            status="no_coordinates" if complex_.coordinates is None else "empty",
        )

    bary = complex_.triangle_barycenters()
    if not np.all(np.isfinite(bary)):
        raise ValueError("nonfinite coordinates/barycenters")

    moment = np.sum(q[:, None].astype(float) * bary, axis=0)
    abs_q = np.fromiter(
        (abs(int(value)) for value in q.flat), dtype=float, count=q.size
    ).reshape(q.shape)

    if q_abs > 0:
        mag_centroid = np.sum(abs_q[:, None] * bary, axis=0) / float(q_abs)
    else:
        mag_centroid = None

    if pos_count > 0:
        pos_centroid = np.sum(q[pos][:, None].astype(float) * bary[pos], axis=0) / float(
            sum(int(value) for value in q[pos])
        )
    else:
        pos_centroid = None

    if neg_count > 0:
        neg_centroid = np.sum(
            abs_q[neg][:, None] * bary[neg], axis=0
        ) / float(sum(abs(int(value)) for value in q[neg]))
    else:
        neg_centroid = None

    if pos_centroid is not None and neg_centroid is not None:
        separation = float(np.linalg.norm(pos_centroid - neg_centroid))
        defined = True
        status = "ok"
    else:
        separation = nan
        defined = False
        status = "undefined_separation"

    return ChargeMomentResult(
        net_charge=q_net,
        abs_charge=q_abs,
        positive_count=pos_count,
        negative_count=neg_count,
        signed_first_moment=moment,
        magnitude_centroid=mag_centroid,
        positive_centroid=pos_centroid,
        negative_centroid=neg_centroid,
        charge_separation=separation,
        charge_separation_defined=defined,
        status=status,
    )


def shift_origin(
    complex_: IndependentComplex,
    origin_shift: Sequence[float] | np.ndarray,
) -> IndependentComplex:
    """Return a complex whose coordinates are expressed in origin-shifted frame.

    Origin move by ``a`` ⇒ new coordinates ``r' = r − a``.
    """
    if complex_.coordinates is None:
        raise ValueError("coordinates required")
    a = np.asarray(origin_shift, dtype=float)
    if a.shape != (complex_.coordinates.shape[1],):
        raise ValueError("origin_shift dimension mismatch")
    if not np.all(np.isfinite(a)):
        raise ValueError("nonfinite origin shift")
    return IndependentComplex(
        num_vertices=complex_.num_vertices,
        edges=complex_.edges,
        triangles=complex_.triangles,
        coordinates=complex_.coordinates - a,
    )


def translate_coordinates(
    complex_: IndependentComplex,
    translation: Sequence[float] | np.ndarray,
) -> IndependentComplex:
    """Point translation ``r' = r + v`` (PR #385 §4.3 form)."""
    if complex_.coordinates is None:
        raise ValueError("coordinates required")
    v = np.asarray(translation, dtype=float)
    if v.shape != (complex_.coordinates.shape[1],):
        raise ValueError("translation dimension mismatch")
    if not np.all(np.isfinite(v)):
        raise ValueError("nonfinite translation")
    return IndependentComplex(
        num_vertices=complex_.num_vertices,
        edges=complex_.edges,
        triangles=complex_.triangles,
        coordinates=complex_.coordinates + v,
    )


# Re-export convention markers for importers / docs generators.
__convention_exports__ = {
    "WRAP_INTERVAL": WRAP_INTERVAL,
    "BRANCH_AT_PLUS_PI": BRANCH_AT_PLUS_PI,
}
