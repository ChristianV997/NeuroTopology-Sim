"""Tiny oriented disk / cycle-complex fixtures with independently derived incidence.

Boundary conditions are stated explicitly. This is not a Delaunay/mesh-validity audit.
"""
from __future__ import annotations

from tools.hodge_decomposition_audit.incidence import (
    OrientedComplex,
    canonicalize_triangle,
    edges_from_triangles,
)
from tools.hodge_decomposition_audit.schema import BoundaryClass


def disk_single_triangle() -> OrientedComplex:
    """Contractible oriented disk: one face, boundary is the three outer edges.

    Expectation (topology, not a numerical claim about every omega):
    first Betti number b1 = 0 for this filled triangle, so the harmonic
    subspace for 1-forms is trivial in the continuous DEC analogy. The audit
    still measures the numerical harmonic residual rather than assuming zero.
    """
    triangles = (canonicalize_triangle(0, 1, 2),)
    edges = edges_from_triangles(triangles)
    return OrientedComplex(
        name="disk_single_triangle",
        boundary_class=BoundaryClass.DISK_WITH_BOUNDARY.value,
        num_vertices=3,
        edges=edges,
        triangles=triangles,
        notes=(
            "Oriented disk with boundary cycle (0,1)-(1,2)-(2,0). "
            "Filled by one triangle; not a closed surface."
        ),
    )


def disk_quad_fan() -> OrientedComplex:
    """Larger contractible disk: four triangles around a center vertex (boundary = outer cycle)."""
    # Center = 4; outer = 0,1,2,3
    triangles = tuple(
        canonicalize_triangle(*t)
        for t in (
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (0, 3, 4),
        )
    )
    edges = edges_from_triangles(triangles)
    return OrientedComplex(
        name="disk_quad_fan",
        boundary_class=BoundaryClass.DISK_WITH_BOUNDARY.value,
        num_vertices=5,
        edges=edges,
        triangles=triangles,
        notes="Contractible disk with boundary the outer 4-cycle; center vertex 4.",
    )


def closed_cycle_complex() -> OrientedComplex:
    """Pure 1-complex cycle: 3 vertices, 3 edges, zero triangles.

    This is a closed complex at the 1-skeleton level (no boundary edges of
    2-simplices because there are no 2-simplices). Circulatory 1-forms lie in
    the harmonic subspace; the audit must not assume harmonic energy is zero.
    """
    edges = ((0, 1), (1, 2), (0, 2))
    return OrientedComplex(
        name="closed_cycle_complex",
        boundary_class=BoundaryClass.CLOSED_CYCLE_COMPLEX.value,
        num_vertices=3,
        edges=edges,
        triangles=(),
        notes=(
            "Closed 1-complex C3 with no 2-simplices. "
            "Harmonic subspace is nontrivial; coexact component is identically zero."
        ),
    )


def annulus_like_band() -> OrientedComplex:
    """Annulus-like band with nontrivial 1-homology (inner + outer rings).

    Independently listed triangles (not imported from PR #385). Used only to
    show that harmonic content need not vanish when b1 > 0.
    """
    triangles = tuple(
        canonicalize_triangle(*t)
        for t in (
            (0, 1, 3),
            (1, 3, 4),
            (1, 2, 4),
            (2, 4, 5),
            (0, 2, 5),
            (0, 3, 5),
        )
    )
    edges = edges_from_triangles(triangles)
    return OrientedComplex(
        name="annulus_like_band",
        boundary_class=BoundaryClass.ANNULUS_LIKE.value,
        num_vertices=6,
        edges=edges,
        triangles=triangles,
        notes=(
            "Annulus-like triangulation of a cylindrical band (inner 0-1-2, outer 3-4-5). "
            "Expect nontrivial harmonic 1-forms; do not assume harmonic == 0."
        ),
    )


def disconnected_two_triangles() -> OrientedComplex:
    """Two disjoint oriented triangles (disconnected 2-complex).

    Gauge kernel of L0 grows with the number of connected components.
    Used to exercise reconstruction/orthogonality without assuming a single
    connected mesh. Independently listed; not imported from PR #385.
    """
    triangles = tuple(
        canonicalize_triangle(*t) for t in ((0, 1, 2), (3, 4, 5))
    )
    edges = edges_from_triangles(triangles)
    return OrientedComplex(
        name="disconnected_two_triangles",
        boundary_class=BoundaryClass.DISK_WITH_BOUNDARY.value,
        num_vertices=6,
        edges=edges,
        triangles=triangles,
        notes=(
            "Two disjoint filled triangles. Disconnected; harmonic residual "
            "still measured numerically; do not assume single-component gauge."
        ),
    )


ALL_FIXTURES = (
    disk_single_triangle,
    disk_quad_fan,
    closed_cycle_complex,
    annulus_like_band,
    disconnected_two_triangles,
)
