"""Boundary signs and ∂²=0 for synthetic complexes (independent oracle)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from tools.batch2_chain_complex_audit.complex import FiniteChainComplex, _matmul
from tools.batch2_chain_complex_audit.fixtures import (
    filled_tetrahedron,
    filled_triangle,
    open_triangular_prism,
    tetrahedron_surface,
    triangle_boundary,
    wedge_circle_and_sphere,
)


@pytest.mark.parametrize(
    "factory",
    [
        triangle_boundary,
        filled_triangle,
        tetrahedron_surface,
        filled_tetrahedron,
        open_triangular_prism,
        wedge_circle_and_sphere,
    ],
    ids=lambda f: f.__name__,
)
def test_boundary_compositions_exact_zero(factory):
    c = factory()
    checks = c.composition_zero()
    assert checks["d1_d2"] is True
    assert checks["d2_d3"] is True


def test_tetrahedron_boundary_1_signs():
    """∂1 column for edge (0,1) is e_1 - e_0."""
    c = filled_tetrahedron()
    d1 = c.boundary_1()
    # edges[0] = (0,1)
    col0 = [d1[r][0] for r in range(c.n_vertices)]
    assert col0 == [
        Fraction(-1),
        Fraction(1),
        Fraction(0),
        Fraction(0),
    ]


def test_filled_triangle_boundary_2_signed_cycle():
    """Face (0,1,2) hits edges (0,1),(1,2),(2,0) each once with consistent signs."""
    c = filled_triangle()
    d2 = c.boundary_2()
    col = [d2[r][0] for r in range(len(c.edges))]
    # Each edge appears once in absolute value
    assert sorted(abs(x) for x in col) == [Fraction(1), Fraction(1), Fraction(1)]
    # ∂1 ∂2 = 0 already covered; also sum of signed vertex incidences via ∂1@col = 0
    d1 = c.boundary_1()
    prod = _matmul(d1, d2)
    assert all(x == 0 for row in prod for x in row)


def test_tetrahedron_d3_four_faces_unit_rank():
    c = filled_tetrahedron()
    d3 = c.boundary_3()
    assert len(d3) == 4 and len(d3[0]) == 1
    col = [d3[r][0] for r in range(4)]
    assert sorted(abs(x) for x in col) == [Fraction(1)] * 4
    # Signs must make ∂2 ∂3 = 0
    assert c.composition_zero()["d2_d3"] is True


def test_open_prism_has_no_3_cells():
    c = open_triangular_prism()
    assert len(c.cells) == 0
    d3 = c.boundary_3()
    assert d3 == [] or all(len(row) == 0 for row in d3)
