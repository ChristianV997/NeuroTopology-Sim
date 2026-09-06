"""Deterministic NumPy/SciPy persistent homology fallback for bounded low-dimensional fixtures.

Implements exact Vietoris-Rips persistent homology (H0 and H1) via Z2 boundary matrix
reduction on bounded simplicial complexes.

Guarantees:
- Pure NumPy/SciPy, zero external TDA library dependencies.
- Exact boundary matrix reduction over GF(2).
- Explicit birth/death intervals and persistence pairs.
- Null serialization (no NaN/Inf).
- Marked with ScientificStatus.APPROXIMATE_FIXTURE_ONLY.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.spatial.distance import pdist, squareform

from .base import BaseTDABackend
from .types import (
    BackendCapability,
    BackendCapabilityStatus,
    BackendName,
    InputKind,
    PersistenceInterval,
    PersistencePair,
    ScientificStatus,
    TDAConfig,
)


class DeterministicFallbackBackend(BaseTDABackend):
    """Deterministic simplicial Vietoris-Rips fallback for bounded low-dimensional fixtures."""

    MAX_POINTS_BOUND: int = 128

    @property
    def name(self) -> str:
        return BackendName.FALLBACK.value

    @property
    def scientific_status(self) -> ScientificStatus:
        return ScientificStatus.APPROXIMATE_FIXTURE_ONLY

    def get_capability(self) -> BackendCapability:
        return BackendCapability(
            name=self.name,
            status=BackendCapabilityStatus.AVAILABLE,
            description="Deterministic NumPy/SciPy simplicial persistent homology fallback for bounded low-dimensional fixtures.",
            supported_inputs=[InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX],
            max_dimension_supported=1,
            supports_exact_pairs=True,
            details="Computes exact Vietoris-Rips H0 and H1 filtration via Z2 boundary matrix reduction. Intended for bounded fixtures and testing.",
        )

    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        n = data.shape[0]
        if n > self.MAX_POINTS_BOUND:
            raise ValueError(
                f"Deterministic fallback backend is restricted to bounded fixtures (N <= {self.MAX_POINTS_BOUND}), "
                f"got N={n}. Please use an accelerated TDA backend such as 'ripser' or 'gudhi'."
            )

        if input_kind == InputKind.POINT_CLOUD:
            dist_mat = squareform(pdist(data, metric="euclidean"))
        else:
            dist_mat = data.copy()

        max_thresh = config.max_edge_length
        if max_thresh is None:
            finite_mask = dist_mat > 1e-12
            max_thresh = float(np.max(dist_mat[finite_mask])) if np.any(finite_mask) else 1.0

        # Build Vietoris-Rips simplices up to dimension 2
        # Dim 0: vertices (i,)
        # Dim 1: edges (i, j) with i < j, weight = dist_mat[i, j]
        # Dim 2: triangles (i, j, k) with i < j < k, weight = max(dist_mat[i,j], dist_mat[j,k], dist_mat[i,k])

        simplices: list[tuple[float, int, tuple[int, ...]]] = []
        # Vertices
        for i in range(n):
            simplices.append((0.0, 0, (i,)))

        # Edges
        edge_map: dict[tuple[int, int], int] = {}
        for i in range(n):
            for j in range(i + 1, n):
                d = float(dist_mat[i, j])
                if max_thresh is None or d <= max_thresh:
                    simplices.append((d, 1, (i, j)))

        # Triangles (only needed if computing H1)
        if config.max_dimension >= 1:
            for i in range(n):
                for j in range(i + 1, n):
                    d_ij = float(dist_mat[i, j])
                    if max_thresh is not None and d_ij > max_thresh:
                        continue
                    for k in range(j + 1, n):
                        d_jk = float(dist_mat[j, k])
                        d_ik = float(dist_mat[i, k])
                        if max_thresh is not None and (d_jk > max_thresh or d_ik > max_thresh):
                            continue
                        w_tri = max(d_ij, d_jk, d_ik)
                        if max_thresh is None or w_tri <= max_thresh:
                            simplices.append((w_tri, 2, (i, j, k)))

        # Sort simplices by (birth, dimension, simplex_tuple)
        simplices.sort(key=lambda item: (item[0], item[1], item[2]))

        simplex_to_idx = {s[2]: idx for idx, s in enumerate(simplices)}
        m = len(simplices)

        # Build boundary list for each simplex
        # boundary[j] = set of indices of codimension-1 faces
        boundary: list[set[int]] = [set() for _ in range(m)]
        for j, (birth, dim, s_tuple) in enumerate(simplices):
            if dim == 1:
                # Edge (u, v) -> vertices (u,), (v,)
                u, v = s_tuple
                boundary[j].add(simplex_to_idx[(u,)])
                boundary[j].add(simplex_to_idx[(v,)])
            elif dim == 2:
                # Triangle (u, v, w) -> edges (u, v), (u, w), (v, w)
                u, v, w = s_tuple
                boundary[j].add(simplex_to_idx[(u, v)])
                boundary[j].add(simplex_to_idx[(u, w)])
                boundary[j].add(simplex_to_idx[(v, w)])

        # Column reduction over Z2
        # pivot_col[row_idx] = col_idx that has row_idx as lowest 1
        pivot_col: dict[int, int] = {}
        for j in range(m):
            while boundary[j]:
                low = max(boundary[j])
                if low in pivot_col:
                    k = pivot_col[low]
                    boundary[j] = boundary[j] ^ boundary[k]  # Symmetric difference over Z2
                else:
                    pivot_col[low] = j
                    break

        # Extract persistence intervals and pairs
        b0_intervals: list[PersistenceInterval] = []
        b1_intervals: list[PersistenceInterval] = []
        pairs: list[PersistencePair] = []

        # Simplices killed by higher simplices
        for row_idx, col_idx in pivot_col.items():
            b_simp = simplices[row_idx]
            d_simp = simplices[col_idx]
            dim = b_simp[1]
            birth = float(b_simp[0])
            death = float(d_simp[0])

            # Only report features with positive persistence or valid range
            if dim in (0, 1):
                p = PersistencePair(
                    dimension=dim,
                    birth=birth,
                    death=death,
                    birth_simplex=b_simp[2],
                    death_simplex=d_simp[2],
                )
                pairs.append(p)
                if death > birth:
                    iv = PersistenceInterval(dimension=dim, birth=birth, death=death)
                    if dim == 0:
                        b0_intervals.append(iv)
                    elif dim == 1:
                        b1_intervals.append(iv)

        # Essential simplices (never killed)
        for idx in range(m):
            dim = simplices[idx][1]
            if dim in (0, 1) and idx not in pivot_col:
                # Check if this simplex was a death simplex (column with a pivot)
                # If it had non-empty boundary, it was a death simplex for someone else, not an essential cycle.
                # Only simplices with empty reduced boundary are cycles!
                if not boundary[idx]:
                    birth = float(simplices[idx][0])
                    p = PersistencePair(
                        dimension=dim,
                        birth=birth,
                        death=None,
                        birth_simplex=simplices[idx][2],
                        death_simplex=None,
                    )
                    pairs.append(p)
                    iv = PersistenceInterval(dimension=dim, birth=birth, death=None)
                    if dim == 0:
                        b0_intervals.append(iv)
                    elif dim == 1:
                        b1_intervals.append(iv)

        # Sort intervals by birth, then death
        b0_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))
        b1_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))

        filt_range = (0.0, max_thresh)
        return b0_intervals, b1_intervals, pairs, filt_range
