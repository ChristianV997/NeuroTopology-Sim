"""Known field initializers for the exploratory SU(2) model."""
from __future__ import annotations

import numpy as np

from .field import SU2GridField, validate_spacing


def _shape(shape: tuple[int, int, int]) -> tuple[int, int, int]:
    if len(shape) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, np.integer)) or x < 2 for x in shape):
        raise ValueError("shape must contain three integers >= 2")
    return tuple(int(x) for x in shape)


def vacuum(shape: tuple[int, int, int], *, spacing=(1., 1., 1.), boundary="fixed_vacuum", length_unit="dimensionless") -> SU2GridField:
    """Return the identity field."""
    n = np.zeros(_shape(shape) + (4,), dtype=float)
    n[..., 0] = 1.0
    return SU2GridField(n, spacing, boundary, length_unit)


def fixed_axis(theta: np.ndarray, axis=(0., 0., 1.), *, spacing=(1., 1., 1.), boundary="fixed_vacuum", length_unit="dimensionless") -> SU2GridField:
    """Lift a 3D scalar phase into a fixed-axis U(1) subgroup of SU(2)."""
    theta = np.asarray(theta)
    if theta.dtype.kind not in "fiu":
        raise ValueError("theta must be a real numeric array")
    theta = theta.astype(float, copy=False)
    if theta.ndim != 3 or not np.isfinite(theta).all():
        raise ValueError("theta must be a finite 3D array")
    _shape(theta.shape)
    raw_axis = np.asarray(axis, dtype=object)
    if raw_axis.shape != (3,) or any(isinstance(x, (bool, np.bool_)) for x in raw_axis):
        raise ValueError("axis must contain three real numeric values")
    raw_axis = np.asarray(axis)
    if raw_axis.dtype.kind not in "fiu":
        raise ValueError("axis must contain three real numeric values")
    axis = raw_axis.astype(float, copy=False)
    if axis.shape != (3,) or not np.isfinite(axis).all():
        raise ValueError("axis must contain three finite values")
    scale = np.max(np.abs(axis))
    if scale == 0:
        raise ValueError("axis must be nonzero")
    axis = axis / scale
    axis = axis / np.linalg.norm(axis)
    n = np.empty(theta.shape + (4,), dtype=float)
    n[..., 0] = np.cos(theta)
    n[..., 1:] = np.sin(theta)[..., None] * axis
    return SU2GridField(n, spacing, boundary, length_unit)


def hedgehog(shape: tuple[int, int, int], *, radius: float, spacing=(1., 1., 1.), length_unit="dimensionless") -> SU2GridField:
    """Compact C1 profile f(r)=pi(1-r/R)^2 for r<R, zero otherwise.

    Grid coordinates are centered; radius must fit strictly inside every box face.
    This is an initializer, not an energy-minimized Skyrmion.
    """
    shape = _shape(shape)
    spacing_arr = np.asarray(validate_spacing(spacing))
    raw_radius = np.asarray(radius)
    if raw_radius.ndim != 0 or raw_radius.dtype.kind not in "fiu":
        raise ValueError("radius must be a positive finite length")
    radius = float(raw_radius)
    if not np.isfinite(radius) or radius <= 0 or radius >= np.min((np.array(shape) - 1) * spacing_arr / 2):
        raise ValueError("radius must be positive and fit strictly inside the grid")
    coords = [(np.arange(size) - (size - 1) / 2) * dx for size, dx in zip(shape, spacing_arr)]
    xyz = np.stack(np.meshgrid(*coords, indexing="ij"), axis=-1)
    r = np.linalg.norm(xyz, axis=-1)
    f = np.pi * np.maximum(1.0 - r / radius, 0.0) ** 2
    direction = np.zeros_like(xyz)
    np.divide(xyz, r[..., None], out=direction, where=r[..., None] > 0)
    n = np.empty(shape + (4,), dtype=float)
    n[..., 0] = np.cos(f)
    n[..., 1:] = np.sin(f)[..., None] * direction
    return SU2GridField(n, tuple(spacing_arr), "fixed_vacuum", length_unit)


def _su2_product(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Multiply components for U(q)=q0 I+i q·sigma, in left-to-right order."""
    a, v = left[..., 0], left[..., 1:]
    b, w = right[..., 0], right[..., 1:]
    result = np.empty(np.broadcast_shapes(left.shape, right.shape), dtype=np.float64)
    result[..., 0] = a * b - np.sum(v * w, axis=-1)
    # (v·sigma)(w·sigma)=(v·w)I+i(v×w)·sigma; i**2=-1.
    result[..., 1:] = a[..., None] * w + b[..., None] * v - np.cross(v, w)
    return result


def multi_hedgehog(
    shape: tuple[int, int, int],
    *,
    centers,
    radii,
    spacing=(1.0, 1.0, 1.0),
    isorotations=None,
    length_unit="dimensionless",
    allow_overlaps: bool = False,
) -> SU2GridField:
    """Build a deterministic pointwise product of compact hedgehog factors.

    Coordinates and radii use ``spacing`` and ``length_unit``. Each factor is
    ``(cos(F), sin(F) xhat)`` with ``F=pi*max(1-r/R, 0)**2``. Factors are
    multiplied in the input order using this module's convention
    ``U=q0 I+i q·sigma``. Optional ``isorotations`` are unit SU(2) quaternions
    ``(g0,g1,g2,g3)`` in the same convention and conjugate the corresponding
    factor as ``G U G†``. Thus ``G=(cos(theta/2), sin(theta/2)*axis)`` induces
    a Rodrigues rotation by ``-theta`` on the three-vector. Overlapping
    support balls are rejected by default;
    set ``allow_overlaps=True`` to request their well-defined product.

    This is an initial-condition ansatz, not an energy-minimized or stable
    multi-Skyrmion solution and not physical time evolution. Approximate
    lattice charge is not forced to an integer; additivity is only a
    well-separated continuum expectation and must be checked with resolution
    convergence for any particular discretization.
    """
    shape = _shape(shape)
    spacing_values = np.asarray(validate_spacing(spacing), dtype=np.float64)

    raw_center_objects = np.asarray(centers, dtype=object)
    if any(isinstance(value, (bool, np.bool_)) for value in raw_center_objects.flat):
        raise ValueError("centers must not contain boolean values")
    raw_centers = np.asarray(centers)
    if (
        raw_centers.dtype.kind not in "fiu"
        or raw_centers.ndim != 2
        or raw_centers.shape[1:] != (3,)
    ):
        raise ValueError("centers must be a nonempty real numeric array with shape (n, 3)")
    center_values = raw_centers.astype(np.float64, copy=False)
    if center_values.shape[0] == 0 or not np.all(np.isfinite(center_values)):
        raise ValueError("centers must be nonempty and finite")

    raw_radius_objects = np.asarray(radii, dtype=object)
    if any(isinstance(value, (bool, np.bool_)) for value in raw_radius_objects.flat):
        raise ValueError("radii must not contain boolean values")
    raw_radii = np.asarray(radii)
    if (
        raw_radii.dtype.kind not in "fiu"
        or raw_radii.ndim != 1
        or raw_radii.shape[0] != center_values.shape[0]
    ):
        raise ValueError("radii must be a real numeric vector matching the centers")
    radius_values = raw_radii.astype(np.float64, copy=False)
    if not np.all(np.isfinite(radius_values)) or np.any(radius_values <= 0.0):
        raise ValueError("radii must be finite and strictly positive")

    if not isinstance(allow_overlaps, (bool, np.bool_)):
        raise ValueError("allow_overlaps must be boolean")

    if isorotations is None:
        rotations = np.zeros((center_values.shape[0], 4), dtype=np.float64)
        rotations[:, 0] = 1.0
    else:
        raw_rotation_objects = np.asarray(isorotations, dtype=object)
        if any(isinstance(value, (bool, np.bool_)) for value in raw_rotation_objects.flat):
            raise ValueError("isorotations must not contain boolean values")
        raw_rotations = np.asarray(isorotations)
        if (
            raw_rotations.dtype.kind not in "fiu"
            or raw_rotations.shape != (center_values.shape[0], 4)
        ):
            raise ValueError("isorotations must be a real numeric array with shape (n, 4)")
        rotations = raw_rotations.astype(np.float64, copy=True)
        if not np.all(np.isfinite(rotations)):
            raise ValueError("isorotations must be finite")
        rotation_norms = np.linalg.norm(rotations, axis=1)
        if np.any(~np.isfinite(rotation_norms)) or np.any(
            np.abs(rotation_norms - 1.0) > 1.0e-10
        ):
            raise ValueError("each isorotation must have unit norm")
        rotations /= rotation_norms[:, None]

    with np.errstate(over="ignore", invalid="ignore"):
        half_extents = (np.asarray(shape, dtype=np.float64) - 1.0) * spacing_values / 2.0
    if not np.all(np.isfinite(half_extents)):
        raise ValueError("grid extents must be finite")
    available = half_extents[None, :] - np.abs(center_values)
    if np.any(available <= 0.0) or np.any(radius_values[:, None] >= available):
        raise ValueError("each support radius must fit strictly inside every grid face")

    if not allow_overlaps and len(radius_values) > 1:
        for first in range(len(radius_values)):
            for second in range(first + 1, len(radius_values)):
                scale = max(
                    float(radius_values[first]),
                    float(radius_values[second]),
                    float(np.max(np.abs(center_values[first]))),
                    float(np.max(np.abs(center_values[second]))),
                )
                scaled_delta = center_values[first] / scale - center_values[second] / scale
                scaled_distance = np.hypot(
                    np.hypot(scaled_delta[0], scaled_delta[1]), scaled_delta[2]
                )
                scaled_radius_sum = (
                    radius_values[first] / scale + radius_values[second] / scale
                )
                if scaled_distance < scaled_radius_sum:
                    raise ValueError(
                        "hedgehog support balls overlap; pass allow_overlaps=True explicitly"
                    )

    coordinates = [
        (np.arange(size, dtype=np.float64) - (size - 1) / 2.0) * step
        for size, step in zip(shape, spacing_values)
    ]
    xyz = np.stack(np.meshgrid(*coordinates, indexing="ij"), axis=-1)
    if not np.all(np.isfinite(xyz)):
        raise ValueError("grid coordinates must be finite")

    product = np.zeros(shape + (4,), dtype=np.float64)
    product[..., 0] = 1.0
    for center, radius, rotation in zip(center_values, radius_values, rotations):
        with np.errstate(over="ignore", invalid="ignore"):
            relative = xyz - center
        if not np.all(np.isfinite(relative)):
            raise ValueError("grid coordinates and centers produce non-finite offsets")
        distance = np.hypot(np.hypot(relative[..., 0], relative[..., 1]), relative[..., 2])
        profile = np.pi * np.maximum(1.0 - distance / radius, 0.0) ** 2
        direction = np.zeros_like(relative)
        np.divide(relative, distance[..., None], out=direction, where=distance[..., None] > 0.0)
        factor = np.empty(shape + (4,), dtype=np.float64)
        factor[..., 0] = np.cos(profile)
        factor[..., 1:] = np.sin(profile)[..., None] * direction

        conjugate = rotation.copy()
        conjugate[1:] *= -1.0
        factor = _su2_product(_su2_product(rotation, factor), conjugate)
        product = _su2_product(product, factor)

    # Supports were required to fit strictly inside the box; analytically all
    # outer faces are identity. Restore that exact Dirichlet value after the
    # floating-point quaternion conjugations and products.
    for axis in range(3):
        for index in (0, -1):
            selector = [slice(None)] * 3
            selector[axis] = index
            product[tuple(selector)] = (1.0, 0.0, 0.0, 0.0)

    return SU2GridField(product, tuple(spacing_values), "fixed_vacuum", length_unit)

