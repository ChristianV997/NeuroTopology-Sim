"""Deterministic sparse graph/cohomology proxy for high-dimensional PITNN TDA.

This is a bounded-memory approximation: points are subsampled before building a
k-nearest-neighbour graph. Its beta-1 is the graph cycle rank, not a claim of
full Vietoris-Rips persistent cohomology equivalence.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class SparseTDAConfig:
    max_points: int = 512
    neighbors: int = 8


def sparsify_points(points: np.ndarray, max_points: int = 512) -> np.ndarray:
    """Return deterministic evenly-spaced points, bounded by `max_points`."""
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2 or not np.all(np.isfinite(values)) or max_points < 2:
        raise ValueError("points must be finite (samples>=2, dimensions) and max_points>=2")
    if len(values) <= max_points:
        return values.copy()
    indices = np.linspace(0, len(values) - 1, max_points, dtype=int)
    return values[indices]


def sparse_cycle_rank(points: np.ndarray, config: SparseTDAConfig = SparseTDAConfig()) -> dict:
    """Compute bounded kNN graph components and beta-1 cycle rank."""
    data = sparsify_points(points, config.max_points)
    k = min(max(1, config.neighbors), len(data) - 1)
    _, indices = cKDTree(data).query(data, k=k + 1)
    edges = {tuple(sorted((i, int(j)))) for i, row in enumerate(indices) for j in row[1:] if i != int(j)}
    parent = np.arange(len(data))
    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]; value = int(parent[value])
        return value
    for left, right in edges:
        a, b = find(left), find(right)
        if a != b: parent[a] = b
    components = len({find(i) for i in range(len(data))})
    beta1 = max(0, len(edges) - len(data) + components)
    return {"beta1_proxy": int(beta1), "components": int(components), "edges": int(len(edges)), "points_used": int(len(data))}
