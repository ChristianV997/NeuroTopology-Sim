"""Independently derived oriented incidence matrices for 2-complexes.

Canonical orientation conventions (hand-derived, not imported from proposals):
- Edges stored as (u, v) with u < v.
- Triangles stored as (i, j, k) with i < j < k.
- d0[e, v] = +1, d0[e, u] = -1  => (d0 theta)_e = theta_v - theta_u
- d1[t, (i,j)] = +1, d1[t, (j,k)] = +1, d1[t, (i,k)] = -1
  => (d1 omega)_t = omega_ij + omega_jk - omega_ik
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

Edge = Tuple[int, int]
Triangle = Tuple[int, int, int]


def canonicalize_edge(u: int, v: int) -> Edge:
    if u == v:
        raise ValueError("degenerate self-loop")
    return (u, v) if u < v else (v, u)


def canonicalize_triangle(i: int, j: int, k: int) -> Triangle:
    verts = sorted({i, j, k})
    if len(verts) != 3:
        raise ValueError("degenerate triangle")
    return verts[0], verts[1], verts[2]


@dataclass(frozen=True)
class OrientedComplex:
    """Tiny synthetic complex with independently derived incidence."""

    name: str
    boundary_class: str
    num_vertices: int
    edges: Tuple[Edge, ...]
    triangles: Tuple[Triangle, ...]
    notes: str

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    @property
    def num_triangles(self) -> int:
        return len(self.triangles)

    @property
    def edge_index(self) -> Dict[Edge, int]:
        return {e: i for i, e in enumerate(self.edges)}

    def d0(self) -> np.ndarray:
        mat = np.zeros((self.num_edges, self.num_vertices), dtype=float)
        for e_idx, (u, v) in enumerate(self.edges):
            mat[e_idx, v] = 1.0
            mat[e_idx, u] = -1.0
        return mat

    def d1(self) -> np.ndarray:
        mat = np.zeros((self.num_triangles, self.num_edges), dtype=float)
        emap = self.edge_index
        for t_idx, (i, j, k) in enumerate(self.triangles):
            mat[t_idx, emap[(i, j)]] = 1.0
            mat[t_idx, emap[(j, k)]] = 1.0
            mat[t_idx, emap[(i, k)]] = -1.0
        return mat


def validate_incidence(complex_: OrientedComplex) -> Dict[str, object]:
    """Check d1@d0=0 and dimension equations. Algebraic over this construction."""
    d0 = complex_.d0()
    d1 = complex_.d1()
    product = d1 @ d0
    max_abs = float(np.max(np.abs(product))) if product.size else 0.0
    dims_ok = d0.shape == (complex_.num_edges, complex_.num_vertices) and d1.shape == (
        complex_.num_triangles,
        complex_.num_edges,
    )
    # Closure: every triangle boundary edge present
    closure_ok = True
    missing: List[str] = []
    emap = complex_.edge_index
    for tri in complex_.triangles:
        i, j, k = tri
        for edge in ((i, j), (j, k), (i, k)):
            if edge not in emap:
                closure_ok = False
                missing.append(f"{tri}->{edge}")
    return {
        "d1_d0_max_abs": max_abs,
        "d1_d0_is_zero": max_abs == 0.0,
        "dimension_equations_ok": dims_ok,
        "d0_shape": list(d0.shape),
        "d1_shape": list(d1.shape),
        "simplicial_closure_ok": closure_ok,
        "missing_boundary_edges": missing,
        "identity_class": "algebraic",
    }


def edges_from_triangles(triangles: Sequence[Triangle]) -> Tuple[Edge, ...]:
    edges: set[Edge] = set()
    for i, j, k in triangles:
        edges.add(canonicalize_edge(i, j))
        edges.add(canonicalize_edge(j, k))
        edges.add(canonicalize_edge(i, k))
    return tuple(sorted(edges))
