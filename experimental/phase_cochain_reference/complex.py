"""Simplicial complex representation and oriented coboundary operators.

Provides an explicit, coordinate-aware simplicial complex data structure
with exact coboundary operators d0 and d1 satisfying the topological
exactness identity d1 @ d0 == 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np


def _canonicalize_edge(u: int, v: int) -> tuple[int, int]:
    """Return canonically sorted edge tuple with u < v."""
    if u == v:
        raise ValueError(f"Degenerate self-loop edge ({u}, {v}) is not permitted in a simplicial complex.")
    return (u, v) if u < v else (v, u)


def _canonicalize_triangle(i: int, j: int, k: int) -> tuple[int, int, int]:
    """Return canonically sorted triangle tuple with i < j < k."""
    verts = {i, j, k}
    if len(verts) < 3:
        raise ValueError(f"Degenerate triangle ({i}, {j}, {k}) contains duplicate vertices.")
    sorted_verts = tuple(sorted(verts))
    return sorted_verts[0], sorted_verts[1], sorted_verts[2]


@dataclass(frozen=True)
class SimplicialComplex:
    """Explicit, finite 2-dimensional simplicial complex.

    Vertices are indexed 0, 1, ..., num_vertices - 1.
    Edges are canonically sorted pairs (u, v) with u < v.
    Triangles are canonically sorted triples (i, j, k) with i < j < k.
    """

    num_vertices: int
    edges: tuple[tuple[int, int], ...]
    triangles: tuple[tuple[int, int, int], ...]
    coordinates: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.num_vertices <= 0:
            raise ValueError(f"num_vertices must be positive, got {self.num_vertices}")

        # Validate coordinate dimensions if provided
        if self.coordinates is not None:
            coords = np.asarray(self.coordinates, dtype=float)
            if coords.ndim != 2 or coords.shape[0] != self.num_vertices:
                raise ValueError(
                    f"coordinates must have shape (num_vertices={self.num_vertices}, D), "
                    f"got {coords.shape}"
                )
            # Store immutable view or copy
            object.__setattr__(self, "coordinates", coords)

        # Validate edges
        seen_edges: set[tuple[int, int]] = set()
        for edge in self.edges:
            if len(edge) != 2:
                raise ValueError(f"Edge must be a 2-tuple, got {edge}")
            u, v = edge
            if not (0 <= u < self.num_vertices and 0 <= v < self.num_vertices):
                raise ValueError(f"Edge vertices ({u}, {v}) out of bounds [0, {self.num_vertices - 1}]")
            if u >= v:
                raise ValueError(f"Edge ({u}, {v}) is not canonically sorted (requires u < v)")
            if edge in seen_edges:
                raise ValueError(f"Duplicate edge {edge} detected")
            seen_edges.add(edge)

        # Validate triangles & simplicial closure
        seen_triangles: set[tuple[int, int, int]] = set()
        for tri in self.triangles:
            if len(tri) != 3:
                raise ValueError(f"Triangle must be a 3-tuple, got {tri}")
            i, j, k = tri
            if not (0 <= i < self.num_vertices and 0 <= j < self.num_vertices and 0 <= k < self.num_vertices):
                raise ValueError(f"Triangle vertices ({i}, {j}, {k}) out of bounds [0, {self.num_vertices - 1}]")
            if not (i < j < k):
                raise ValueError(f"Triangle ({i}, {j}, {k}) is not canonically sorted (requires i < j < k)")
            if tri in seen_triangles:
                raise ValueError(f"Duplicate triangle {tri} detected")
            seen_triangles.add(tri)

            # Simplicial closure check: all 3 boundary edges must exist in the complex
            boundary_edges = [(i, j), (j, k), (i, k)]
            for b_edge in boundary_edges:
                if b_edge not in seen_edges:
                    raise ValueError(
                        f"Simplicial closure violated: triangle {tri} requires edge {b_edge}, "
                        f"which is missing from the edge set."
                    )

    @property
    def num_edges(self) -> int:
        """Return the number of edges."""
        return len(self.edges)

    @property
    def num_triangles(self) -> int:
        """Return the number of triangles."""
        return len(self.triangles)

    @property
    def edge_index_map(self) -> dict[tuple[int, int], int]:
        """Mapping from canonical edge (u, v) to its row index in d0."""
        return {e: idx for idx, e in enumerate(self.edges)}

    @property
    def triangle_index_map(self) -> dict[tuple[int, int, int], int]:
        """Mapping from canonical triangle (i, j, k) to its row index in d1."""
        return {t: idx for idx, t in enumerate(self.triangles)}

    @property
    def d0(self) -> np.ndarray:
        """Oriented coboundary operator d0: C^0 -> C^1.

        Matrix of shape (|E|, |V|).
        For edge e = (u, v) with u < v:
            (d0 theta)_e = theta_v - theta_u
            d0[e, v] = +1.0
            d0[e, u] = -1.0
        """
        matrix = np.zeros((self.num_edges, self.num_vertices), dtype=float)
        for e_idx, (u, v) in enumerate(self.edges):
            matrix[e_idx, v] = 1.0
            matrix[e_idx, u] = -1.0
        return matrix

    @property
    def d1(self) -> np.ndarray:
        """Oriented coboundary operator d1: C^1 -> C^2.

        Matrix of shape (|T|, |E|).
        For canonically oriented triangle t = (i, j, k) with i < j < k:
            Boundary cycle: partial_2 t = (j, k) - (i, k) + (i, j)
            (d1 omega)_t = omega_(j, k) - omega_(i, k) + omega_(i, j)
            d1[t, (j, k)] = +1.0
            d1[t, (i, k)] = -1.0
            d1[t, (i, j)] = +1.0
        """
        matrix = np.zeros((self.num_triangles, self.num_edges), dtype=float)
        edge_map = self.edge_index_map
        for t_idx, (i, j, k) in enumerate(self.triangles):
            e_jk = edge_map[(j, k)]
            e_ik = edge_map[(i, k)]
            e_ij = edge_map[(i, j)]
            matrix[t_idx, e_jk] = 1.0
            matrix[t_idx, e_ik] = -1.0
            matrix[t_idx, e_ij] = 1.0
        return matrix

    def verify_coboundary_exactness(self) -> bool:
        """Verify the fundamental exactness identity d1 @ d0 == 0.

        Returns True if d1 @ d0 is identically zero, otherwise False.
        """
        if self.num_triangles == 0 or self.num_edges == 0:
            return True
        product = self.d1 @ self.d0
        return bool(np.all(product == 0.0))

    def triangle_barycenters(self) -> np.ndarray:
        """Compute the spatial barycenters of all triangles.

        Returns:
            np.ndarray of shape (|T|, D).
        Raises:
            ValueError if coordinates were not provided on initialization.
        """
        if self.coordinates is None:
            raise ValueError("Coordinates are required to compute triangle barycenters.")
        barycenters = np.zeros((self.num_triangles, self.coordinates.shape[1]), dtype=float)
        for t_idx, (i, j, k) in enumerate(self.triangles):
            barycenters[t_idx] = (
                self.coordinates[i] + self.coordinates[j] + self.coordinates[k]
            ) / 3.0
        return barycenters

    @classmethod
    def from_triangles(
        cls,
        triangles: Sequence[Sequence[int]],
        coordinates: np.ndarray | None = None,
        num_vertices: int | None = None,
    ) -> SimplicialComplex:
        """Construct a simplicial complex automatically deducing canonical edges from triangles.

        Args:
            triangles: Collection of 3-element sequences of vertex indices.
            coordinates: Optional (N, D) vertex coordinates.
            num_vertices: Total vertices; if None, inferred from max vertex index in triangles.
        """
        canonical_triangles_set: set[tuple[int, int, int]] = set()
        canonical_edges_set: set[tuple[int, int]] = set()
        max_v = -1

        for tri in triangles:
            if len(tri) != 3:
                raise ValueError(f"Each triangle must have 3 vertices, got {tri}")
            ctri = _canonicalize_triangle(int(tri[0]), int(tri[1]), int(tri[2]))
            canonical_triangles_set.add(ctri)
            i, j, k = ctri
            max_v = max(max_v, i, j, k)
            canonical_edges_set.add((i, j))
            canonical_edges_set.add((j, k))
            canonical_edges_set.add((i, k))

        inferred_num_v = max_v + 1 if max_v >= 0 else 0
        if num_vertices is not None:
            if num_vertices < inferred_num_v:
                raise ValueError(
                    f"num_vertices={num_vertices} is smaller than highest vertex index {max_v}"
                )
            actual_num_v = num_vertices
        else:
            if coordinates is not None:
                actual_num_v = len(coordinates)
            else:
                actual_num_v = inferred_num_v

        sorted_edges = tuple(sorted(canonical_edges_set))
        sorted_triangles = tuple(sorted(canonical_triangles_set))

        return cls(
            num_vertices=actual_num_v,
            edges=sorted_edges,
            triangles=sorted_triangles,
            coordinates=coordinates,
        )
