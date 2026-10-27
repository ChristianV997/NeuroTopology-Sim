"""Canonical directed-triangle sheaf with one rotated restriction."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from .sheaf import (
    CellularSheaf,
    Edge,
    LinearReadout,
    cycle_sum,
    is_endpoint_compatible,
    scalarize_edge_cochain,
    sheaf_coboundary,
)

I2 = np.eye(2)
R90 = np.array([[0.0, -1.0], [1.0, 0.0]])  # rotation by π/2


def build_canonical_triangle() -> CellularSheaf:
    """Directed triangle 1→2, 2→3, 3→1; stalks R²; ρ_{1≤e31}=R_{π/2}, else I."""
    edges = [
        Edge("e12", "1", "2"),
        Edge("e23", "2", "3"),
        Edge("e31", "3", "1"),
    ]
    vertices = ["1", "2", "3"]
    restrictions = {}
    for e in edges:
        restrictions[(e.src, e.name)] = I2.copy()
        restrictions[(e.dst, e.name)] = I2.copy()
    # override: ρ_{1≤e31} = R_{π/2}, ρ_{3≤e31} = I (already I)
    restrictions[("1", "e31")] = R90.copy()
    return CellularSheaf(
        vertices=vertices,
        edges=edges,
        vertex_dim={v: 2 for v in vertices},
        edge_dim={e.name: 2 for e in edges},
        restrictions=restrictions,
    )


def first_coordinate_readout(sheaf: CellularSheaf) -> LinearReadout:
    return LinearReadout({e.name: np.array([1.0, 0.0]) for e in sheaf.edges})


def compatible_readout_all_identity_sheaf() -> tuple[CellularSheaf, LinearReadout]:
    """Same triangle but all restrictions identity — first-coord readout is compatible."""
    edges = [
        Edge("e12", "1", "2"),
        Edge("e23", "2", "3"),
        Edge("e31", "3", "1"),
    ]
    vertices = ["1", "2", "3"]
    restrictions = {}
    for e in edges:
        restrictions[(e.src, e.name)] = I2.copy()
        restrictions[(e.dst, e.name)] = I2.copy()
    sheaf = CellularSheaf(
        vertices=vertices,
        edges=edges,
        vertex_dim={v: 2 for v in vertices},
        edge_dim={e.name: 2 for e in edges},
        restrictions=restrictions,
    )
    return sheaf, first_coordinate_readout(sheaf)


def run_canonical_triangle() -> Dict[str, Any]:
    """Compute B₀^F z, scalar readout, exactness vs cycle sum for the TASK case."""
    sheaf = build_canonical_triangle()
    readout = first_coordinate_readout(sheaf)
    z = {
        "1": np.array([1.0, 1.0]),
        "2": np.array([0.0, 0.0]),
        "3": np.array([0.0, 0.0]),
    }
    omega = sheaf_coboundary(sheaf, z)
    # Analytic expectations:
    # e12: I*0 - I*(1,1) = (-1,-1)
    # e23: 0
    # e31: R90*(1,1) - I*0 = (-1,1)
    expected = {
        "e12": np.array([-1.0, -1.0]),
        "e23": np.array([0.0, 0.0]),
        "e31": np.array([-1.0, 1.0]),
    }
    scalar = scalarize_edge_cochain(readout, omega)
    # first coordinates: -1, 0, -1; cycle sum = -2
    csum = cycle_sum(scalar, ["e12", "e23", "e31"])
    compat_ok, vmaps, diag = is_endpoint_compatible(sheaf, readout)

    return {
        "z": {k: v.tolist() for k, v in z.items()},
        "B0F_z": {k: v.tolist() for k, v in omega.items()},
        "B0F_z_expected": {k: v.tolist() for k, v in expected.items()},
        "B0F_matches_expected": all(
            np.allclose(omega[k], expected[k]) for k in expected
        ),
        "scalar_edges": scalar,
        "cycle_sum_1231": csum,
        "sheaf_cochain_exact": True,  # ω := B₀^F z by construction
        "scalar_cycle_sum_nonzero": abs(csum) > 1e-12,
        "endpoint_compatible": compat_ok,
        "compatibility_diag": diag,
        "vertex_maps": None if vmaps is None else {k: v.tolist() for k, v in vmaps.items()},
        "claim": (
            "Sheaf 1-cochain ω=B₀^F z is exact, but incompatible first-coordinate "
            "readout yields scalar cycle sum −2 ≠ 0, so the scalar cochain is not exact."
        ),
        "R90": R90.tolist(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_canonical_triangle(), indent=2))
