"""Finite-difference diagnostics for a static SU(2) Skyrme field.

The field is represented as ``n=(n0,n1,n2,n3)`` with ``|n|=1`` and
``U = n0 I + i n_a sigma_a``.  This module evaluates the static energy

    E = integral d^3x [ F_pi^2/8 sum_i |d_i n|^2
                       + 1/(2 e^2) sum_{i<j} sum_{a<b}
                         (d_i n_a d_j n_b - d_i n_b d_j n_a)^2 ].

This is the standard two-term SU(2) Skyrme energy in an explicit current
normalization: if ``L_i = U^dagger d_i U = i sigma . ell_i``, then
``ell_i . ell_j = d_i n . d_j n`` and
``-Tr([L_i,L_j]^2) = 8 sum_{a<b}(...)^2``.  Equivalently, the quartic
term is ``-1/(32 e^2) sum_{i,j} Tr([L_i,L_j]^2)``.  In natural units
(``hbar=c=1``),
``n`` is dimensionless, ``F_pi`` has units length^-1, ``e`` is dimensionless,
and the integrated energy has units length^-1.  With dimensionless lattice
coordinates and default ``F_pi=e=1``, outputs are dimensionless lattice
quantities, not calibrated physical energies.

The degree convention is

    B = 1/(2 pi^2) integral epsilon_abcd n_a
        d_x n_b d_y n_c d_z n_d d^3x.

The target S^3 orientation is ``(n0,n1,n2,n3)`` and the spatial orientation
is ``(x,y,z)``.  Thus the sample hedgehog ``(cos(F), sin(F) x_hat)`` with
``F(0)=pi`` and ``F(boundary)=0`` has degree -1.  Reversing one target
orientation or one spatial coordinate reverses the reported sign.

``periodic`` uses periodic centered differences and a half-open cell grid.
``fixed_vacuum`` requires every boundary face to equal the supplied unit
vacuum; it uses vacuum ghost values, a node grid including the boundary, and
tensor-product trapezoidal quadrature.  Neither discretization enforces an
integer charge at finite resolution.  The returned charge is a convergence
diagnostic, not a proof of a continuum topological sector.

Centered finite differences are projected onto the tangent space of S^3 at
each grid node. This removes discrete radial components and preserves the
declared equivalence between the four-vector and SU(2) trace energies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np

Boundary = Literal["periodic", "fixed_vacuum"]
_UNIT_TOLERANCE = 1.0e-8
_BOUNDARY_TOLERANCE = 1.0e-8


@dataclass(frozen=True)
class SkyrmeDiagnostics:
    """Computed energies and approximate degree, with input conventions."""

    energy_sigma: float
    energy_skyrme: float
    energy_total: float
    topological_charge: float
    spacing: tuple[float, float, float]
    boundary: Boundary
    f_pi: float
    e: float


def _real_float_scalar(value: object, name: str, *, allow_zero: bool) -> float:
    """Validate a real scalar without accepting booleans or coercive strings."""
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric scalar")
    result = float(raw)
    if not np.isfinite(result) or (result < 0 if allow_zero else result <= 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _validate_spacing(spacing: float | Sequence[float]) -> tuple[float, float, float]:
    raw = np.asarray(spacing)
    if raw.dtype.kind not in "fiu":
        raise ValueError("spacing must contain real numeric values")
    if raw.ndim == 0:
        values = np.repeat(raw.astype(np.float64), 3)
    elif raw.shape == (3,):
        values = raw.astype(np.float64)
    else:
        raise ValueError("spacing must be a positive scalar or three-vector")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("spacing must be finite and strictly positive")
    return tuple(float(x) for x in values)


def _validate_vacuum(vacuum: Sequence[float]) -> np.ndarray:
    raw = np.asarray(vacuum)
    if raw.shape != (4,) or raw.dtype.kind not in "fiu":
        raise ValueError("vacuum must be a real four-vector")
    result = raw.astype(np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError("vacuum must be finite")
    if abs(float(np.linalg.norm(result)) - 1.0) > _UNIT_TOLERANCE:
        raise ValueError("vacuum must have unit norm")
    return result


def _validate_field(field: np.ndarray) -> np.ndarray:
    raw = np.asarray(field)
    if raw.dtype.kind not in "fiu":
        raise ValueError("field must be a real numeric array; booleans are not fields")
    values = raw.astype(np.float64, copy=False)
    if values.ndim != 4 or values.shape[-1] != 4:
        raise ValueError("field shape must be (nx, ny, nz, 4)")
    if any(size < 3 for size in values.shape[:3]):
        raise ValueError("each spatial dimension must contain at least three nodes")
    if not np.all(np.isfinite(values)):
        raise ValueError("field must contain only finite values")
    norms = np.linalg.norm(values, axis=-1)
    if np.any(np.abs(norms - 1.0) > _UNIT_TOLERANCE):
        raise ValueError("field must already lie on the unit three-sphere")
    return values


def _derivative(
    field: np.ndarray,
    axis: int,
    step: float,
    boundary: Boundary,
    vacuum: np.ndarray,
) -> np.ndarray:
    if boundary == "periodic":
        return (np.roll(field, -1, axis=axis) - np.roll(field, 1, axis=axis)) / (2.0 * step)

    pad_width = [(0, 0)] * field.ndim
    pad_width[axis] = (1, 1)
    padded = np.pad(field, pad_width, mode="constant")
    face = [slice(None)] * field.ndim
    face[axis] = 0
    padded[tuple(face)] = vacuum
    face[axis] = -1
    padded[tuple(face)] = vacuum
    size = field.shape[axis]
    forward = np.take(padded, np.arange(2, size + 2), axis=axis)
    backward = np.take(padded, np.arange(0, size), axis=axis)
    return (forward - backward) / (2.0 * step)


def _quadrature_weights(shape: tuple[int, int, int], boundary: Boundary) -> np.ndarray:
    axes = []
    for size in shape:
        weights = np.ones(size, dtype=np.float64)
        if boundary == "fixed_vacuum":
            weights[[0, -1]] = 0.5
        axes.append(weights)
    return axes[0][:, None, None] * axes[1][None, :, None] * axes[2][None, None, :]


def _assert_fixed_vacuum_boundary(field: np.ndarray, vacuum: np.ndarray) -> None:
    for axis in range(3):
        for index in (0, -1):
            face = np.take(field, index, axis=axis)
            if np.any(np.abs(face - vacuum) > _BOUNDARY_TOLERANCE):
                raise ValueError("fixed_vacuum boundary requires every outer face to equal vacuum")


def compute_skyrme_diagnostics(
    field: np.ndarray,
    spacing: float | Sequence[float],
    *,
    boundary: Boundary,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
) -> SkyrmeDiagnostics:
    """Return finite-difference static energy and approximate degree.

    Parameters
    ----------
    field:
        Real NumPy-compatible array ordered ``(nx, ny, nz, n0..n3)``.
        Values are validated but never renormalized or otherwise modified.
    spacing:
        Positive physical/lattice spacing, as a scalar or ``(hx,hy,hz)``.
    boundary:
        Explicitly ``"periodic"`` or ``"fixed_vacuum"``.  No implicit
        boundary condition is selected.
    f_pi, e:
        Coefficients in the energy convention in the module docstring.
    ``f_pi`` and ``e`` are finite and strictly positive.
    vacuum:
        Unit four-vector required on every outer face for ``fixed_vacuum``.

    Raises
    ------
    ValueError
        For malformed geometry, unsupported boundary, non-finite/non-unit
        fields, or an incompatible fixed-vacuum boundary.
    FloatingPointError
        If the requested discretization overflows or produces non-finite
        diagnostics.
    """
    if not isinstance(boundary, str) or boundary not in ("periodic", "fixed_vacuum"):
        raise ValueError("boundary must be 'periodic' or 'fixed_vacuum'")
    values = _validate_field(field)
    h = _validate_spacing(spacing)
    f_value = _real_float_scalar(f_pi, "f_pi", allow_zero=False)
    e_value = _real_float_scalar(e, "e", allow_zero=False)
    vacuum_value = _validate_vacuum(vacuum)
    if boundary == "fixed_vacuum":
        _assert_fixed_vacuum_boundary(values, vacuum_value)

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            raw_derivatives = tuple(
                _derivative(values, axis, h[axis], boundary, vacuum_value)
                for axis in range(3)
            )
            derivatives = tuple(
                derivative - values * np.sum(values * derivative, axis=-1, keepdims=True)
                for derivative in raw_derivatives
            )
            weights = _quadrature_weights(values.shape[:3], boundary)
            volume_element = h[0] * h[1] * h[2]
            if not np.isfinite(volume_element) or volume_element <= 0.0:
                raise FloatingPointError

            sigma_density = (f_value * f_value / 8.0) * sum(
                np.sum(derivative * derivative, axis=-1) for derivative in derivatives
            )

            quartic_density = np.zeros(values.shape[:3], dtype=np.float64)
            for i in range(3):
                for j in range(i + 1, 3):
                    wedge_squared = np.zeros(values.shape[:3], dtype=np.float64)
                    for a in range(4):
                        for b in range(a + 1, 4):
                            minor = (
                                derivatives[i][..., a] * derivatives[j][..., b]
                                - derivatives[i][..., b] * derivatives[j][..., a]
                            )
                            wedge_squared += minor * minor
                    quartic_density += wedge_squared / (2.0 * e_value * e_value)

            jacobian_columns = np.stack((values, *derivatives), axis=-1)
            degree_density = np.linalg.det(jacobian_columns) / (2.0 * np.pi**2)
            energy_sigma = float(np.sum(sigma_density * weights) * volume_element)
            energy_skyrme = float(np.sum(quartic_density * weights) * volume_element)
            topological_charge = float(np.sum(degree_density * weights) * volume_element)
    except FloatingPointError:
        raise FloatingPointError(
            "non-finite Skyrme diagnostic; reduce scales or refine safely"
        ) from None

    energy_total = energy_sigma + energy_skyrme
    output = np.asarray((energy_sigma, energy_skyrme, energy_total, topological_charge))
    if not np.all(np.isfinite(output)):
        raise FloatingPointError("non-finite Skyrme diagnostic; reduce scales or refine safely")
    if energy_sigma < 0.0 or energy_skyrme < 0.0:
        raise FloatingPointError("positive energy invariant violated by numerical evaluation")

    return SkyrmeDiagnostics(
        energy_sigma=energy_sigma,
        energy_skyrme=energy_skyrme,
        energy_total=energy_total,
        topological_charge=topological_charge,
        spacing=h,
        boundary=boundary,
        f_pi=f_value,
        e=e_value,
    )


