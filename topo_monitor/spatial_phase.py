"""Coordinate-aware spatial phase topology.

Spatial winding is a geometric quantity. This module therefore never creates
coordinates from channel order and never aliases graph beta-1 to spatial
charge. Missing coordinates return a structured ``INCONCLUSIVE`` result from
the public wrapper; legacy valid calls still return a numeric winding charge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.spatial import Delaunay


@dataclass(frozen=True)
class SpatialPhaseResult:
    status: str
    metric_name: str
    winding_q: float | None
    coordinate_frame: str | None
    interpolation_method: str
    amplitude_mask: np.ndarray | None
    valid_cell_count: int
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "metric_name": self.metric_name,
            "winding_q": self.winding_q,
            "coordinate_frame": self.coordinate_frame,
            "interpolation_method": self.interpolation_method,
            "amplitude_mask": None if self.amplitude_mask is None else self.amplitude_mask.tolist(),
            "valid_cell_count": self.valid_cell_count,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _inconclusive(message: str, *, interpolation_method: str) -> SpatialPhaseResult:
    return SpatialPhaseResult(
        status="INCONCLUSIVE",
        metric_name="spatial_winding_q",
        winding_q=None,
        coordinate_frame=None,
        interpolation_method=interpolation_method,
        amplitude_mask=None,
        valid_cell_count=0,
        errors=(message,),
    )


def analyze_spatial_phase(
    phases: np.ndarray,
    coordinates: np.ndarray | None,
    *,
    amplitude: np.ndarray | None = None,
    amplitude_threshold: float | None = None,
    coordinate_frame: str = "unknown",
    interpolation_method: str = "plaquette_grid",
) -> SpatialPhaseResult:
    """Return a structured spatial winding result with explicit geometry.

    ``coordinates`` is mandatory for an interpretable result. ``amplitude``
    can mask low-amplitude cells; the mask is returned rather than silently
    dropping provenance about where the winding was measured.
    """
    if coordinates is None:
        return _inconclusive("real coordinates are required; geometry was not fabricated", interpolation_method=interpolation_method)
    try:
        if np.iscomplexobj(phases) or np.iscomplexobj(coordinates) or np.iscomplexobj(amplitude):
            return _inconclusive("phases, coordinates, and amplitude must be real", interpolation_method=interpolation_method)
        theta = np.asarray(phases, float)
        coords = np.asarray(coordinates, float)
    except (TypeError, ValueError):
        return _inconclusive("phases and coordinates must be real numeric arrays", interpolation_method=interpolation_method)
    if theta.ndim != 2 or coords.shape != theta.shape + (2,):
        return _inconclusive("phases must be (H,W) and coordinates must be (H,W,2)", interpolation_method=interpolation_method)
    if not np.all(np.isfinite(theta)) or not np.all(np.isfinite(coords)):
        return _inconclusive("phases and coordinates must be finite", interpolation_method=interpolation_method)
    if not coordinate_frame or coordinate_frame == "unknown":
        coordinate_frame_value = "unspecified"
    else:
        coordinate_frame_value = str(coordinate_frame)
    if not interpolation_method:
        return _inconclusive("interpolation_method must be declared", interpolation_method="unspecified")

    amplitude_mask: np.ndarray | None = None
    if amplitude is not None:
        try:
            amp = np.asarray(amplitude, float)
        except (TypeError, ValueError):
            return _inconclusive("amplitude mask input must be real numeric data", interpolation_method=interpolation_method)
        if amp.shape != theta.shape or not np.all(np.isfinite(amp)):
            return _inconclusive("amplitude must match phases and be finite", interpolation_method=interpolation_method)
        threshold = 0.0 if amplitude_threshold is None else float(amplitude_threshold)
        if not np.isfinite(threshold):
            return _inconclusive("amplitude_threshold must be finite", interpolation_method=interpolation_method)
        amplitude_mask = amp >= threshold

    # A real coordinate frame is not just a shape annotation: reject cells
    # with zero geometric area so winding is not inferred from collapsed axes.
    corners = np.stack(
        (coords[:-1, :-1], coords[1:, :-1], coords[1:, 1:], coords[:-1, 1:]),
        axis=0,
    )
    cross2 = lambda left, right: left[..., 0] * right[..., 1] - left[..., 1] * right[..., 0]
    cell_area = 0.5 * np.abs(
        cross2(corners[1] - corners[0], corners[3] - corners[0])
        + cross2(corners[2] - corners[1], corners[3] - corners[1])
    )
    valid_cells = cell_area > np.finfo(float).eps
    if amplitude_mask is not None:
        valid_cells &= (
            amplitude_mask[:-1, :-1]
            & amplitude_mask[1:, :-1]
            & amplitude_mask[1:, 1:]
            & amplitude_mask[:-1, 1:]
        )
    if not np.any(valid_cells):
        return SpatialPhaseResult(
            status="INCONCLUSIVE",
            metric_name="spatial_winding_q",
            winding_q=None,
            coordinate_frame=coordinate_frame_value,
            interpolation_method=interpolation_method,
            amplitude_mask=amplitude_mask,
            valid_cell_count=0,
            errors=("no non-degenerate, amplitude-valid cells remain",),
        )

    wrap = lambda value: (value + np.pi) % (2 * np.pi) - np.pi
    local = (
        wrap(theta[1:, :-1] - theta[:-1, :-1])
        + wrap(theta[1:, 1:] - theta[1:, :-1])
        + wrap(theta[:-1, 1:] - theta[1:, 1:])
        + wrap(theta[:-1, :-1] - theta[:-1, 1:])
    ) / (2 * np.pi)
    charge = float(np.sum(local[valid_cells]))
    return SpatialPhaseResult(
        status="VALID",
        metric_name="spatial_winding_q",
        winding_q=float(np.rint(charge)),
        coordinate_frame=coordinate_frame_value,
        interpolation_method=interpolation_method,
        amplitude_mask=amplitude_mask,
        valid_cell_count=int(np.count_nonzero(valid_cells)),
    )


def spatial_winding_charge(
    phases: np.ndarray,
    coordinates: np.ndarray | None = None,
    *,
    amplitude: np.ndarray | None = None,
    amplitude_threshold: float | None = None,
    coordinate_frame: str = "unknown",
    interpolation_method: str = "plaquette_grid",
    return_details: bool = False,
) -> float | SpatialPhaseResult | dict[str, Any]:
    """Return spatial winding while preserving the legacy numeric API.

    Valid legacy calls return ``float``. Callers can request metadata with
    ``return_details=True``. When coordinates are missing, a structured
    ``INCONCLUSIVE`` mapping is returned even without ``return_details`` so
    missing geometry cannot be mistaken for a zero charge.
    """
    result = analyze_spatial_phase(
        phases,
        coordinates,
        amplitude=amplitude,
        amplitude_threshold=amplitude_threshold,
        coordinate_frame=coordinate_frame,
        interpolation_method=interpolation_method,
    )
    if return_details:
        return result
    if result.status == "VALID":
        return float(result.winding_q)
    if coordinates is None:
        return result.to_dict()
    raise ValueError("spatial phase is uninterpretable: " + "; ".join(result.errors))


def analytic_vortex_fixture(
    shape: tuple[int, int] = (65, 65),
    *,
    charge: int = 1,
    center: tuple[float, float] = (0.0, 0.0),
    coordinate_frame: str = "fixture_cartesian_xy",
) -> dict[str, Any]:
    """Create a labelled analytic vortex fixture for method validation only."""
    if len(shape) != 2 or min(shape) < 3 or int(charge) == 0:
        raise ValueError("shape must be 2D with at least 3 points per axis and non-zero charge")
    # Half-cell offset avoids placing the analytic singularity exactly on a
    # grid vertex, where a plaquette winding is not uniquely assigned.
    y_values = (np.arange(shape[0], dtype=float) - shape[0] / 2.0) * (2.0 / shape[0])
    x_values = (np.arange(shape[1], dtype=float) - shape[1] / 2.0) * (2.0 / shape[1])
    y, x = np.meshgrid(y_values, x_values, indexing="ij")
    cx, cy = map(float, center)
    phases = np.arctan2(y - cy, x - cx) * int(charge)
    amplitude = np.hypot(x - cx, y - cy)
    return {
        "phases": phases,
        "coordinates": np.stack((x, y), axis=-1),
        "amplitude": amplitude,
        "coordinate_frame": coordinate_frame,
        "source_kind": "analytic_fixture",
        "provenance_status": "fixture",
    }


def complex_phase_grid(real: np.ndarray, imag: np.ndarray) -> np.ndarray:
    """Return finite phase from complex field components without angle interpolation."""
    a, b = np.asarray(real, float), np.asarray(imag, float)
    if a.shape != b.shape or a.ndim != 2 or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("real/imag must be finite same-shaped 2D arrays")
    return np.angle(a + 1j * b)


def sensor_spatial_charge(
    phases: np.ndarray,
    coordinates: np.ndarray,
    *,
    coordinate_frame: str = "unknown",
) -> float:
    """Estimate spatial charge on real 3D sensor coordinates via Delaunay."""
    theta = np.asarray(phases, float)
    xyz = np.asarray(coordinates, float)
    if theta.ndim != 1 or xyz.ndim != 2 or xyz.shape != (theta.size, 3):
        raise ValueError("phases must be (N,) and coordinates must be (N,3)")
    if not coordinate_frame:
        raise ValueError("coordinate_frame must be declared")
    valid = np.isfinite(theta) & np.all(np.isfinite(xyz), axis=1)
    if np.count_nonzero(valid) < 3:
        raise ValueError("at least three finite montage sensors are required")
    points = xyz[valid]
    centered = points - points.mean(axis=0)
    _, singular_values, vh = np.linalg.svd(centered, full_matrices=False)
    if singular_values.size < 2 or singular_values[1] <= np.finfo(float).eps:
        raise ValueError("sensor coordinates are geometrically degenerate")
    planar = centered @ vh[:2].T
    simplices = Delaunay(planar).simplices
    phase = theta[valid]
    wrap = lambda value: (value + np.pi) % (2 * np.pi) - np.pi
    total = 0.0
    for tri in simplices:
        values = phase[tri]
        total += (wrap(values[1] - values[0]) + wrap(values[2] - values[1]) + wrap(values[0] - values[2])) / (2 * np.pi)
    return float(np.rint(total))
