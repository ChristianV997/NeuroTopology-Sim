"""Persistent H1 analysis for dynamic weighted graphs.

All metrics in this module are graph-derived. ``graph_beta1`` is never a
spatial winding or spatial charge estimate; spatial quantities belong to
``topo_monitor.spatial_phase`` and require coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


GRAPH_PERSISTENCE_METHOD = "vietoris_rips_h1_distance_1_minus_similarity"
DEFAULT_FILTRATION_THRESHOLDS = np.linspace(0.1, 0.9, 9, dtype=float)


@dataclass(frozen=True)
class PersistenceResult:
    diagram_h1: np.ndarray
    beta_curve: np.ndarray
    landscape: np.ndarray
    threshold: float
    sweep_thresholds: np.ndarray | None = None
    sweep_beta1: np.ndarray | None = None
    integrated_landscape_area: float = 0.0
    metric_name: str = "graph_beta1"
    method: str = GRAPH_PERSISTENCE_METHOD
    coordinate_frame: str | None = None

    @property
    def graph_beta1(self) -> int:
        """H1 feature count at the selected graph similarity threshold."""
        if self.sweep_thresholds is not None and self.sweep_beta1 is not None:
            matches = np.flatnonzero(np.isclose(self.sweep_thresholds, self.threshold))
            if matches.size:
                return int(self.sweep_beta1[matches[0]])
        return int(self.beta_curve[-1]) if self.beta_curve.size else 0

    @property
    def persistence_landscape_area(self) -> float:
        return float(self.integrated_landscape_area)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible metadata without silently mixing spaces."""
        return {
            "metric_name": self.metric_name,
            "method": self.method,
            "coordinate_frame": self.coordinate_frame,
            "threshold": float(self.threshold),
            "graph_beta1": self.graph_beta1,
            "thresholds": [] if self.sweep_thresholds is None else self.sweep_thresholds.tolist(),
            "beta1_curve": [] if self.sweep_beta1 is None else self.sweep_beta1.tolist(),
            "persistence_landscape_area": self.persistence_landscape_area,
        }


def _validate(a: np.ndarray) -> np.ndarray:
    arr = np.asarray(a, float)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1] or not np.all(np.isfinite(arr)):
        raise ValueError("adjacency must be finite and square")
    if np.any(arr < 0) or np.any(arr > 1):
        raise ValueError("weighted adjacency must be in [0,1]")
    return (arr + arr.T) / 2


def _validate_diagram(diagram: np.ndarray) -> np.ndarray:
    d = np.asarray(diagram, float)
    if d.size == 0:
        return np.empty((0, 2), dtype=float)
    if d.ndim != 2 or d.shape[1] != 2:
        raise ValueError("diagram must have shape (pairs,2)")
    if np.any(np.isnan(d)) or np.any(d[:, 0] < 0):
        raise ValueError("diagram contains invalid birth/death values")
    return d


def persistence_diagram(adjacency: np.ndarray) -> np.ndarray:
    """Return the graph-derived Vietoris-Rips H1 persistence diagram."""
    try:
        from ripser import ripser
    except ImportError as exc:
        raise RuntimeError("ripser is required for persistent H1") from exc
    a = _validate(adjacency)
    d = 1 - a
    np.fill_diagonal(d, 0)
    diagrams = ripser(d, distance_matrix=True, maxdim=1)["dgms"]
    return _validate_diagram(diagrams[1] if len(diagrams) > 1 else np.empty((0, 2)))


def betti_curve(diagram: np.ndarray, filtration: np.ndarray) -> np.ndarray:
    d = _validate_diagram(diagram)
    grid = np.asarray(filtration, float)
    if grid.ndim != 1 or not np.all(np.isfinite(grid)):
        raise ValueError("filtration must be finite 1D")
    if d.size == 0:
        return np.zeros(grid.shape, int)
    death = np.where(np.isfinite(d[:, 1]), d[:, 1], np.inf)
    return np.sum(
        (grid[None, :] >= d[:, 0, None]) & (grid[None, :] < death[:, None]), axis=0
    ).astype(int)


def persistence_landscape(
    diagram: np.ndarray,
    grid: np.ndarray,
    n_layers: int = 5,
) -> np.ndarray:
    d = _validate_diagram(diagram)
    x = np.asarray(grid, float)
    if n_layers < 1 or x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("invalid landscape parameters")
    finite = d[np.isfinite(d).all(axis=1)] if d.size else np.empty((0, 2))
    out = np.zeros((n_layers, x.size))
    if not finite.size:
        return out
    tents = np.maximum(
        0,
        np.minimum(
            x[None, :] - finite[:, 0, None],
            finite[:, 1, None] - x[None, :],
        ),
    )
    out[: min(n_layers, len(tents))] = np.sort(tents, axis=0)[::-1][:n_layers]
    return out


def filtration_sweep(
    diagram: np.ndarray,
    thresholds: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate graph beta-1 over deterministic similarity thresholds."""
    t = DEFAULT_FILTRATION_THRESHOLDS.copy() if thresholds is None else np.asarray(thresholds, float)
    if t.ndim != 1 or not t.size or not np.all(np.isfinite(t)) or np.any((t < 0) | (t > 1)):
        raise ValueError("thresholds must be finite values in [0,1]")
    if np.any(np.diff(t) <= 0):
        raise ValueError("thresholds must be strictly increasing")
    d = _validate_diagram(diagram)
    death = np.where(np.isfinite(d[:, 1]), d[:, 1], np.inf) if d.size else np.empty(0)
    beta = np.asarray(
        [np.count_nonzero((d[:, 0] <= 1 - value) & (death > 1 - value)) if d.size else 0 for value in t],
        int,
    )
    return t, beta


def analyze_adjacency(
    adjacency: np.ndarray,
    *,
    threshold: float = 0.5,
    grid: np.ndarray | None = None,
    n_layers: int = 5,
    sweep_thresholds: np.ndarray | None = None,
) -> PersistenceResult:
    """Analyze graph H1 with explicit threshold and graph-method metadata."""
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0,1]")
    diagram = persistence_diagram(adjacency)
    x = np.linspace(0, 1, 101) if grid is None else np.asarray(grid, float)
    curve = betti_curve(diagram, x)
    cutoff = 1 - threshold
    death = np.where(np.isfinite(diagram[:, 1]), diagram[:, 1], np.inf) if diagram.size else np.empty(0)
    selected_beta = int(np.count_nonzero((diagram[:, 0] <= cutoff) & (death > cutoff))) if diagram.size else 0
    landscape = persistence_landscape(diagram, x, n_layers)
    sweep_t, sweep_b = filtration_sweep(diagram, sweep_thresholds)
    if not np.any(np.isclose(sweep_t, threshold)):
        sweep_t = np.sort(np.unique(np.r_[sweep_t, threshold]))
        _, sweep_b = filtration_sweep(diagram, sweep_t)
    area = float(np.trapezoid(np.sum(landscape, axis=0), x))
    result = PersistenceResult(
        diagram,
        curve,
        landscape,
        threshold,
        sweep_t,
        sweep_b,
        area,
    )
    # Keep the exact selected value available even when the requested
    # threshold was not part of the default sweep.
    if result.graph_beta1 != selected_beta:
        return PersistenceResult(
            diagram,
            curve,
            landscape,
            threshold,
            np.asarray([threshold]),
            np.asarray([selected_beta]),
            area,
        )
    return result


def _canonical_diagram(diagram: np.ndarray) -> np.ndarray:
    d = _validate_diagram(diagram)
    if not d.size:
        return d
    return d[np.lexsort((d[:, 1], d[:, 0]))]


def reorder_invariant(adjacency: np.ndarray, order: np.ndarray) -> bool:
    """Check that node relabelling preserves graph-derived persistence."""
    a = _validate(adjacency)
    p = np.asarray(order, int)
    if not np.array_equal(np.sort(p), np.arange(len(a))):
        return False
    original = _canonical_diagram(persistence_diagram(a))
    reordered = _canonical_diagram(persistence_diagram(a[np.ix_(p, p)]))
    return original.shape == reordered.shape and np.allclose(original, reordered, equal_nan=True)


def node_order_invariant(adjacency: np.ndarray, order: np.ndarray) -> bool:
    """Descriptive alias whose name makes the graph contract explicit."""
    return reorder_invariant(adjacency, order)
