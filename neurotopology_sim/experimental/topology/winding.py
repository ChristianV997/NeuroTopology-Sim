"""Oriented-complex integer phase-winding (algebraic sensor-space descriptor).

HOLD / SYNTHETIC_ONLY
=====================
This module computes an algebraic integer winding / face-charge descriptor on an
oriented 2-complex from vertex phases and integer incidence matrices. It is
**not** evidence of cortical propagation, biological vortices, consciousness, or
any clinical claim. Gemini Revision 8 and related research notes are unverified
inputs; this code implements only the stated discrete convention.

Orientation convention
----------------------
- ``d0`` maps vertex 0-cochains to oriented edge differences:
  ``(d0 @ theta)_e`` is the raw (unwrapped) phase difference on edge ``e``.
- ``d1`` maps oriented edge 1-cochains to oriented face boundary circulations.
- Integer incidence matrices must satisfy the cochain identity
  ``d1 @ d0 == 0`` exactly (checked before any winding computation).
- Incidence entries must lie in ``{-1, 0, +1}``.

Branch / wrap convention (``wrap_interval="[-pi,pi)"``)
------------------------------------------------------
For each edge raw difference ``raw_e = (d0 @ theta)_e``::

    n_e     = floor((raw_e + π) / (2π))          # integer branch index
    omega_e = raw_e - 2π n_e                     # principal value in [-π, π)

Exact ``+π`` maps to ``-π``; exact ``-π`` stays ``-π``.

Float interval hardening: if the reconstructed ``omega`` falls outside
``[-π, π)`` (ulp neighborhoods of odd multiples of ``π``), ``n`` is shifted
by ``±1`` with ``omega`` and ``n`` recomputed together so
``omega = raw - 2π n`` always holds. Desynchronizing ``n`` from ``omega``
would silently corrupt ``q = -d1 @ n``.

Discrete identity and integer face charge
-----------------------------------------
Because ``d1 @ d0 == 0``::

    d1 @ omega = -2π (d1 @ n)

The integer face charge under this convention is::

    q = - d1 @ n

Sign is verified against explicit CCW / CW phase fixtures in the test suite
(not by naming intuition). For the standard oriented triangle with
``(d1 ω)_t = ω_01 + ω_12 - ω_02`` and CCW phases
``θ = [0, 2π/3, 4π/3]``, ``q = +1``; the CW fixture yields ``q = -1``.

Tie / branch ambiguity
----------------------
Edges whose principal value lies within ``tie_tol`` of either wrap
discontinuity endpoint (``±π`` under the ``[-π, π)`` convention) are flagged in
``tie_edge_mask``. The module does **not** silently resolve branch ambiguity at
those edges.

Amplitude / near-zero phase
---------------------------
Phase behavior near zero amplitude (ill-defined Arg) is **not** resolved here.
Callers must gate or mask low-amplitude sensors upstream.

Moments (optional helpers)
--------------------------
``signed_first_moment`` / ``charge_moments`` take face barycenter coordinates in
**sensor-coordinate units**: whatever Euclidean units the caller uses for the
sensor / electrode embedding (e.g. mm on a scalp montage). These are not
anatomical, biological, or cortical surface coordinates unless the caller
supplies such an embedding. The origin-shift identity is algebraic::

    p_q(a) = p_q(0) - Q_net * a

where ``a`` is the origin displacement (new coords ``r' = r - a``). Charge
separation is undefined (explicit NaN + ``charge_separation_defined=False``)
when either sign class is absent — never substitute 0.0, and never label this
as biological origin invariance.

Scope note
----------
``d1 @ d0 == 0`` is a cochain / incidence identity. It does **not** prove that
the mesh is a valid planar embedding; geometric validity belongs to the
geometry module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

import numpy as np

TWO_PI = 2.0 * np.pi
SUPPORTED_WRAP_INTERVALS = ("[-pi,pi)",)
DEFAULT_TIE_TOL = 1e-12
DEFAULT_IDENTITY_ATOL = 0.0  # exact for integer incidence
# Contract: dense ndarray incidence only (scipy.sparse and duck-types rejected).
SUPPORTS_SPARSE_INCIDENCE = False
# Origin-shift reference: r' = r - a  ⇒  p_q(a) = p_q(0) - Q_net * a
ORIGIN_SHIFT_COORDINATE_MAP = "r_prime = r - a"


ArrayLike = Union[Sequence[float], np.ndarray]


class WindingError(ValueError):
    """Raised when winding inputs fail validation."""


@dataclass(frozen=True)
class WindingResult:
    """Integer phase-winding result on an oriented 2-complex.

    Attributes:
        raw_difference: Unwrapped edge differences ``d0 @ theta`` (float, |E|).
        branch_index: Integer branch indices ``n`` (int64, |E|).
        omega: Principal wrapped edge values in ``[-π, π)`` (float, |E|).
        face_charge: Integer face charges ``q = -d1 @ n`` (int64, |F|).
        tie_edge_mask: True where ``omega`` is within ``tie_tol`` of ±π.
        tie_edge_count: Number of flagged tie edges.
        d1_d0_residual_max_abs: ``max|d1 @ d0|`` (must be 0 for acceptance).
        identity_residual_max_abs: ``max|d1 @ omega + 2π (d1 @ n)|``.
        wrap_interval: Documented wrap interval string.
        tie_tol: Tie tolerance used for flagging.
        net_charge: ``sum(q)`` as Python ``int``.
        abs_charge: ``sum(|q|)`` as Python ``int``.
    """

    raw_difference: np.ndarray
    branch_index: np.ndarray
    omega: np.ndarray
    face_charge: np.ndarray
    tie_edge_mask: np.ndarray
    tie_edge_count: int
    d1_d0_residual_max_abs: float
    identity_residual_max_abs: float
    wrap_interval: str
    tie_tol: float
    net_charge: int
    abs_charge: int


@dataclass(frozen=True)
class ChargeMomentResult:
    """Spatial moments of signed integer face charges.

    Coordinate units are those of ``face_coordinates`` (caller-defined).
    ``charge_separation`` is Euclidean distance between positive and negative
    centroids when both sign classes are present; otherwise undefined.

    This is an algebraic descriptor only — not biological origin invariance.
    """

    net_charge: int
    abs_charge: int
    signed_first_moment: Optional[np.ndarray]
    magnitude_centroid: Optional[np.ndarray]
    positive_centroid: Optional[np.ndarray]
    negative_centroid: Optional[np.ndarray]
    charge_separation: float
    charge_separation_defined: bool
    status: str  # "ok" | "undefined_separation" | "empty"


def _as_1d_float(name: str, values: ArrayLike) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise WindingError(f"{name} must be 1-D; got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise WindingError(f"{name} contains non-finite values")
    return arr


def _reject_sparse_like(name: str, mat: object) -> None:
    """Reject sparse matrices and sparse-like duck types (dense ndarray only)."""
    mod = type(mat).__module__ or ""
    if mod.startswith("scipy.sparse") or mod.startswith("scipy.sparse."):
        raise WindingError(
            f"{name} must be a dense ndarray; sparse incidence is not accepted "
            f"(got {type(mat).__module__}.{type(mat).__name__})"
        )
    # Duck-typed sparse: has CSR/CSC conversion or nnz+format without being ndarray.
    if not isinstance(mat, np.ndarray) and (
        hasattr(mat, "tocsr") or hasattr(mat, "tocsc") or (
            hasattr(mat, "nnz") and hasattr(mat, "format")
        )
    ):
        raise WindingError(
            f"{name} must be a dense ndarray; sparse-like incidence is not accepted "
            f"(got {type(mat).__name__})"
        )


def _as_incidence(name: str, mat: ArrayLike) -> np.ndarray:
    _reject_sparse_like(name, mat)
    arr = np.asarray(mat)
    if arr.dtype == object:
        raise WindingError(f"{name} must be a numeric dense array; got dtype=object")
    if arr.ndim != 2:
        raise WindingError(f"{name} must be 2-D dense; got shape {arr.shape}")
    if arr.size == 0:
        # Allow empty faces (0 x E) or empty edges (0 x V) when dimensions agree.
        return np.asarray(arr, dtype=np.int64)
    if not np.issubdtype(arr.dtype, np.number):
        raise WindingError(f"{name} must be numeric; got dtype={arr.dtype}")
    float_arr = arr.astype(float, copy=False)
    if not np.all(np.isfinite(float_arr)):
        raise WindingError(f"{name} contains non-finite values")
    # Require integer-valued entries in {-1, 0, +1}.
    rounded = np.rint(float_arr)
    if not np.allclose(float_arr, rounded, rtol=0.0, atol=0.0):
        raise WindingError(f"{name} must be integer-valued in {{-1,0,+1}}")
    int_arr = rounded.astype(np.int64)
    unique = set(np.unique(int_arr).tolist())
    if not unique.issubset({-1, 0, 1}):
        raise WindingError(f"{name} entries must lie in {{-1,0,+1}}; got {sorted(unique)}")
    return int_arr


def _validate_wrap_interval(wrap_interval: str) -> None:
    if wrap_interval not in SUPPORTED_WRAP_INTERVALS:
        raise WindingError(
            f"unsupported wrap_interval={wrap_interval!r}; "
            f"supported={SUPPORTED_WRAP_INTERVALS}"
        )


def branch_index_floor(raw: ArrayLike) -> Tuple[np.ndarray, np.ndarray]:
    """Return ``(n, omega)`` with floor wrap into ``[-π, π)``.

    Ideal arithmetic: ``n_e = floor((raw_e + π) / (2π))``,
    ``omega_e = raw_e - 2π n_e``. In float, the floor step can disagree with
    the reconstructed principal value near odd multiples of ``π``. Interval
    hardening therefore shifts ``n`` by ``±1`` whenever ``omega`` is shifted
    by ``±2π``, then recomputes ``omega = raw - 2π n`` so the pair stays
    consistent (required for ``q = -d1 @ n`` to match ``(d1 @ omega) / 2π``).
    Exact ``+π`` still maps to ``−π`` via ``omega >= π`` → ``n += 1``.
    """
    raw_arr = _as_1d_float("raw", raw)
    # floor of float; cast to int64 afterwards (core branch index stays integer).
    n = np.floor((raw_arr + np.pi) / TWO_PI).astype(np.int64)
    omega = raw_arr - TWO_PI * n.astype(float)
    # Harden into [-π, π) while keeping omega = raw - 2π n.
    # Two passes cover residual float overshoot after the first adjust.
    for _ in range(2):
        high = omega >= np.pi
        low = omega < -np.pi
        if not (np.any(high) or np.any(low)):
            break
        n = (n + high.astype(np.int64) - low.astype(np.int64)).astype(np.int64)
        omega = raw_arr - TWO_PI * n.astype(float)
    return n, omega


def _tie_mask(omega: np.ndarray, tie_tol: float) -> np.ndarray:
    """Flag edges within ``tie_tol`` of wrap discontinuities ±π."""
    if tie_tol < 0.0 or not np.isfinite(tie_tol):
        raise WindingError("tie_tol must be a finite non-negative float")
    # Under [-π, π), the cut is at −π (and +π is identified with −π).
    dist_minus = np.abs(omega - (-np.pi))
    dist_plus = np.abs(omega - np.pi)
    return (dist_minus <= tie_tol) | (dist_plus <= tie_tol)


def phase_winding(
    vertex_phase: ArrayLike,
    d0: ArrayLike,
    d1: ArrayLike,
    *,
    wrap_interval: str = "[-pi,pi)",
    tie_tol: float = DEFAULT_TIE_TOL,
) -> WindingResult:
    """Compute oriented integer phase winding / face charges.

    Args:
        vertex_phase: Vertex phases θ in radians, shape ``(|V|,)``. Finite.
        d0: Integer incidence ``|E| × |V|`` with entries in ``{-1,0,+1}``.
        d1: Integer incidence ``|F| × |E|`` with entries in ``{-1,0,+1}``.
        wrap_interval: Must be ``"[-pi,pi)"`` (only supported interval).
        tie_tol: Non-negative tolerance for flagging near-cut edges.

    Returns:
        :class:`WindingResult` with integer ``branch_index`` / ``face_charge``.

    Raises:
        WindingError: On malformed shapes, non-finite phases, invalid incidence,
            dimension mismatch, or failed ``d1 @ d0 == 0`` identity.
    """
    _validate_wrap_interval(wrap_interval)
    if tie_tol < 0.0 or not np.isfinite(tie_tol):
        raise WindingError("tie_tol must be a finite non-negative float")

    theta = _as_1d_float("vertex_phase", vertex_phase)
    d0_i = _as_incidence("d0", d0)
    d1_i = _as_incidence("d1", d1)

    n_edges, n_verts = d0_i.shape
    n_faces, n_edges_d1 = d1_i.shape
    if n_edges_d1 != n_edges:
        raise WindingError(
            f"inconsistent edge dimension: d0 has {n_edges} edges, d1 has {n_edges_d1}"
        )
    if theta.shape[0] != n_verts:
        raise WindingError(
            f"vertex_phase length {theta.shape[0]} != d0 num_vertices {n_verts}"
        )

    # Exact cochain identity on integer incidence.
    product = d1_i @ d0_i
    residual_d1d0 = float(np.max(np.abs(product))) if product.size else 0.0
    if residual_d1d0 != 0.0:
        raise WindingError(
            f"incidence identity d1 @ d0 == 0 failed; max|d1@d0|={residual_d1d0}"
        )

    raw = d0_i.astype(float) @ theta
    n, omega = branch_index_floor(raw)

    # Integer face charge: keep integer arithmetic for the core path.
    if n_faces == 0:
        q = np.empty((0,), dtype=np.int64)
        identity_residual = 0.0
    else:
        d1_n = d1_i @ n  # int64 @ int64 → int64
        q = -d1_n
        # Residual of the continuous identity d1@omega + 2π (d1@n) ≈ 0.
        circ = d1_i.astype(float) @ omega
        identity_residual = float(np.max(np.abs(circ + TWO_PI * d1_n.astype(float))))

    ties = _tie_mask(omega, tie_tol)
    q_net = int(np.sum(q)) if q.size else 0
    q_abs = int(np.sum(np.abs(q))) if q.size else 0

    return WindingResult(
        raw_difference=np.asarray(raw, dtype=float),
        branch_index=np.asarray(n, dtype=np.int64),
        omega=np.asarray(omega, dtype=float),
        face_charge=np.asarray(q, dtype=np.int64),
        tie_edge_mask=np.asarray(ties, dtype=bool),
        tie_edge_count=int(np.sum(ties)),
        d1_d0_residual_max_abs=residual_d1d0,
        identity_residual_max_abs=identity_residual,
        wrap_interval=wrap_interval,
        tie_tol=float(tie_tol),
        net_charge=q_net,
        abs_charge=q_abs,
    )


def signed_first_moment(
    face_charge: ArrayLike,
    face_coordinates: ArrayLike,
) -> np.ndarray:
    """Signed first moment ``p_q = sum_t q_t * r_t``.

    ``face_coordinates`` has shape ``(|F|, D)`` in sensor-coordinate units
    (caller-defined Euclidean embedding units for face barycenters).
    """
    q = np.asarray(face_charge)
    if q.ndim != 1:
        raise WindingError(f"face_charge must be 1-D; got {q.shape}")
    if q.dtype.kind not in "iu":
        # Allow float that are exact integers, but core path prefers int.
        q_f = np.asarray(q, dtype=float)
        if not np.allclose(q_f, np.rint(q_f), rtol=0.0, atol=0.0):
            raise WindingError("face_charge must be integer-valued")
        q = np.rint(q_f).astype(np.int64)
    else:
        q = q.astype(np.int64, copy=False)

    coords = np.asarray(face_coordinates, dtype=float)
    if coords.ndim != 2 or coords.shape[0] != q.shape[0]:
        raise WindingError(
            f"face_coordinates shape {coords.shape} incompatible with "
            f"face_charge length {q.shape[0]}"
        )
    if not np.all(np.isfinite(coords)):
        raise WindingError("face_coordinates contains non-finite values")
    return np.sum(q.astype(float)[:, None] * coords, axis=0)


def origin_shifted_moment(
    moment_at_origin: ArrayLike,
    net_charge: int,
    origin_shift: ArrayLike,
) -> np.ndarray:
    """Algebraic origin-shift: ``p_q(a) = p_q(0) - Q_net * a``.

    ``origin_shift`` ``a`` uses the same coordinate units as the moment.
    Equivalently, new coordinates are ``r' = r - a``.
    """
    p0 = _as_1d_float("moment_at_origin", moment_at_origin)
    a = _as_1d_float("origin_shift", origin_shift)
    if p0.shape != a.shape:
        raise WindingError("moment_at_origin and origin_shift dimension mismatch")
    return p0 - float(net_charge) * a


def charge_moments(
    face_charge: ArrayLike,
    face_coordinates: ArrayLike,
) -> ChargeMomentResult:
    """Moments and charge separation; missing-sign ⇒ undefined (not 0.0).

    ``face_coordinates`` are in sensor-coordinate units (caller Euclidean
    embedding). Separation is ``||r_+ - r_-||`` when both positive and negative
    charges exist. Otherwise ``charge_separation_defined=False`` and separation
    is NaN — never substitute 0.0.
    """
    q = np.asarray(face_charge)
    if q.ndim != 1:
        raise WindingError(f"face_charge must be 1-D; got {q.shape}")
    if q.dtype.kind not in "iu":
        q_f = np.asarray(q, dtype=float)
        if not np.allclose(q_f, np.rint(q_f), rtol=0.0, atol=0.0):
            raise WindingError("face_charge must be integer-valued")
        q = np.rint(q_f).astype(np.int64)
    else:
        q = q.astype(np.int64, copy=False)

    coords = np.asarray(face_coordinates, dtype=float)
    if coords.ndim != 2 or coords.shape[0] != q.shape[0]:
        raise WindingError(
            f"face_coordinates shape {coords.shape} incompatible with "
            f"face_charge length {q.shape[0]}"
        )
    if not np.all(np.isfinite(coords)):
        raise WindingError("face_coordinates contains non-finite values")

    q_net = int(np.sum(q))
    q_abs = int(np.sum(np.abs(q)))
    nan = float("nan")

    if q.shape[0] == 0:
        return ChargeMomentResult(
            net_charge=0,
            abs_charge=0,
            signed_first_moment=None,
            magnitude_centroid=None,
            positive_centroid=None,
            negative_centroid=None,
            charge_separation=nan,
            charge_separation_defined=False,
            status="empty",
        )

    moment = np.sum(q.astype(float)[:, None] * coords, axis=0)
    pos = q > 0
    neg = q < 0
    pos_count = int(np.sum(pos))
    neg_count = int(np.sum(neg))

    if q_abs > 0:
        mag_centroid = np.sum(np.abs(q).astype(float)[:, None] * coords, axis=0) / float(q_abs)
    else:
        mag_centroid = None

    if pos_count > 0:
        pos_centroid = np.sum(q[pos].astype(float)[:, None] * coords[pos], axis=0) / float(
            np.sum(q[pos])
        )
    else:
        pos_centroid = None

    if neg_count > 0:
        neg_centroid = np.sum(
            np.abs(q[neg]).astype(float)[:, None] * coords[neg], axis=0
        ) / float(np.sum(np.abs(q[neg])))
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
        signed_first_moment=moment,
        magnitude_centroid=mag_centroid,
        positive_centroid=pos_centroid,
        negative_centroid=neg_centroid,
        charge_separation=separation,
        charge_separation_defined=defined,
        status=status,
    )


__all__ = [
    "TWO_PI",
    "SUPPORTED_WRAP_INTERVALS",
    "DEFAULT_TIE_TOL",
    "SUPPORTS_SPARSE_INCIDENCE",
    "ORIGIN_SHIFT_COORDINATE_MAP",
    "WindingError",
    "WindingResult",
    "ChargeMomentResult",
    "branch_index_floor",
    "phase_winding",
    "signed_first_moment",
    "origin_shifted_moment",
    "charge_moments",
]
