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

