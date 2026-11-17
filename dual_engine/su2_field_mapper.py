"""SU(2) order-parameter mapping for the dual-engine topological framework.

Both domains this framework ingests -- cortical phase maps (from Hilbert-transformed
BIDS EEG) and quantum field grids (from HDF5 spinor/gauge configurations) -- are reduced
to a shared representation: a 2D (or stacked 3D) *phase field* theta(x) in (-pi, pi], and
its lift into an SU(2) order-parameter field U(x).

Construction (standard, not novel):
    Given a scalar phase theta and a unit axis n_hat = (nx, ny, nz),
        U = cos(theta) * I  +  i * sin(theta) * (nx*sigma_x + ny*sigma_y + nz*sigma_z)
    which is exactly exp(i * theta * (n_hat . sigma)). This is a genuine element of SU(2):
    U is unitary (U U^dagger = I) and det(U) = 1, verified numerically in the tests.

    For a pure U(1) phase field (the common case for EEG phase and complex scalar BEC
    fields), n_hat = z_hat gives U = diag(e^{i theta}, e^{-i theta}). The downstream
    core.topology routines calculate phase winding on two-dimensional slices; that
    quantity is not the three-dimensional SU(2) Skyrme degree. A smooth fixed-axis
    lift remains in a U(1) subgroup and cannot carry nonzero 3D Skyrme degree.

This module does NOT claim that EEG and quantum fields are physically the same system.
It provides a common mathematical container so the SAME downstream topology/action code
runs on both. Provenance is carried through unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# Pauli matrices (Hermitian, traceless), the su(2) generators up to a factor.
SIGMA_X = np.array([[0, 1], [1, 0]], dtype=complex)
SIGMA_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
SIGMA_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_IDENTITY2 = np.eye(2, dtype=complex)

_VALID_PROVENANCE = {"real_bids", "synthetic_proxy", "quantum_field"}


@dataclass
class SU2Field:
    """An SU(2) order-parameter field with its generating phase field.

    Attributes
    ----------
    theta : np.ndarray
        Real phase field, shape (H, W) or (T, H, W), values in (-pi, pi].
    U : np.ndarray
        SU(2) matrices, shape theta.shape + (2, 2), complex.
    axis : np.ndarray
        Unit rotation axis n_hat used for the lift, shape (3,).
    provenance : str
        One of {"real_bids", "synthetic_proxy", "quantum_field"}.
    meta : dict
        Free-form provenance metadata (subject, task, dataset, dt, etc.).
    """

    theta: np.ndarray
    U: np.ndarray
    axis: np.ndarray
    provenance: str
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.provenance not in _VALID_PROVENANCE:
            raise ValueError(
                f"provenance must be one of {_VALID_PROVENANCE}, got {self.provenance!r}"
            )

    @property
    def complex_scalar(self) -> np.ndarray:
        """The U(1) reduction psi = e^{i theta} (same winding as U for axis=z_hat)."""
        return np.exp(1j * self.theta)


def phase_to_su2(
    theta: np.ndarray,
    axis: Optional[np.ndarray] = None,
    provenance: str = "synthetic_proxy",
    meta: Optional[dict] = None,
) -> SU2Field:
    """Lift a real phase field theta(x) into an SU(2) order-parameter field.

    Parameters
    ----------
    theta : array (H, W) or (T, H, W)
        Real phase field. Not required to be pre-wrapped; it is wrapped to (-pi, pi].
    axis : array (3,), optional
        Rotation axis n_hat; defaults to z_hat = (0, 0, 1), the U(1) embedding.
    provenance : str
        Provenance tag carried onto the result.
    meta : dict, optional
        Extra provenance metadata.

    Returns
    -------
    SU2Field
    """
    theta = np.asarray(theta, dtype=float)
    if theta.ndim not in (2, 3):
        raise ValueError(f"theta must be 2D or 3D, got shape {theta.shape}")

    # wrap to (-pi, pi] for a single-valued lift
    theta_w = (theta + np.pi) % (2 * np.pi) - np.pi

    if axis is None:
        axis = np.array([0.0, 0.0, 1.0])
    axis = np.asarray(axis, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-12:
        raise ValueError("axis must be non-zero")
    axis = axis / norm

    n_dot_sigma = axis[0] * SIGMA_X + axis[1] * SIGMA_Y + axis[2] * SIGMA_Z  # (2,2)

    c = np.cos(theta_w)[..., None, None]  # (..., 1, 1)
    s = np.sin(theta_w)[..., None, None]
    U = c * _IDENTITY2 + 1j * s * n_dot_sigma  # broadcast to (..., 2, 2)

    return SU2Field(
        theta=theta_w,
        U=U.astype(complex),
        axis=axis,
        provenance=provenance,
        meta=dict(meta or {}),
    )


def su2_to_phase(field_obj: SU2Field) -> np.ndarray:
    """Recover the generating phase field from an SU(2) field (inverse of the lift).

    Uses theta = atan2( Im(U_00) * sign, Re(U_00) ) via the z-projected component; for the
    z-axis embedding this is exact. For a general axis the diagonal still encodes cos(theta)
    and the axis-weighted sin(theta), which we invert with the known axis.
    """
    U = field_obj.U
    c = np.real(0.5 * np.trace(U, axis1=-2, axis2=-1))  # cos(theta) = Re(tr U)/2
    # sin(theta) recovered from the (n.sigma) projection: tr(-i (n.sigma) U)/2 = sin(theta)
    axis = field_obj.axis
    n_dot_sigma = axis[0] * SIGMA_X + axis[1] * SIGMA_Y + axis[2] * SIGMA_Z
    proj = np.einsum("ij,...ji->...", -1j * n_dot_sigma, U) * 0.5
    s = np.real(proj)
    return np.arctan2(s, c)


def is_in_su2(U: np.ndarray, tol: float = 1e-9) -> bool:
    """Check that every matrix in U (shape (..., 2, 2)) is unitary with det == 1."""
    U = np.asarray(U)
    if U.shape[-2:] != (2, 2):
        return False
    Udag = np.conjugate(np.swapaxes(U, -1, -2))
    prod = np.einsum("...ij,...jk->...ik", U, Udag)
    eye = np.broadcast_to(_IDENTITY2, prod.shape)
    unitary = np.allclose(prod, eye, atol=tol)
    dets = U[..., 0, 0] * U[..., 1, 1] - U[..., 0, 1] * U[..., 1, 0]
    det_one = np.allclose(dets, 1.0 + 0j, atol=tol)
    return bool(unitary and det_one)


def stack_windows_to_field(phase_windows: list[np.ndarray], provenance: str,
                           meta: Optional[dict] = None) -> SU2Field:
    """Stack a list of 2D phase maps (one per time window) into a (T, H, W) SU(2) field.

    All windows must share the same (H, W). Useful for turning per-window cortical or
    quantum phase maps into a single time-indexed SU(2) field for longitudinal analysis.
    """
    if not phase_windows:
        raise ValueError("phase_windows is empty")
    shapes = {w.shape for w in phase_windows}
    if len(shapes) != 1:
        raise ValueError(f"all windows must share one shape, got {shapes}")
    theta = np.stack([np.asarray(w, dtype=float) for w in phase_windows], axis=0)
    return phase_to_su2(theta, provenance=provenance, meta=meta)

