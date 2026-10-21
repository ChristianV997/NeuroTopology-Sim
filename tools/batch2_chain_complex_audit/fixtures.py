"""Small synthetic complexes for the independent oracle (SYNTHETIC_ONLY)."""

from __future__ import annotations

from tools.batch2_chain_complex_audit.complex import FiniteChainComplex


def empty_complex() -> FiniteChainComplex:
    """No cells of any dimension → Betti (0,0,0,0)."""
    return FiniteChainComplex(n_vertices=0, edges=())


def two_isolated_vertices() -> FiniteChainComplex:
    """Disconnected 0-skeleton → β0 = 2."""
    return FiniteChainComplex(n_vertices=2, edges=())


def single_edge() -> FiniteChainComplex:
    """Interval → Betti (1,0,0,0)."""
    return FiniteChainComplex(n_vertices=2, edges=((0, 1),))


def triangle_boundary() -> FiniteChainComplex:
    """Hollow triangle (S^1) → Betti (1,1,0,0)."""
    return FiniteChainComplex(
        n_vertices=3,
        edges=((0, 1), (1, 2), (2, 0)),
        faces=(),
    )


def filled_triangle() -> FiniteChainComplex:
    """Disk (filled 2-simplex) → Betti (1,0,0,0)."""
    return FiniteChainComplex(
        n_vertices=3,
        edges=((0, 1), (1, 2), (2, 0)),
        faces=((0, 1, 2),),
    )


def tetrahedron_surface() -> FiniteChainComplex:
    """Hollow tetrahedron (S^2) → Betti (1,0,1,0). Closed surface with H2."""
    # Vertices 0,1,2,3
    edges = (
        (0, 1), (0, 2), (0, 3),
        (1, 2), (1, 3), (2, 3),
    )
    faces = (
        (0, 1, 2),
        (0, 1, 3),
        (0, 2, 3),
        (1, 2, 3),
    )
    return FiniteChainComplex(n_vertices=4, edges=edges, faces=faces)


def filled_tetrahedron() -> FiniteChainComplex:
    """Solid tetrahedron (3-ball) → Betti (1,0,0,0)."""
    base = tetrahedron_surface()
    return FiniteChainComplex(
        n_vertices=base.n_vertices,
        edges=base.edges,
        faces=base.faces,
        cells=((0, 1, 2, 3),),
    )


def open_triangular_prism() -> FiniteChainComplex:
    """Open triangular prism lateral surface (no caps).

    Homotopy-equivalent to a circle. Proposal fixture claims Betti tuple
    (1,1,0) for (β0,β1,β2). Oracle returns (β0,β1,β2,β3)=(1,1,0,0).

    Vertices: bottom triangle 0,1,2; top triangle 3,4,5.
    Edges: 3 bottom + 3 top + 3 vertical.
    Faces: 3 lateral quads each split into 2 triangles = 6 faces.
    No 3-cells (open / hollow lateral only).
    """
    edges = (
        # bottom
        (0, 1), (1, 2), (2, 0),
        # top
        (3, 4), (4, 5), (5, 3),
        # vertical
        (0, 3), (1, 4), (2, 5),
        # lateral diagonals (for triangulation)
        (0, 4), (1, 5), (2, 3),
    )
    faces = (
        # wall 0-1-4-3
        (0, 1, 4), (0, 4, 3),
        # wall 1-2-5-4
        (1, 2, 5), (1, 5, 4),
        # wall 2-0-3-5
        (2, 0, 3), (2, 3, 5),
    )
    return FiniteChainComplex(n_vertices=6, edges=edges, faces=faces)


def disconnected_two_edges() -> FiniteChainComplex:
    """Two disjoint edges → β0=2, β1=0."""
    return FiniteChainComplex(
        n_vertices=4,
        edges=((0, 1), (2, 3)),
    )


def wedge_circle_and_sphere() -> FiniteChainComplex:
    """Disconnected union of a hollow triangle and a hollow tetrahedron.

    Gives nontrivial H1 and H2 simultaneously without a large triangulation:
      β0 = 2 (two components), β1 = 1, β2 = 1, β3 = 0.
    Relabel tetrahedron vertices to 3..6 so complexes do not share vertices.
    """
    # Triangle on verts 0,1,2
    # Tet surface on verts 3,4,5,6
    edges = (
        (0, 1), (1, 2), (2, 0),
        (3, 4), (3, 5), (3, 6),
        (4, 5), (4, 6), (5, 6),
    )
    faces = (
        (3, 4, 5),
        (3, 4, 6),
        (3, 5, 6),
        (4, 5, 6),
    )
    return FiniteChainComplex(n_vertices=7, edges=edges, faces=faces)


def closed_surface_sphere() -> FiniteChainComplex:
    """Alias: closed surface = tetrahedron boundary (S^2)."""
    return tetrahedron_surface()
