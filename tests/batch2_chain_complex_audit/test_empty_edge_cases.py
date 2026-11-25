"""Empty-cell and dimension-edge Betti / boundary formulas."""

from __future__ import annotations

from tools.batch2_chain_complex_audit.complex import FiniteChainComplex
from tools.batch2_chain_complex_audit.fixtures import (
    empty_complex,
    single_edge,
    two_isolated_vertices,
)


def test_empty_complex_betti_and_compositions():
    c = empty_complex()
    assert c.betti() == (0, 0, 0, 0)
    assert c.composition_zero() == {"d1_d2": True, "d2_d3": True}
    assert c.ranks() == {
        "rank_d1": 0,
        "rank_d2": 0,
        "rank_d3": 0,
        "n0": 0,
        "n1": 0,
        "n2": 0,
        "n3": 0,
    }


def test_vertices_only_no_edges():
    c = two_isolated_vertices()
    assert c.boundary_1() == [[], []] or c.boundary_1() == [
        [] for _ in range(2)
    ]
    # n_edges = 0 → boundary_1 is n0 x 0
    d1 = c.boundary_1()
    assert len(d1) == 2 and all(len(row) == 0 for row in d1)
    assert c.betti() == (2, 0, 0, 0)


def test_graph_without_faces_beta1():
    """Cycle graph C4: β0=1, β1=1, β2=0, β3=0."""
    c = FiniteChainComplex(
        n_vertices=4,
        edges=((0, 1), (1, 2), (2, 3), (3, 0)),
    )
    assert c.betti() == (1, 1, 0, 0)
    assert c.composition_zero()["d1_d2"] is True


def test_single_edge_interval():
    c = single_edge()
    assert c.betti() == (1, 0, 0, 0)
    assert c.ranks()["rank_d1"] == 1
