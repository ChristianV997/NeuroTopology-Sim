"""Cellular sheaf coboundary and edgewise linear readouts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class Edge:
    """Oriented edge e = (u, v)."""

    name: str
    src: str  # u
    dst: str  # v


@dataclass
class CellularSheaf:
    """Finite cellular sheaf on an oriented graph (0- and 1-skeleta).

    Vertex stalks R^{d_v}, edge stalks R^{k_e}, restrictions ρ_{v≤e}: stalk(v)→stalk(e).
    """

    vertices: Sequence[str]
    edges: Sequence[Edge]
    vertex_dim: Mapping[str, int]
    edge_dim: Mapping[str, int]
    # restrictions[(vertex, edge_name)] -> (k_e, d_v) matrix
    restrictions: Dict[Tuple[str, str], Array]

    def restriction(self, vertex: str, edge_name: str) -> Array:
        key = (vertex, edge_name)
        if key not in self.restrictions:
            raise KeyError(f"missing restriction ρ_{{{vertex}≤{edge_name}}}")
        return np.asarray(self.restrictions[key], dtype=float)


@dataclass
class LinearReadout:
    """Edgewise linear maps Λ_e : R^{k_e} → R (row vectors / 1×k matrices)."""

    # edge_name -> shape (k_e,) row
    maps: Dict[str, Array]

    def apply(self, edge_name: str, value: Array) -> float:
        lam = np.asarray(self.maps[edge_name], dtype=float).reshape(-1)
        return float(lam @ np.asarray(value, dtype=float).reshape(-1))


def sheaf_coboundary(
    sheaf: CellularSheaf, z: Mapping[str, Array]
) -> Dict[str, Array]:
    """(B₀^F z)_e = ρ_{v≤e} z_v − ρ_{u≤e} z_u for e=(u,v)."""
    out: Dict[str, Array] = {}
    for e in sheaf.edges:
        zu = np.asarray(z[e.src], dtype=float).reshape(-1)
        zv = np.asarray(z[e.dst], dtype=float).reshape(-1)
        rho_u = sheaf.restriction(e.src, e.name)
        rho_v = sheaf.restriction(e.dst, e.name)
        out[e.name] = rho_v @ zv - rho_u @ zu
    return out


def scalarize_edge_cochain(
    readout: LinearReadout, omega: Mapping[str, Array]
) -> Dict[str, float]:
    return {name: readout.apply(name, val) for name, val in omega.items()}


def cycle_sum(scalar_edges: Mapping[str, float], cycle: Sequence[str]) -> float:
    """Sum of scalar affinities along an oriented edge cycle (by edge name)."""
    return float(sum(scalar_edges[e] for e in cycle))


def is_endpoint_compatible(
    sheaf: CellularSheaf,
    readout: LinearReadout,
    tol: float = 1e-10,
) -> Tuple[bool, Optional[Dict[str, Array]], str]:
    """Check existence of vertex maps Λ_{0,v} with Λ_e ∘ ρ_{w≤e} = Λ_{0,w}.

    Returns (ok, vertex_maps or None, diagnostic).
    """
    # Candidate Λ_{0,v} collected from incident half-edges; must agree.
    candidates: Dict[str, List[Array]] = {v: [] for v in sheaf.vertices}
    for e in sheaf.edges:
        lam = np.asarray(readout.maps[e.name], dtype=float).reshape(1, -1)
        for w in (e.src, e.dst):
            rho = sheaf.restriction(w, e.name)
            composed = (lam @ rho).reshape(-1)  # 1 × d_w
            candidates[w].append(composed)

    vertex_maps: Dict[str, Array] = {}
    for v, mats in candidates.items():
        if not mats:
            # isolated vertex: free choice; use zeros of declared dim
            vertex_maps[v] = np.zeros(sheaf.vertex_dim[v], dtype=float)
            continue
        ref = mats[0]
        for m in mats[1:]:
            if m.shape != ref.shape or np.linalg.norm(m - ref) > tol:
                return (
                    False,
                    None,
                    f"endpoint incompatibility at vertex {v}: {ref} vs {m}",
                )
        vertex_maps[v] = ref
    return True, vertex_maps, "endpoint-compatible"


def scalar_coboundary(
    sheaf: CellularSheaf, phi: Mapping[str, float]
) -> Dict[str, float]:
    """Ordinary graph coboundary (B₀ φ)_e = φ_v − φ_u."""
    return {e.name: float(phi[e.dst] - phi[e.src]) for e in sheaf.edges}


def exactness_preserved(
    sheaf: CellularSheaf,
    readout: LinearReadout,
    z: Mapping[str, Array],
    tol: float = 1e-9,
) -> Tuple[bool, Dict[str, float], float]:
    """If compatible, Λ B₀^F z equals B₀ (Λ₀ z) and cycle sums vanish on graph cycles.

    Returns (exact_scalar, scalar_edges, triangle_cycle_sum_if_present).
    """
    omega = sheaf_coboundary(sheaf, z)
    scalar_edges = scalarize_edge_cochain(readout, omega)
    ok, vmaps, _ = is_endpoint_compatible(sheaf, readout, tol=tol)
    cycle_names = [e.name for e in sheaf.edges]
    csum = cycle_sum(scalar_edges, cycle_names) if len(sheaf.edges) >= 3 else float("nan")

    if not ok or vmaps is None:
        # Incompatible: scalar need not be exact
        # Check whether scalar happens to be a coboundary anyway
        # For triangle: exactness ⇔ cycle sum 0
        is_exact = abs(csum) <= tol if np.isfinite(csum) else False
        return is_exact, scalar_edges, csum

    phi = {v: float(vmaps[v] @ np.asarray(z[v], dtype=float).reshape(-1)) for v in sheaf.vertices}
    expected = scalar_coboundary(sheaf, phi)
    err = max(abs(scalar_edges[e] - expected[e]) for e in scalar_edges)
    return err <= tol, scalar_edges, csum


def reverse_edge_orientation(sheaf: CellularSheaf, edge_name: str) -> CellularSheaf:
    """Return a new sheaf with one edge orientation reversed and restrictions swapped.

    For e=(u,v) → e'=(v,u): (B z)_{e'} = ρ_u z_u − ρ_v z_v = −(B z)_e when the
    same restriction matrices are attached to the same endpoints.
    """
    new_edges: List[Edge] = []
    new_restr = dict(sheaf.restrictions)
    for e in sheaf.edges:
        if e.name != edge_name:
            new_edges.append(e)
            continue
        # swap endpoints; keep restriction keys as (vertex, edge_name)
        new_edges.append(Edge(name=e.name, src=e.dst, dst=e.src))
        # restrictions already keyed by (vertex, edge); no change needed
        _ = new_restr
    return CellularSheaf(
        vertices=list(sheaf.vertices),
        edges=new_edges,
        vertex_dim=dict(sheaf.vertex_dim),
        edge_dim=dict(sheaf.edge_dim),
        restrictions=new_restr,
    )


def random_vertex_cochain(
    sheaf: CellularSheaf, rng: np.random.Generator
) -> Dict[str, Array]:
    return {
        v: rng.normal(size=sheaf.vertex_dim[v]) for v in sheaf.vertices
    }
