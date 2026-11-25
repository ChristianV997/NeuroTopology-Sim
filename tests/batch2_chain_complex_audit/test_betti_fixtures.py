"""Exact Betti numbers for synthetic fixtures (independent oracle)."""

from __future__ import annotations

import pytest

from tools.batch2_chain_complex_audit.fixtures import (
    closed_surface_sphere,
    disconnected_two_edges,
    empty_complex,
    filled_tetrahedron,
    filled_triangle,
    open_triangular_prism,
    single_edge,
    tetrahedron_surface,
    triangle_boundary,
    two_isolated_vertices,
    wedge_circle_and_sphere,
)


@pytest.mark.parametrize(
    "factory, expected",
    [
        (empty_complex, (0, 0, 0, 0)),
        (two_isolated_vertices, (2, 0, 0, 0)),
        (single_edge, (1, 0, 0, 0)),
        (triangle_boundary, (1, 1, 0, 0)),
        (filled_triangle, (1, 0, 0, 0)),
        (tetrahedron_surface, (1, 0, 1, 0)),
        (closed_surface_sphere, (1, 0, 1, 0)),
        (filled_tetrahedron, (1, 0, 0, 0)),
        (open_triangular_prism, (1, 1, 0, 0)),  # proposal claim (1,1,0)
        (disconnected_two_edges, (2, 0, 0, 0)),
        (wedge_circle_and_sphere, (2, 1, 1, 0)),  # nontrivial H1 and H2
    ],
    ids=lambda x: x.__name__ if callable(x) else str(x),
)
def test_exact_betti(factory, expected):
    c = factory()
    assert c.betti() == expected


def test_betti_matches_rank_dimension_formulas():
    c = open_triangular_prism()
    ranks = c.ranks()
    b0, b1, b2, b3 = c.betti()
    assert b0 == ranks["n0"] - ranks["rank_d1"]
    assert b1 == ranks["n1"] - ranks["rank_d1"] - ranks["rank_d2"]
    assert b2 == ranks["n2"] - ranks["rank_d2"] - ranks["rank_d3"]
    assert b3 == ranks["n3"] - ranks["rank_d3"]


def test_open_prism_dimensions_documented():
    """Document matrix sizes used for the proposal's (1,1,0) fixture."""
    c = open_triangular_prism()
    r = c.ranks()
    assert (r["n0"], r["n1"], r["n2"], r["n3"]) == (6, 12, 6, 0)
    b0, b1, b2, b3 = c.betti()
    assert (b0, b1, b2, b3) == (1, 1, 0, 0)
    # Connected open prism: rank ∂1 = n0 - β0 = 5; rank ∂2 = n1 - rank∂1 - β1 = 6
    assert r["rank_d1"] == 5
    assert r["rank_d2"] == 6
    assert r["rank_d3"] == 0


def test_filled_vs_hollow_tetrahedron_kills_h2():
    hollow = tetrahedron_surface().betti()
    solid = filled_tetrahedron().betti()
    assert hollow == (1, 0, 1, 0)
    assert solid == (1, 0, 0, 0)
