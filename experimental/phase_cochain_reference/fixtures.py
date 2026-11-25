"""Hand-verifiable simplicial complex fixtures for testing and validation.

Includes:
1. single_triangle: 3 vertices, 3 edges, 1 triangle.
2. vortex_quad: 5 vertices (4 outer, 1 center), 4 triangles.
3. dipole_complex: Two separated triangles forming an exact dipole (q=+1, q=-1).
4. annulus_complex: Non-contractible 6-vertex ring (annulus) with b1=1,
   supporting non-trivial harmonic 1-forms.
"""

from __future__ import annotations

import numpy as np

from .complex import SimplicialComplex


def build_single_triangle_fixture() -> SimplicialComplex:
    """Minimal single triangle complex.

    Vertices:
        0: (0.0, 0.0)
        1: (1.0, 0.0)
        2: (0.5, sqrt(3)/2)
    Triangles: [(0, 1, 2)]
    """
    coords = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0],
        ],
        dtype=float,
    )
    triangles = [(0, 1, 2)]
    return SimplicialComplex.from_triangles(triangles, coordinates=coords, num_vertices=3)


def build_vortex_quad_fixture() -> SimplicialComplex:
    """Disk complex composed of 4 triangles surrounding a central vertex.

    Vertices:
        0: (1.0, 0.0)
        1: (0.0, 1.0)
        2: (-1.0, 0.0)
        3: (0.0, -1.0)
        4: (0.0, 0.0)  (center vertex)
    Triangles:
        t0: (0, 1, 4)
        t1: (1, 2, 4)
        t2: (2, 3, 4)
        t3: (0, 3, 4)
    """
    coords = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
            [0.0, -1.0],
            [0.0, 0.0],
        ],
        dtype=float,
    )
    triangles = [
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (0, 3, 4),
    ]
    return SimplicialComplex.from_triangles(triangles, coordinates=coords, num_vertices=5)


def build_dipole_complex_fixture(separation_distance: float = 4.0) -> SimplicialComplex:
    """Two separated planar triangles forming a neutral dipole pair.

    Triangle A (left, centered at x = -separation_distance/2):
        Vertices 0, 1, 2
    Triangle B (right, centered at x = +separation_distance/2):
        Vertices 3, 4, 5
    """
    half_d = separation_distance / 2.0
    h = np.sqrt(3.0) / 2.0
    coords = np.array(
        [
            # Left triangle
            [-half_d - 0.5, -h / 3.0],
            [-half_d + 0.5, -h / 3.0],
            [-half_d, 2.0 * h / 3.0],
            # Right triangle
            [half_d - 0.5, -h / 3.0],
            [half_d + 0.5, -h / 3.0],
            [half_d, 2.0 * h / 3.0],
        ],
        dtype=float,
    )
    triangles = [
        (0, 1, 2),
        (3, 4, 5),
    ]
    return SimplicialComplex.from_triangles(triangles, coordinates=coords, num_vertices=6)


def build_annulus_fixture() -> SimplicialComplex:
    """Non-contractible annulus complex with 1-dimensional homology b1=1.

    Vertices:
        0, 1, 2: Inner boundary ring (radius 1.0) at angles 0, 2pi/3, 4pi/3
        3, 4, 5: Outer boundary ring (radius 2.0) at angles 0, 2pi/3, 4pi/3

    Euler characteristic:
        V = 6, E = 12, F = 6 => chi = 6 - 12 + 6 = 0
        b0 = 1, b1 = 1, b2 = 0 => chi = b0 - b1 + b2 = 0.
    """
    r_in = 1.0
    r_out = 2.0
    angles = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])

    inner_coords = np.column_stack([r_in * np.cos(angles), r_in * np.sin(angles)])
    outer_coords = np.column_stack([r_out * np.cos(angles), r_out * np.sin(angles)])
    coords = np.vstack([inner_coords, outer_coords])

    # 6 triangles triangulating the cylindrical band between inner and outer rings
    triangles = [
        (0, 1, 3),
        (1, 3, 4),
        (1, 2, 4),
        (2, 4, 5),
        (0, 2, 5),
        (0, 3, 5),
    ]
    return SimplicialComplex.from_triangles(triangles, coordinates=coords, num_vertices=6)
