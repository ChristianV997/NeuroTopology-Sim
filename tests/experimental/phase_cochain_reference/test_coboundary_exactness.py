"""Tests for simplicial coboundary exactness identity d1 @ d0 == 0 and complex validation."""

import numpy as np
import pytest

from experimental.phase_cochain_reference.complex import SimplicialComplex
from experimental.phase_cochain_reference.fixtures import (
    build_annulus_fixture,
    build_dipole_complex_fixture,
    build_single_triangle_fixture,
    build_vortex_quad_fixture,
)


def test_coboundary_exactness_all_fixtures() -> None:
    """Verify that d1 @ d0 == 0 holds identically over integer and real arithmetic."""
    fixtures = [
        ("single_triangle", build_single_triangle_fixture()),
        ("vortex_quad", build_vortex_quad_fixture()),
        ("dipole_complex", build_dipole_complex_fixture()),
        ("annulus_complex", build_annulus_fixture()),
    ]
    for name, c in fixtures:
        assert c.verify_coboundary_exactness(), f"Exactness failed for {name}"
        prod = c.d1 @ c.d0
        assert prod.shape == (c.num_triangles, c.num_vertices)
        assert np.all(prod == 0.0), f"Non-zero entry in d1 @ d0 for {name}"


def test_d0_structure_and_row_sums() -> None:
    """Each row of d0 must correspond to an oriented edge (u, v) with entries -1 at u and +1 at v."""
    c = build_single_triangle_fixture()
    d0 = c.d0
    assert d0.shape == (3, 3)

    for e_idx, (u, v) in enumerate(c.edges):
        assert d0[e_idx, u] == -1.0
        assert d0[e_idx, v] == 1.0
        # All other entries 0
        other_verts = [x for x in range(c.num_vertices) if x not in (u, v)]
        for other in other_verts:
            assert d0[e_idx, other] == 0.0
        # Row sum of d0 is always 0 (constant 0-cochains are in ker d0)
        assert np.sum(d0[e_idx]) == 0.0


def test_d1_structure_and_boundary_cycle() -> None:
    """Each row of d1 must have two +1s and one -1 corresponding to (j, k) - (i, k) + (i, j)."""
    c = build_annulus_fixture()
    d1 = c.d1
    edge_map = c.edge_index_map

    for t_idx, (i, j, k) in enumerate(c.triangles):
        assert d1[t_idx, edge_map[(j, k)]] == 1.0
        assert d1[t_idx, edge_map[(i, k)]] == -1.0
        assert d1[t_idx, edge_map[(i, j)]] == 1.0

        # Exactly 3 non-zero entries per row
        non_zero = np.nonzero(d1[t_idx])[0]
        assert len(non_zero) == 3


def test_simplicial_closure_validation() -> None:
    """Simplicial complex must reject triangles whose boundary edges are not in the edge set."""
    with pytest.raises(ValueError, match="Simplicial closure violated"):
        SimplicialComplex(
            num_vertices=3,
            edges=((0, 1), (1, 2)),  # Missing (0, 2)
            triangles=((0, 1, 2),),
        )


def test_degenerate_simplices_rejected() -> None:
    """Self-loops and degenerate triangles must be rejected."""
    with pytest.raises(ValueError, match="is not canonically sorted"):
        SimplicialComplex(
            num_vertices=3,
            edges=((0, 0),),
            triangles=(),
        )

    with pytest.raises(ValueError, match="is not canonically sorted"):
        SimplicialComplex(
            num_vertices=3,
            edges=((0, 1), (1, 2), (0, 2)),
            triangles=((0, 1, 1),),
        )


def test_out_of_bounds_vertices_rejected() -> None:
    """Vertices exceeding num_vertices must be rejected."""
    with pytest.raises(ValueError, match="out of bounds"):
        SimplicialComplex(
            num_vertices=3,
            edges=((0, 3),),
            triangles=(),
        )


def test_coordinate_dimension_validation() -> None:
    """Coordinate array must match (num_vertices, D)."""
    with pytest.raises(ValueError, match="coordinates must have shape"):
        SimplicialComplex(
            num_vertices=3,
            edges=((0, 1),),
            triangles=(),
            coordinates=np.zeros((4, 2)),
        )


def test_from_triangles_deduction() -> None:
    """from_triangles must automatically deduce and canonicalize all edges."""
    c = SimplicialComplex.from_triangles([(2, 0, 1), (1, 3, 2)])
    assert c.num_vertices == 4
    assert c.num_triangles == 2
    assert (0, 1, 2) in c.triangles
    assert (1, 2, 3) in c.triangles
    assert c.verify_coboundary_exactness()
