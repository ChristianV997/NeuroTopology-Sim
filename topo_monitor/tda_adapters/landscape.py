"""Deterministic beta-1 persistence landscape calculations.

Implements Bubenik (2015) persistence landscapes:
- Explicit tent functions f_{(b, d)}(t) = max(0, min(t - b, d - t)).
- Layer extraction lambda_k(t) via deterministic descending order.
- Exact trapezoidal integration over explicit filtration grids.
- Sanitized outputs free of NaN and Infinity.
"""
from __future__ import annotations

from typing import Sequence
import numpy as np

from .types import PersistenceInterval, sanitize_float


def compute_persistence_landscape(
    intervals: Sequence[PersistenceInterval] | np.ndarray,
    grid: np.ndarray | Sequence[float] | None = None,
    num_layers: int = 5,
    resolution: int = 101,
    filtration_range: tuple[float, float | None] | None = None,
) -> tuple[list[list[float]], list[float], float]:
    """Compute explicit, deterministic persistence landscape layers and integrated area.

    Args:
        intervals: Collection of PersistenceInterval objects or (K, 2) array of [birth, death].
        grid: Optional explicit 1D evaluation grid. If None, derived from filtration_range or intervals.
        num_layers: Number of landscape layers to compute (k = 1..num_layers).
        resolution: Number of grid evaluation points if grid is None.
        filtration_range: Optional (min_filt, max_filt) tuple.

    Returns:
        (landscape_layers, grid_points, integrated_area):
        - landscape_layers: List of num_layers rows, each row containing resolution floats.
        - grid_points: List of grid evaluation points.
        - integrated_area: Total trapezoidal area under all landscape layers.
    """
    if num_layers < 1:
        raise ValueError(f"num_layers must be >= 1, got {num_layers}")

    # Extract finite [birth, death] pairs
    pairs: list[tuple[float, float]] = []
    if isinstance(intervals, np.ndarray):
        if intervals.size > 0:
            if intervals.ndim != 2 or intervals.shape[1] != 2:
                raise ValueError("intervals array must have shape (K, 2)")
            for row in intervals:
                b, d = float(row[0]), float(row[1])
                if np.isfinite(b) and np.isfinite(d) and d > b:
                    pairs.append((b, d))
    else:
        for iv in intervals:
            b = iv.birth
            d = iv.death
            if d is not None and np.isfinite(b) and np.isfinite(d) and d > b:
                pairs.append((float(b), float(d)))

    # Determine evaluation grid
    if grid is not None:
        x_grid = np.asarray(grid, dtype=np.float64)
        if x_grid.ndim != 1 or len(x_grid) < 2 or not np.all(np.isfinite(x_grid)):
            raise ValueError("explicit grid must be a finite 1D array with at least 2 points")
    else:
        if filtration_range is not None and filtration_range[1] is not None:
            t_min, t_max = float(filtration_range[0]), float(filtration_range[1])
        elif pairs:
            t_min = min(p[0] for p in pairs)
            t_max = max(p[1] for p in pairs)
            if t_min == t_max:
                t_max = t_min + 1.0
        else:
            t_min, t_max = 0.0, 1.0

        if resolution < 2:
            raise ValueError(f"resolution must be >= 2, got {resolution}")
        x_grid = np.linspace(t_min, t_max, resolution, dtype=np.float64)

    m = len(x_grid)
    out_layers = np.zeros((num_layers, m), dtype=np.float64)

    if pairs:
        pair_arr = np.asarray(pairs, dtype=np.float64)  # (P, 2)
        births = pair_arr[:, 0, None]  # (P, 1)
        deaths = pair_arr[:, 1, None]  # (P, 1)
        x_row = x_grid[None, :]        # (1, M)

        # Tent function: f(t) = max(0, min(t - b, d - t))
        tents = np.maximum(0.0, np.minimum(x_row - births, deaths - x_row))  # (P, M)

        # Sort tents along simplex dimension descending for each column (grid point)
        sorted_tents = np.sort(tents, axis=0)[::-1]
        active_k = min(num_layers, sorted_tents.shape[0])
        out_layers[:active_k, :] = sorted_tents[:active_k, :]

    # Deterministic integration via trapezoidal rule
    trap_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    if trap_fn is not None:
        layer_sum = np.sum(out_layers, axis=0)
        total_area = float(trap_fn(layer_sum, x_grid))
    else:
        # Fallback explicit trapezoidal calculation
        dx = np.diff(x_grid)
        layer_sum = np.sum(out_layers, axis=0)
        total_area = float(np.sum(dx * (layer_sum[:-1] + layer_sum[1:]) / 2.0))

    clean_layers = [[float(v) for v in row] for row in out_layers]
    clean_grid = [float(v) for v in x_grid]
    clean_area = float(max(0.0, total_area))

    return clean_layers, clean_grid, clean_area
