"""Pure NumPy/Python reference Vietoris-Rips persistent homology engine.

Provides zero-dependency ground-truth persistence calculations over Z_2 coefficients
for small finite complexes (points, edges, triangles, tetrahedra).
Used as an independent mathematical reference to verify semantic conformance of
optional TDA backends.
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from .models import PersistenceBar


def compute_euclidean_distance_matrix(points: np.ndarray) -> np.ndarray:
    """Compute symmetric pairwise Euclidean distance matrix."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2:
        raise ValueError(f"points must be 2D (N, D), got {pts.shape}")
    diff = pts[:, np.newaxis, :] - pts[np.newaxis, :, :]
    dist = np.sqrt(np.sum(diff ** 2, axis=-1))
    np.fill_diagonal(dist, 0.0)
    return dist


def compute_vietoris_rips_reference(
    distance_matrix: np.ndarray,
    max_dimension: int = 1,
    threshold: float | None = None,
) -> dict[int, list[PersistenceBar]]:
    """Compute exact Vietoris-Rips persistence diagrams up to max_dimension over Z_2.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Square symmetric non-negative matrix with zero diagonal.
    max_dimension : int
        Maximum homology dimension (0, 1, or 2).
    threshold : float, optional
        Maximum filtration parameter. Simplices with diameter > threshold are omitted.

    Returns
    -------
    dict[int, list[PersistenceBar]]
        Persistence bars sorted canonically for each dimension.
    """
    D = np.asarray(distance_matrix, dtype=np.float64)
    if D.ndim != 2 or D.shape[0] != D.shape[1]:
        raise ValueError("distance_matrix must be square 2D array")
    n = D.shape[0]

    diagrams: dict[int, list[PersistenceBar]] = {d: [] for d in range(max_dimension + 1)}
    if n == 0:
        return diagrams

    # Symmetrize and zero-diagonal
    D = 0.5 * (D + D.T)
    np.fill_diagonal(D, 0.0)

    t_max = float(threshold) if threshold is not None else float("inf")

    # 1. Enumerate simplices with their filtration values (diameter)
    # Simplex represented as tuple of sorted vertex indices
    simplices: list[tuple[float, int, tuple[int, ...]]] = []

    # 0-simplices (vertices) all born at 0.0
    for i in range(n):
        simplices.append((0.0, 0, (i,)))

    # 1-simplices (edges)
    for i in range(n):
        for j in range(i + 1, n):
            weight = float(D[i, j])
            if weight <= t_max:
                simplices.append((weight, 1, (i, j)))

    # 2-simplices (triangles) if max_dimension >= 1
    if max_dimension >= 1:
        for i in range(n):
            for j in range(i + 1, n):
                d_ij = D[i, j]
                for k in range(j + 1, n):
                    d_ik = D[i, k]
                    d_jk = D[j, k]
                    weight = float(max(d_ij, d_ik, d_jk))
                    if weight <= t_max:
                        simplices.append((weight, 2, (i, j, k)))

    # 3-simplices (tetrahedra) if max_dimension >= 2
    if max_dimension >= 2:
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    for l in range(k + 1, n):
                        weight = float(max(D[i, j], D[i, k], D[i, l], D[j, k], D[j, l], D[k, l]))
                        if weight <= t_max:
                            simplices.append((weight, 3, (i, j, k, l)))

    # 2. Sort simplices: filtration value ascending, dimension ascending, vertices ascending
    simplices.sort(key=lambda s: (round(s[0], 9), s[1], s[2]))
    simplex_to_idx = {s[2]: idx for idx, s in enumerate(simplices)}
    m = len(simplices)

    # 3. Construct boundary matrix over Z_2 (represented as sets of row indices)
    boundary_cols: list[set[int]] = []
    for filt, dim, verts in simplices:
        col: set[int] = set()
        if dim == 1:
            col.add(simplex_to_idx[(verts[0],)])
            col.add(simplex_to_idx[(verts[1],)])
        elif dim == 2:
            col.add(simplex_to_idx[(verts[0], verts[1])])
            col.add(simplex_to_idx[(verts[0], verts[2])])
            col.add(simplex_to_idx[(verts[1], verts[2])])
        elif dim == 3:
            col.add(simplex_to_idx[(verts[0], verts[1], verts[2])])
            col.add(simplex_to_idx[(verts[0], verts[1], verts[3])])
            col.add(simplex_to_idx[(verts[0], verts[2], verts[3])])
            col.add(simplex_to_idx[(verts[1], verts[2], verts[3])])
        boundary_cols.append(col)

    # 4. Standard persistence reduction algorithm over Z_2
    low: dict[int, int] = {}  # pivot row -> col
    is_paired_creator: set[int] = set()
    pairs: list[tuple[int, int]] = []

    for j in range(m):
        while boundary_cols[j]:
            pivot = max(boundary_cols[j])
            if pivot in low:
                other_col = low[pivot]
                boundary_cols[j] ^= boundary_cols[other_col]
            else:
                low[pivot] = j
                is_paired_creator.add(pivot)
                pairs.append((pivot, j))
                break

    # 5. Extract paired intervals [birth, death)
    for birth_idx, death_idx in pairs:
        birth_dim = simplices[birth_idx][1]
        birth_val = simplices[birth_idx][0]
        death_val = simplices[death_idx][0]

        if birth_dim <= max_dimension:
            # Drop zero-persistence pairs (birth == death) to match standard diagram conventions
            if abs(death_val - birth_val) > 1e-9:
                diagrams[birth_dim].append(
                    PersistenceBar.from_pair(birth_dim, birth_val, death_val)
                )

    # 6. Extract unpaired intervals (infinite persistence)
    for i in range(m):
        if i not in is_paired_creator and i not in low.values():
            dim = simplices[i][1]
            birth_val = simplices[i][0]
            if dim <= max_dimension:
                diagrams[dim].append(
                    PersistenceBar.from_pair(dim, birth_val, None)
                )

    # 7. Canonical sort per dimension
    for dim in diagrams:
        diagrams[dim].sort(
            key=lambda b: (
                round(b.birth, 8),
                round(b.death, 8) if b.death is not None else float("inf")
            )
        )

    return diagrams
