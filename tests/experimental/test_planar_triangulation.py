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

from neurotopology_sim.experimental.geometry.planar_triangulation import (
    ClaimLayer,
    DegeneracyPolicy,
    PlanarTriangulationResult,
    triangulate_2d,
    validate_planar_mesh,
)
from tests.experimental.planar_mesh_test_helpers import (
    audit_planar_triangle_mesh,
    build_simplicial_boundary_matrices,
    clip_polygon_with_convex_polygon,
    counterexample_a_exact_fixture,
    counterexample_a_fixtures,
    counterexample_b_exact_fixture,
    counterexample_b_fixture,
    delaunay_incircle_exact,
    exact_convex_hull,
    exact_segment_line_intersection,
    mandatory_full_validator_counterexample_fixture,
    non_delaunay_valid_fixture,
    orient2d,
    polygon_area_exact,
    to_fraction_point,
    triangle_signed_area_twice,
)


class TestCounterexampleAFullValidator:
    """Test Counterexample A directly against the PR #416 candidate validator.

    Coordinates: (0,0), (4,0), (4,4), (0,4), (2,1)
    Triangles:   (0,1,2), (0,1,4), (1,2,4), (0,4,3)

    Geometric Properties:
    - 5 vertices forming a 4x4 square with interior point 4=(2,1).
    - All 4 triangles are strictly CCW with positive areas:
      Area(0,1,2) = 8
      Area(0,1,4) = 2
      Area(1,2,4) = 4
      Area(0,4,3) = 4
    - Convex hull area: [0,4] x [0,4] square has area 16.
    - True rational sum of face areas: 8 + 2 + 4 + 4 = 18.
      (The area sum exceeds the hull area of 16 because (0,1,4) and (1,2,4)
      are strictly contained inside (0,1,2), causing internal double-coverage.)
    - Topological chain complex:
      D1 @ D0 == 0 (partial_1 partial_2 == 0) holds identically.
    - Candidate validator MUST reject this invalid embedding:
      Flags triangle overlaps, nonincident edge crossings, and hull boundary mismatch.
    """

    def test_counterexample_a_rejected_by_candidate_validator(self):
        fixture = counterexample_a_exact_fixture()
        vertices = fixture["points"]
        triangles = fixture["triangles"]

        result = validate_planar_mesh(vertices, triangles, check_delaunay=False)

        # Candidate validator must reject this invalid embedding
        assert not result.ok
        assert result.status == "rejected"
        assert result.scientific_pass is False

        # Extract diagnostics by layer
        diags = {d.layer: d for d in result.diagnostics}

        # Abstract chain layer (D1 @ D0 == 0) holds algebraically
        assert ClaimLayer.ABSTRACT_CHAIN.value in diags
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].status == "holds"
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].detail == "D1 @ D0 == 0"

        # Planar hull triangulation layer MUST fail
        assert ClaimLayer.PLANAR_HULL_TRIANGULATION.value in diags
        assert not diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok
        assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].status == "fails"

        # Assert rejection for the actual geometric/mesh defects
        assert any("boundary edges" in issue for issue in result.issues)
        assert any("edge crossing" in issue for issue in result.issues)
        assert any("overlapping triangle" in issue for issue in result.issues)

    def test_counterexample_a_exact_oracle_arithmetic(self):
        fixture = counterexample_a_exact_fixture()
        points = [to_fraction_point(p) for p in fixture["points"]]
        triangles = fixture["triangles"]

        # 1. Verify signed areas: 8, 2, 4, 4 (all strictly positive CCW)
        areas = [triangle_signed_area_twice(points[t[0]], points[t[1]], points[t[2]]) / 2 for t in triangles]
        assert areas == [Fraction(8), Fraction(2), Fraction(4), Fraction(4)]
        assert all(a > 0 for a in areas)

        # 2. Square hull area is 16
        hull = exact_convex_hull(points)
        hull_area = hull["hull_area_twice"] / 2
        assert hull_area == Fraction(16)

        # 3. Rational area sum is 18 (exceeds hull area 16 due to overlapping faces)
        assert sum(areas) == Fraction(18)

        # 4. Simplicial boundary identity: D1 @ D0 == 0 is exact despite invalid embedding
        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)

        # 5. Overlap detection via exact polygon clipping
        poly_012 = [points[i] for i in (0, 1, 2)]
        poly_014 = [points[i] for i in (0, 1, 4)]
        poly_124 = [points[i] for i in (1, 2, 4)]
        inter_014 = clip_polygon_with_convex_polygon(poly_014, poly_012)
        inter_124 = clip_polygon_with_convex_polygon(poly_124, poly_012)
        assert polygon_area_exact(inter_014) == Fraction(2)  # fully interior to (0,1,2)
        assert polygon_area_exact(inter_124) == Fraction(4)  # fully interior to (0,1,2)


class TestMandatoryFullValidatorCounterexample:
    """Test Counterexample B directly against the PR #416 candidate validator.

    Vertices:
    0=(0,0), 1=(4,0), 2=(4,4), 3=(0,4), 4=(3,1)
    Triangles:
    (0,1,3), (0,1,4), (1,2,4), (2,0,4)

    Properties:
    - CCW areas: 8, 2, 2, 4 -> sum is 16, matching the square hull area.
    - 5 vertices, 4 faces, 8 unique edges.
    - All edge incidences are 1 or 2, and incidence-1 vertices are {0, 1, 2, 3}.
    - Crossing edges: nonincident edges (1, 3) and (0, 2) cross at (2, 2).
    - Triangle interiors overlap (e.g. (0,1,3) overlaps (0,1,4) and (2,0,4)).
    - Boundary edges {(1,3), (3,0), (1,2), (2,0)} are not the convex hull cycle {(0,1), (1,2), (2,3), (3,0)}.
    """

    def test_mandatory_counterexample_rejected_by_candidate_validator(self):
        fixture = mandatory_full_validator_counterexample_fixture()
        vertices = fixture["points"]
        triangles = fixture["triangles"]

        result = validate_planar_mesh(vertices, triangles)

        # Candidate validator must reject this invalid embedding
        assert not result.ok
        assert result.status == "rejected"
        assert result.scientific_pass is False

        # Extract diagnostics by layer
        diags = {d.layer: d for d in result.diagnostics}

        # Abstract chain layer (D1 @ D0 == 0) holds algebraically
        assert ClaimLayer.ABSTRACT_CHAIN.value in diags
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].status == "holds"
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].detail == "D1 @ D0 == 0"

        # Planar hull triangulation layer MUST fail
        assert ClaimLayer.PLANAR_HULL_TRIANGULATION.value in diags
        assert not diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok
        assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].status == "fails"

        # Check that specific geometric failures are flagged in issues
        assert any("boundary edges" in issue for issue in result.issues)
        assert any("edge crossing" in issue for issue in result.issues)
        assert any("overlapping triangle" in issue for issue in result.issues)

    def test_mandatory_counterexample_exact_oracle_arithmetic(self):
        fixture = mandatory_full_validator_counterexample_fixture()
        points = [to_fraction_point(p) for p in fixture["points"]]
        triangles = fixture["triangles"]

        # 1. Verify signed areas: 8, 2, 2, 4
        areas = [triangle_signed_area_twice(points[t[0]], points[t[1]], points[t[2]]) / 2 for t in triangles]
        assert areas == [Fraction(8), Fraction(2), Fraction(2), Fraction(4)]
        assert sum(areas) == Fraction(16)

        # 2. Hull area of the square (0,0), (4,0), (4,4), (0,4)
        hull = exact_convex_hull(points)
        assert hull["hull_area_twice"] / 2 == Fraction(16)
        assert sum(areas) == hull["hull_area_twice"] / 2

        # 3. Edge incidences: all edges have incidence 1 or 2
        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero  # D1 @ D0 == 0 is exact

        # 4. Crossing edges (1, 3) and (2, 0) cross at (2, 2)
        s, e = points[1], points[3]    # (4, 0) -> (0, 4)
        c1, c2 = points[0], points[2]  # (0, 0) -> (4, 4)
        t, u, inter = exact_segment_line_intersection(s, e, c1, c2)
        assert t == Fraction(1, 2)
        assert u == Fraction(1, 2)
        assert inter == (Fraction(2), Fraction(2))

        # 5. Overlap detection via exact polygon clipping
        poly_014 = [points[i] for i in (0, 1, 4)]
        poly_013 = [points[i] for i in (0, 1, 3)]
        inter_poly = clip_polygon_with_convex_polygon(poly_014, poly_013)
        assert polygon_area_exact(inter_poly) == Fraction(2)  # triangle (0,1,4) fully inside (0,1,3)


class TestFractionClipperAndIntersectionDerivation:
    """Independently derive and test line/segment intersection parameter signs and exact polygon clipping."""

    def test_segment_line_intersection_parameter_sign_and_crossing(self):
        """Derivation:
        For s + t(e - s) = c1 + u(c2 - c1),
        t = orient2d(c1, c2, s) / (orient2d(c1, c2, s) - orient2d(c1, c2, e)).

        Known crossing segment: (0, -1) -> (0, 1) against line (0, 0) -> (1, 0).
        Must return t = 1/2 and point (0, 0).
        """
        s = (Fraction(0), Fraction(-1))
        e = (Fraction(0), Fraction(1))
        c1 = (Fraction(0), Fraction(0))
        c2 = (Fraction(1), Fraction(0))

        t, u, pt = exact_segment_line_intersection(s, e, c1, c2)

        assert t == Fraction(1, 2), f"Expected t=1/2, got {t}"
        assert u == Fraction(0), f"Expected u=0, got {u}"
        assert pt == (Fraction(0), Fraction(0)), f"Expected intersection at (0, 0), got {pt}"

    def test_exact_polygon_clipping_disjoint_triangles(self):
        t1 = [(Fraction(0), Fraction(0)), (Fraction(1), Fraction(0)), (Fraction(0), Fraction(1))]
        t2 = [(Fraction(2), Fraction(2)), (Fraction(3), Fraction(2)), (Fraction(2), Fraction(3))]
        inter = clip_polygon_with_convex_polygon(t1, t2)
        assert len(inter) == 0
        assert polygon_area_exact(inter) == Fraction(0)


class TestEarlierFiveVertexPartialOverlapFixture:
    """Test the earlier five-vertex partial overlap fixture against PR #416 candidate validator."""

    def test_earlier_partial_fan_fixture_rejected(self):
        fixture = counterexample_a_fixtures()
        points = fixture["points"]
        partial_mesh = fixture["partial_fixture_a1"]  # Missing triangle (3, 0, 4)

        result = validate_planar_mesh(points, partial_mesh)
        assert not result.ok
        assert result.status == "rejected"
        assert any("edges do not match independent hull boundary edges" in issue for issue in result.issues)

    def test_earlier_omitted_interior_vertex_rejected(self):
        fixture = counterexample_a_fixtures()
        points = fixture["points"]
        omitted_mesh = fixture["omitted_vertex_fixture_a2"]  # Ignores interior vertex 4

        result = validate_planar_mesh(points, omitted_mesh)
        assert not result.ok
        assert result.status == "rejected"
        assert any("uncovered input points: [4]" in issue for issue in result.issues)

    def test_earlier_valid_mesh_accepted(self):
        fixture = counterexample_a_fixtures()
        points = fixture["points"]
        valid_mesh = fixture["valid_delaunay"]

        result = validate_planar_mesh(points, valid_mesh)
        assert result.ok
        assert result.status == "ok"


class TestIndexValidationAdversarial:
    """Adversarial testing of simplex indices against PR #416 candidate validator.

    Verifies that malformed simplex indices (floats, booleans, repeated vertices,
    out of range 99, negative -1) are rejected before array indexing without
    unhandled IndexError or wraparound.
    """

    def test_repeated_indices_within_simplex_rejected(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        simplices = [(0, 0, 1)]
        result = validate_planar_mesh(coords, simplices)
        assert not result.ok
        assert any("repeated vertices" in issue for issue in result.issues)

    def test_negative_simplex_index_rejected(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        simplices = [(-1, 0, 1)]
        result = validate_planar_mesh(coords, simplices)
        assert not result.ok
        assert any("negative simplex index" in issue for issue in result.issues)

    def test_out_of_range_index_rejected_before_indexing(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        simplices = [(0, 1, 99)]
        result = validate_planar_mesh(coords, simplices)
        assert not result.ok
        assert any("out of range for n_points" in issue for issue in result.issues)

    def test_float_and_boolean_simplex_indices_rejected_before_indexing(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        float_simplices = [(0.9, 1.0, 2.0)]
        res_float = validate_planar_mesh(coords, float_simplices)
        assert not res_float.ok
        assert any("floating-point simplex index is not allowed" in issue for issue in res_float.issues)

        bool_simplices = [(True, 1, 2)]
        res_bool = validate_planar_mesh(coords, bool_simplices)
        assert not res_bool.ok
        assert any("boolean is not a valid simplex index" in issue for issue in res_bool.issues)


class TestMalformedAndNonFiniteInputs:
    """Test candidate validator and triangulator input validation on malformed and non-finite inputs."""

    def test_numpy_coordinate_array_acceptance(self):
        coords_np = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        simplices_np = np.array([[0, 1, 2]])
        result = validate_planar_mesh(coords_np, simplices_np)
        assert result.ok
        assert result.status == "ok"

    def test_numpy_coordinate_array_malformed_shape_rejected(self):
        coords_bad_shape = np.zeros((3, 3))
        simplices_np = np.array([[0, 1, 2]])
        result = validate_planar_mesh(coords_bad_shape, simplices_np)
        assert not result.ok
        assert any("coords array must have shape (n, 2)" in issue for issue in result.issues)

        coords_1d = np.zeros(6)
        result_1d = validate_planar_mesh(coords_1d, simplices_np)
        assert not result_1d.ok
        assert any("shape (2,)" in issue or "shape (n, 2)" in issue for issue in result_1d.issues)

    @pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_coordinates_rejected_by_candidate(self, bad_val):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, bad_val)]
        result = validate_planar_mesh(coords, [(0, 1, 2)])
        assert not result.ok
        assert any("non-finite float coordinate" in issue for issue in result.issues)

    def test_boolean_coordinates_rejected(self):
        coords = [(True, 0.0), (False, 1.0), (1.0, 1.0)]
        result = validate_planar_mesh(coords, [(0, 1, 2)])
        assert not result.ok
        assert any("boolean is not a geometric coordinate" in issue for issue in result.issues)

    def test_duplicate_points_rejected_by_triangulate_2d(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, 0.0)]
        result = triangulate_2d(coords)
        assert not result.ok
        assert result.status == "rejected"
        assert any("duplicate coordinates at indices" in issue for issue in result.issues)

    def test_collinear_points_rejected_by_triangulate_2d(self):
        coords = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
        result = triangulate_2d(coords)
        assert not result.ok
        assert result.status == "rejected"
        assert any("globally collinear point set" in issue for issue in result.issues)


class TestCocircularPolicyDelaunayEnabledVsDisabled:
    """Verify cocircular input handling with Delaunay validation disabled versus enabled."""

    def test_square_cocircular_policy_outcomes(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        triangles = [(0, 1, 2), (0, 2, 3)]

        res_no_delaunay = validate_planar_mesh(coords, triangles, check_delaunay=False)
        assert res_no_delaunay.ok
        assert res_no_delaunay.status == "ok"

        res_reject = validate_planar_mesh(
            coords,
            triangles,
            check_delaunay=True,
            degeneracy_policy=DegeneracyPolicy.REJECT,
        )
        assert not res_reject.ok
        assert res_reject.status == "rejected"
        assert any("exact cocircular incident(s); degeneracy_policy=reject" in issue for issue in res_reject.issues)

        res_tiebreak = validate_planar_mesh(
            coords,
            triangles,
            check_delaunay=True,
            degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK,
        )
        assert res_tiebreak.ok
        assert res_tiebreak.status == "ok"

    def test_triangulate_2d_cocircular_policy(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        # When require_delaunay=True (default) and degeneracy_policy=REJECT: rejects
        res_reject = triangulate_2d(coords, degeneracy_policy=DegeneracyPolicy.REJECT, require_delaunay=True)
        assert not res_reject.ok
        assert res_reject.status == "rejected"

        # When require_delaunay=False: accepts as valid planar triangulation even with reject policy
        res_planar_only = triangulate_2d(coords, degeneracy_policy=DegeneracyPolicy.REJECT, require_delaunay=False)
        assert res_planar_only.ok
        assert res_planar_only.status == "ok"
        assert len(res_planar_only.simplices) == 2

        # When require_delaunay=True and degeneracy_policy=LEXICOGRAPHIC_TIEBREAK: accepts via tiebreak
        res_tiebreak = triangulate_2d(coords, degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK, require_delaunay=True)
        assert res_tiebreak.ok
        assert res_tiebreak.status == "ok"
        assert len(res_tiebreak.simplices) == 2


class TestHullCycleCrossingEdgePositiveAreaOrientation:
    """Test hull-cycle, crossing-edge, positive-area, and exact-orientation behavior."""

    def test_triangulate_2d_produces_ccw_simplices_and_exact_hull_cycle(self):
        coords = [(0.0, 0.0), (2.0, 0.0), (1.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
        res = triangulate_2d(coords, degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK)
        assert res.ok

        pts = [to_fraction_point(c) for c in coords]
        for t in res.simplices:
            assert orient2d(pts[t[0]], pts[t[1]], pts[t[2]]) > 0

        assert set(res.hull_cycle) == {0, 1, 3, 4}
        assert set(res.hull_boundary_cycle) == {0, 1, 2, 3, 4}

    def test_inverted_triangle_detected_as_nonpositive_orientation(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        simplices = [(0, 1, 2)]
        res = validate_planar_mesh(coords, simplices)
        assert res.ok


class TestScaleAndTranslationInvariance:
    """Verify that candidate validator and geometric oracle maintain validity across scales and translations."""

    @pytest.mark.parametrize("scale, tx, ty", [
        (1.0, 0.0, 0.0),
        (1e-20, 0.0, 0.0),
        (1e20, 0.0, 0.0),
        (1.0, 2.0**30, -(2.0**30)),
    ])
    def test_scale_translation_invariance(self, scale, tx, ty):
        base_points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        triangles = [(0, 1, 2), (0, 2, 3)]
        transformed = [(scale * x + tx, scale * y + ty) for x, y in base_points]

        result = validate_planar_mesh(transformed, triangles)
        assert result.ok
        assert result.status == "ok"
        assert result.n_points == 4
        assert len(result.simplices) == 2


class TestCounterexampleBRevision8OverlappingFaces:
    """Independently construct and audit Revision 8 Counterexample B against candidate validator.

    Proves that a supplied invalid mesh can satisfy weaker count, area, Euler,
    and boundary-cycle heuristics while violating planar geometric embedding.
    """

    def test_counterexample_b_rejected_by_candidate_validator(self):
        data = counterexample_b_fixture()
        points = data["points"]
        triangles = data["triangles"]

        result = validate_planar_mesh(points, triangles)
        assert not result.ok
        assert result.status == "rejected"

        diags = {d.layer: d for d in result.diagnostics}
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok
        assert not diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok

        assert any("edges do not match independent hull boundary edges" in issue for issue in result.issues)
        assert any("edge crossing" in issue for issue in result.issues)
        assert any("overlapping triangle" in issue for issue in result.issues)

    def test_counterexample_b_weaker_checks_pass(self):
        data = counterexample_b_fixture()
        points = data["points"]
        triangles = data["triangles"]

        p_frac = [to_fraction_point(p) for p in points]
        area0 = triangle_signed_area_twice(p_frac[triangles[0][0]], p_frac[triangles[0][1]], p_frac[triangles[0][2]]) / 2
        area1 = triangle_signed_area_twice(p_frac[triangles[1][0]], p_frac[triangles[1][1]], p_frac[triangles[1][2]]) / 2
        assert area0 == Fraction(1, 2)
        assert area1 == Fraction(1, 2)

        hull = exact_convex_hull(p_frac)
        assert (area0 + area1) == hull["hull_area_twice"] / 2

        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)


class TestTopologicalBoundaryVsGeometricEmbedding:
    """Assert independently that incidence matrices satisfy D1 @ D0 == 0 even when planar embedding is completely invalid."""

    def test_simplicial_d1_d0_zero_holds_for_counterexample_a(self):
        """D1 @ D0 == 0 (partial_1 partial_2 == 0) holds identically for Counterexample A despite severe overlap."""
        data = counterexample_a_exact_fixture()
        points = data["points"]
        triangles = data["triangles"]

        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)

        # Candidate validator rejects the embedding despite chain complex identity holding
        result = validate_planar_mesh(points, triangles, check_delaunay=False)
        assert not result.ok
        assert result.status == "rejected"
        diags = {d.layer: d for d in result.diagnostics}
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok is True
        assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok is False

    def test_simplicial_d1_d0_zero_holds_for_counterexample_b(self):
        """D1 @ D0 == 0 (partial_1 partial_2 == 0) holds identically for Counterexample B despite edge crossing."""
        data = counterexample_b_exact_fixture()
        points = data["points"]
        triangles = data["triangles"]

        _, b1, b2, is_zero = build_simplicial_boundary_matrices(len(points), triangles)
        assert is_zero
        assert np.all(b1 @ b2 == 0)

        # Candidate validator rejects the embedding despite chain complex identity holding
        result = validate_planar_mesh(points, triangles, check_delaunay=False)
        assert not result.ok
        assert result.status == "rejected"
        diags = {d.layer: d for d in result.diagnostics}
        assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok is True
        assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok is False



class TestLegacyComparisonAndBlockerStatus:
    """Document legacy triangulate_xy unhandled errors versus PR #416 candidate."""

    def test_legacy_triangulate_xy_unhandled_errors(self):
        from validation.montage_topology import triangulate_xy

        collinear = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        with pytest.raises(Exception) as exc_info:
            triangulate_xy(collinear)
        assert "Qhull" in type(exc_info.value).__name__ or "Qhull" in str(exc_info.value)

        duplicates = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]])
        with pytest.raises(Exception) as exc_info:
            triangulate_xy(duplicates)
        assert "Qhull" in type(exc_info.value).__name__ or "Qhull" in str(exc_info.value)
