"""Independent adversarial test suite for planar triangulation and embedding validity.

PROJECT POSTURE: HOLD / SYNTHETIC_ONLY
Geometry tests establish only properties of a planar sensor-coordinate mesh.
They do not establish cortical topology or scientific validity.
Gemini Revision 8 is research input, not ground truth.
"""

from __future__ import annotations

import math
from fractions import Fraction
import numpy as np
import pytest

from tests.experimental.planar_mesh_test_helpers import (
    audit_planar_triangle_mesh,
    build_simplicial_boundary_matrices,
    counterexample_a_fixtures,
    counterexample_b_fixture,
    delaunay_incircle_exact,
    exact_convex_hull,
    non_delaunay_valid_fixture,
    orient2d,
    segments_intersect,
    to_fraction_point,
    triangle_signed_area_twice,
)


class TestInvalidInputs:
    """Verify fail-closed behavior on invalid, duplicate, and degenerate input point sets."""

    @pytest.mark.parametrize("fewer_points", [
        [],
        [(0.0, 0.0)],
        [(0.0, 0.0), (1.0, 0.0)],
    ])
    def test_fewer_than_three_points_rejected(self, fewer_points):
        report = audit_planar_triangle_mesh(fewer_points, [])
        assert not report["geometry_checks_all_satisfied"]
        assert not report["checks"]["nondegenerate_convex_hull"]
        assert any("at least 3 points" in issue for issue in report["issues"])

    @pytest.mark.parametrize("non_finite_point", [
        (float("nan"), 0.0),
        (0.0, float("nan")),
        (float("inf"), 1.0),
        (1.0, float("-inf")),
    ])
    def test_non_finite_coordinates_rejected(self, non_finite_point):
        points = [(0.0, 0.0), (1.0, 0.0), non_finite_point]
        report = audit_planar_triangle_mesh(points, [(0, 1, 2)])
        assert not report["geometry_checks_all_satisfied"]
        assert not report["checks"]["coordinates_finite"]
        assert any("coordinates_finite failed" in issue for issue in report["issues"])

    def test_duplicate_coincident_points_rejected(self):
        # 4 points with index 0 and 3 exactly coincident
        points = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, 0.0)]
        triangles = [(0, 1, 2)]
        report = audit_planar_triangle_mesh(points, triangles)
        assert not report["geometry_checks_all_satisfied"]
        assert not report["checks"]["coordinates_unique"]
        assert any("Duplicate points detected" in issue for issue in report["issues"])

    @pytest.mark.parametrize("collinear_points", [
        [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
        [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)],
        [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 5.0)],
    ])
    def test_collinear_points_rejected(self, collinear_points):
        # 3 or more points on a line have hull area 0 and cannot form a 2D triangulation
        triangles = [(0, 1, 2)]
        report = audit_planar_triangle_mesh(collinear_points, triangles)
        assert not report["geometry_checks_all_satisfied"]
        assert not report["checks"]["nondegenerate_convex_hull"]
        assert any("Convex hull is degenerate" in issue for issue in report["issues"])

    def test_near_degenerate_collinear_geometry(self):
        # Nearly collinear points: y-offset is 1e-15 (close to machine epsilon)
        points = [(0.0, 0.0), (1.0, 0.0), (0.5, 1e-15)]
        report = audit_planar_triangle_mesh(points, [(0, 1, 2)])
        # Exact arithmetic records exact non-zero area without floating underflow
        assert report["checks"]["nonzero_triangle_areas"]
        assert report["checks"]["area_partition_identity"]
        assert report["geometry_checks_all_satisfied"]

        # Even smaller height: 1e-30
        points_extreme = [(Fraction(0), Fraction(0)), (Fraction(1), Fraction(0)), (Fraction(1, 2), Fraction(1, 10**30))]
        report_extreme = audit_planar_triangle_mesh(points_extreme, [(0, 1, 2)])
        assert report_extreme["checks"]["nonzero_triangle_areas"]
        assert report_extreme["geometry_checks_all_satisfied"]


class TestCocircularPolicyAndJitterLimits:
    """Verify cocircular tie-policy requirements and limits of finite float jitter."""

    def test_exact_cocircular_quadrilateral_determinant_is_zero(self):
        # 4 vertices of unit square on circle of radius sqrt(2)/2
        a = (Fraction(0), Fraction(0))
        b = (Fraction(1), Fraction(0))
        c = (Fraction(1), Fraction(1))
        d = (Fraction(0), Fraction(1))

        # Incircle test of d relative to triangle abc
        inc = delaunay_incircle_exact(a, b, c, d)
        assert inc == Fraction(0), f"Expected exact zero incircle determinant for square vertices, got {inc}"

        # Both diagonal splits (0-2 vs 1-3) are valid planar triangulations
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        tri_diag_02 = [(0, 1, 2), (0, 2, 3)]
        tri_diag_13 = [(0, 1, 3), (1, 2, 3)]

        rep_02 = audit_planar_triangle_mesh(points, tri_diag_02)
        rep_13 = audit_planar_triangle_mesh(points, tri_diag_13)

        assert rep_02["geometry_checks_all_satisfied"]
        assert rep_13["geometry_checks_all_satisfied"]
        # Both are neutral with respect to Delaunay condition (no vertex strictly inside circumcircle)
        assert rep_02["is_delaunay"]
        assert rep_13["is_delaunay"]

    def test_finite_float_jitter_is_erased_under_large_translation(self):
        """Proves that finite float jitter (e.g. 1e-10) is NOT equivalent to Simulation of Simplicity (SoS).

        In IEEE 754 float64, at magnitude 2^30 (~1.07e9), the unit in the last place (ULP)
        is 2^30 * 2^-52 = 2^-22 ~= 2.38e-7.
        Adding 1e-10 to 2^30 rounds back to 2^30 exactly, wiping out the jitter entirely!
        """
        base_x = float(2**30)
        jitter = 1e-10

        # In standard floating point, addition of jitter is completely absorbed
        jittered_x = base_x + jitter
        assert jittered_x == base_x
        assert (jittered_x - base_x) == 0.0

        # Exact SoS uses symbolic perturbation, which is independent of coordinate magnitude


class TestCounterexampleASquarePlusInteriorVertex:
    """Independently construct and audit Counterexample A (square + interior vertex)."""

    def test_counterexample_a_exact_arithmetic_and_valid_mesh(self):
        data = counterexample_a_fixtures()
        points = data["points"]
        valid_triangles = data["valid_delaunay"]

        report = audit_planar_triangle_mesh(points, valid_triangles)
        assert report["geometry_checks_all_satisfied"]
        assert report["counts"]["point_count"] == 5
        assert report["counts"]["extreme_hull_vertex_count"] == 4
        assert report["counts"]["triangle_count"] == 4
        assert report["counts"]["edge_count"] == 8  # 4 boundary + 4 internal
        assert report["metrics"]["convex_hull_area_twice"] == "2"  # 2 * Area(1.0) = 2
        assert report["metrics"]["sum_triangle_area_twice"] == "2"

    def test_counterexample_a_partial_fixture_a1_rejected(self):
        """Partial fixture A1: 3 of 4 triangles supplied, missing triangle (3, 0, 4)."""
        data = counterexample_a_fixtures()
        points = data["points"]
        partial_triangles = data["partial_fixture_a1"]

        report = audit_planar_triangle_mesh(points, partial_triangles)
        assert not report["geometry_checks_all_satisfied"]

        # Signed areas of supplied triangles are all positive (0.25 each)
        assert report["checks"]["nonzero_triangle_areas"]
        assert report["checks"]["consistent_triangle_orientation"]

        # But sum of face areas = 0.75 != 1.0 (hull area)
        assert not report["checks"]["area_partition_identity"]
        assert report["metrics"]["sum_triangle_area_twice"] == "3/2"
        assert report["metrics"]["convex_hull_area_twice"] == "2"

        # Boundary incidence-1 edges include internal chords (0, 4) and (3, 4), and miss hull edge (0, 3)
        assert not report["checks"]["boundary_matches_independent_hull"]

        # Euler counts fail: E=7 != 8, F=3 != 4
        assert not report["checks"]["euler_counts_match"]

    def test_counterexample_a_omitted_interior_vertex_a2_rejected(self):
        """Omitted vertex fixture A2: square triangulated with (0,1,2) and (0,2,3), ignoring interior vertex 4."""
        data = counterexample_a_fixtures()
        points = data["points"]
        omitted_triangles = data["omitted_vertex_fixture_a2"]

        report = audit_planar_triangle_mesh(points, omitted_triangles)
        assert not report["geometry_checks_all_satisfied"]

        # Vertex 4 is completely uncovered / unused
        assert not report["checks"]["all_input_points_covered"]
        assert any("Uncovered vertex indices: [4]" in issue for issue in report["issues"])

        # Euler formula for V=5 points fails
        assert not report["checks"]["euler_counts_match"]


class TestCounterexampleBRevision8OverlappingFaces:
    """Independently construct and audit Revision 8 Counterexample B.

    Proves that a supplied invalid mesh can satisfy weaker count, area, Euler,
    and boundary-cycle heuristics while violating planar geometric embedding.
    """

    def test_counterexample_b_weaker_checks_pass(self):
        data = counterexample_b_fixture()
        points = data["points"]
        triangles = data["triangles"]

        # 1. Exact signed areas are both strictly positive (+0.5)
        p_frac = [to_fraction_point(p) for p in points]
        area0 = triangle_signed_area_twice(p_frac[triangles[0][0]], p_frac[triangles[0][1]], p_frac[triangles[0][2]])
        area1 = triangle_signed_area_twice(p_frac[triangles[1][0]], p_frac[triangles[1][1]], p_frac[triangles[1][2]])
        assert area0 == Fraction(1)  # twice area = 1 -> area = 0.5
        assert area1 == Fraction(1)
        assert area0 > 0 and area1 > 0

        # 2. Area sum equals convex hull area: 0.5 + 0.5 = 1.0
        hull = exact_convex_hull(p_frac)
        assert (area0 + area1) == hull["hull_area_twice"]

        # 3. Combinatorial Euler count matches: V=4, B=4 -> E=5, F=2
        # E = 3(4) - 3 - 4 = 5; F = 2(4) - 2 - 4 = 2
        report = audit_planar_triangle_mesh(points, triangles)
        assert report["checks"]["euler_counts_match"]
        assert report["checks"]["area_partition_identity"]
        assert report["checks"]["all_input_points_covered"]
        assert report["checks"]["nonzero_triangle_areas"]
        assert report["checks"]["consistent_triangle_orientation"]
        assert report["checks"]["edge_incidence_valid"]
        assert report["checks"]["edge_connected"]

        # 4. Inferred boundary vertices {0, 1, 2, 3} angularly sort around centroid to convex hull cycle
        inferred_boundary_vertices = sorted({v for e in report["hull"]["observed_boundary_edges"] for v in e})
        assert inferred_boundary_vertices == [0, 1, 2, 3]

        centroid_x = sum(p[0] for p in points) / len(points)
        centroid_y = sum(p[1] for p in points) / len(points)
        angular_sorted = sorted(
            inferred_boundary_vertices,
            key=lambda idx: math.atan2(points[idx][1] - centroid_y, points[idx][0] - centroid_x),
        )
        # Shoelace formula on angular sorted vertices gives exact hull area
        shoelace_twice = sum(
            points[angular_sorted[i]][0] * points[angular_sorted[(i + 1) % 4]][1]
            - points[angular_sorted[(i + 1) % 4]][0] * points[angular_sorted[i]][1]
            for i in range(4)
        )
        assert shoelace_twice == 2.0  # twice area = 2 -> area = 1.0

        # 5. Boundary matrix identity B1 @ B2 == 0 holds identically!
        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)

    def test_counterexample_b_embedding_checks_fail(self):
        """Verifies that the independent geometric oracle correctly rejects Counterexample B."""
        data = counterexample_b_fixture()
        points = data["points"]
        triangles = data["triangles"]

        report = audit_planar_triangle_mesh(points, triangles)
        assert not report["geometry_checks_all_satisfied"]

        # 1. Crossing edges detected: diagonal (0, 2) crosses diagonal (1, 3) at (0.5, 0.5)
        assert not report["checks"]["noncrossing_edges"]
        assert any("Improper edge crossings detected" in issue for issue in report["issues"])

        # 2. Triangle overlap detected: triangles (0, 1, 2) and (0, 1, 3) overlap in their interior
        assert not report["checks"]["nonoverlapping_triangles"]
        assert any("Improper triangle overlaps detected" in issue for issue in report["issues"])

        # 3. Boundary mismatch: incidence-1 edges are {(1, 2), (2, 0), (1, 3), (3, 0)},
        # which does NOT match the convex hull edges {(0, 1), (1, 2), (2, 3), (3, 0)}
        assert not report["checks"]["boundary_matches_independent_hull"]
        assert any("boundary edges do not match independent convex hull cycle" in issue for issue in report["issues"])


class TestTopologicalBoundaryVsGeometricEmbedding:
    """Assert independently that incidence matrices can satisfy D1 @ D0 == 0 even when embedding is invalid."""

    def test_simplicial_d1_d0_zero_holds_for_invalid_complexes(self):
        """B1 @ B2 == 0 (partial_1 partial_2 == 0) is an algebraic identity that holds for ANY simplicial complex."""
        data = counterexample_b_fixture()
        points = data["points"]
        triangles = data["triangles"]

        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)

        # Confirm that geometric embedding is nevertheless completely invalid
        report = audit_planar_triangle_mesh(points, triangles)
        assert not report["geometry_checks_all_satisfied"]

    def test_boundary_incidence_one_edges_must_equal_ordered_convex_hull_cycle(self):
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        p_frac = [to_fraction_point(p) for p in points]
        hull = exact_convex_hull(p_frac)
        expected_boundary = hull["expected_boundary_edges"]
        # Expected boundary edges for unit square: (0, 1), (1, 2), (2, 3), (0, 3)
        assert expected_boundary == [(0, 1), (0, 3), (1, 2), (2, 3)]

        # Valid triangulation incidence-1 edges match expected boundary
        valid_triangles = [(0, 1, 2), (0, 2, 3)]
        rep_valid = audit_planar_triangle_mesh(points, valid_triangles)
        assert rep_valid["checks"]["boundary_matches_independent_hull"]
        assert rep_valid["hull"]["observed_boundary_edges"] == [list(e) for e in expected_boundary]


class TestDelaunayConditionIndependence:
    """Assert independently that empty circumcircle is an independent Delaunay condition, not an embedding requirement."""

    def test_valid_planar_triangulation_can_fail_empty_circumcircle(self):
        data = non_delaunay_valid_fixture()
        points = data["points"]
        triangles = data["triangles"]

        report = audit_planar_triangle_mesh(points, triangles)

        # Planar embedding axioms are 100% satisfied:
        assert report["geometry_checks_all_satisfied"]
        assert report["checks"]["noncrossing_edges"]
        assert report["checks"]["nonoverlapping_triangles"]
        assert report["checks"]["boundary_matches_independent_hull"]
        assert report["checks"]["area_partition_identity"]
        assert report["checks"]["euler_counts_match"]

        # But empty circumcircle fails (Non-Delaunay)!
        assert not report["is_delaunay"]
        assert report["metrics"]["delaunay_violations_count"] > 0


class TestScaleAndTranslationInvariance:
    """Verify that geometric validity is strictly invariant under scaling and translation."""

    @pytest.mark.parametrize("scale, tx, ty", [
        (1.0, 0.0, 0.0),
        (1e-20, 0.0, 0.0),
        (1e20, 0.0, 0.0),
        (1.0, 2.0**30, -(2.0**30)),
        (1e-10, 1e6, -1e6),
    ])
    def test_scale_translation_invariance_on_square_triangulation(self, scale, tx, ty):
        base_points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        triangles = [(0, 1, 2), (0, 2, 3)]

        transformed = [(scale * x + tx, scale * y + ty) for x, y in base_points]
        report = audit_planar_triangle_mesh(transformed, triangles)

        assert report["geometry_checks_all_satisfied"]
        assert report["counts"]["triangle_count"] == 2
        assert report["counts"]["edge_count"] == 5
        assert report["counts"]["extreme_hull_vertex_count"] == 4


class TestCandidateProductionTriangulatorAudit:
    """Audit existing candidate production triangulator in validation/montage_topology.py.

    Documents unhandled exceptions and absence of dedicated production planar embedding validator.
    """

    def test_legacy_triangulate_xy_unhandled_collinear_crash(self):
        """Legacy triangulate_xy calls scipy.spatial.Delaunay directly, raising unhandled QhullError on collinear points."""
        from validation.montage_topology import triangulate_xy

        collinear = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        with pytest.raises(Exception) as exc_info:
            triangulate_xy(collinear)
        # scipy raises QhullError (derived from RuntimeError)
        assert "Qhull" in type(exc_info.value).__name__ or "Qhull" in str(exc_info.value)

    def test_legacy_triangulate_xy_unhandled_duplicate_crash(self):
        """Legacy triangulate_xy crashes on duplicate coincident points."""
        from validation.montage_topology import triangulate_xy

        duplicates = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]])
        with pytest.raises(Exception) as exc_info:
            triangulate_xy(duplicates)
        assert "Qhull" in type(exc_info.value).__name__ or "Qhull" in str(exc_info.value)

    def test_legacy_triangulate_xy_does_not_audit_supplied_meshes(self):
        """triangulate_xy only generates simplices from scipy.spatial.Delaunay; it does not validate supplied meshes."""
        from validation.montage_topology import triangulate_xy

        # Passes cocircular points to Qhull without tie-break policy disclosure
        square = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        tri = triangulate_xy(square)
        assert tri.shape == (2, 3)
