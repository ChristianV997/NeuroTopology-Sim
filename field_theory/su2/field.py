"""Static three-dimensional SU(2) fields on explicit Cartesian grids.

The component convention is U = n0 I + i(n1 sigma1+n2 sigma2+n3 sigma3).
Coordinates and spacing are dimensionless unless the caller supplies a length unit.
This representation describes a mathematical field, not measured neural tissue.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def validate_spacing(spacing) -> tuple[float, float, float]:
    """Validate geometric spacing without treating booleans as lengths."""
    raw = np.asarray(spacing, dtype=object)
    if raw.shape != (3,) or any(isinstance(x, (bool, np.bool_)) for x in raw):
        raise ValueError("spacing must contain three positive finite values")
    try:
        values = np.asarray(raw, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("spacing must contain three positive finite values") from exc
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("spacing must contain three positive finite values")
    return tuple(float(x) for x in values)


@dataclass(frozen=True)
class SU2GridField:
    """Unit four-vectors with shape (nx, ny, nz, 4) and spatial metadata."""

    components: np.ndarray
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)
    boundary: str = "fixed_vacuum"
    length_unit: str = "dimensionless"

    def __post_init__(self) -> None:
        n = np.array(self.components, dtype=float, copy=True)
        if n.ndim != 4 or n.shape[-1] != 4 or min(n.shape[:3]) < 2:
            raise ValueError("components must have shape (nx, ny, nz, 4), nx,ny,nz >= 2")
        if not np.isfinite(n).all():
            raise ValueError("components must be finite")
        if not np.allclose(np.sum(n * n, axis=-1), 1.0, rtol=0.0, atol=1e-9):
            raise ValueError("each four-vector must have unit norm")
        spacing = validate_spacing(self.spacing)
        if self.boundary not in {"fixed_vacuum", "periodic"}:
            raise ValueError("unsupported boundary")
        if not isinstance(self.length_unit, str) or not self.length_unit.strip():
            raise ValueError("length_unit must be a nonempty string")
        n.setflags(write=False)
        object.__setattr__(self, "components", n)
        object.__setattr__(self, "spacing", spacing)

    def matrices(self) -> np.ndarray:
        """Convert to complex matrices with shape (nx, ny, nz, 2, 2)."""
        a, b, c, d = np.moveaxis(self.components, -1, 0)
        out = np.empty(self.components.shape[:-1] + (2, 2), dtype=complex)
        out[..., 0, 0] = a + 1j * d
        out[..., 0, 1] = c + 1j * b
        out[..., 1, 0] = -c + 1j * b
        out[..., 1, 1] = a - 1j * d
        return out

