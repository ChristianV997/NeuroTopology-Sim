"""Production-contract tests for planar triangulation (HOLD / SYNTHETIC_ONLY).

These are focused engineering checks for
``neurotopology_sim.experimental.geometry.planar_triangulation``.
Adversarial geometry tests are owned by Antigravity Agent A and are not edited here.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from neurotopology_sim.experimental.geometry.planar_triangulation import (
    SCHEMA_VERSION,
    ClaimLayer,
    DegeneracyPolicy,
    FailureKind,
    _orient_value,
    incircle,
    orient2d,
    triangulate_2d,
    validate_planar_mesh,
)


def _exact_signed_area(points, triangle):
    """Independent twice-area / 2 via Fraction orientation (recomputed, not prose)."""
    i, j, k = triangle
    a = (Fraction(points[i][0]), Fraction(points[i][1]))
    b = (Fraction(points[j][0]), Fraction(points[j][1]))
    c = (Fraction(points[k][0]), Fraction(points[k][1]))
    return _orient_value(a, b, c) / 2


def test_schema_and_hold_posture():
    result = triangulate_2d([(0, 0), (1, 0), (0, 1)])
    assert result.schema_version == SCHEMA_VERSION
    assert result.project_status == "HOLD"
    assert result.data_policy == "SYNTHETIC_ONLY"
    assert result.scientific_pass is False
    assert result.ok is True
    assert len(result.simplices) == 1


def test_layer_diagnostics_are_separate():
    result = triangulate_2d([(0, 0), (2, 0), (1, 1), (0.5, 0.2)])
    layers = {d.layer for d in result.diagnostics}
    assert "input_validation" in layers
    assert "abstract_chain" in layers
    assert "planar_hull_triangulation" in layers
    assert "delaunay_empty_circle" in layers
    assert result.ok


def test_abstract_chain_holds_on_valid_mesh():
    result = triangulate_2d([(0, 0), (3, 0), (0, 3), (1, 1)])
    chain = next(d for d in result.diagnostics if d.layer == "abstract_chain")
    assert chain.ok and chain.status == "holds"


def test_reject_duplicates_and_collinear():
    assert triangulate_2d([(0, 0), (1, 0), (0, 1), (0, 0)]).ok is False
    assert triangulate_2d([(0, 0), (1, 0), (2, 0)]).ok is False


def test_reject_nonfinite():
    assert triangulate_2d([(0, 0), (1, 0), (0, float("nan"))]).ok is False
    assert triangulate_2d([(0, 0), (1, 0), (0, float("inf"))]).ok is False


def test_square_cocircular_delaunay_reject_vs_lex():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    rejected = triangulate_2d(
        square, degeneracy_policy=DegeneracyPolicy.REJECT, require_delaunay=True
    )
    assert rejected.ok is False
    allowed = triangulate_2d(
        square,
        degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK,
        require_delaunay=True,
    )
    assert allowed.ok is True
    assert len(allowed.simplices) == 2
    ones = [e for e, c in allowed.edge_incidences.items() if c == 1]
    twos = [e for e, c in allowed.edge_incidences.items() if c == 2]
    assert len(ones) == 4
    assert len(twos) == 1


def test_cocircular_accepted_when_delaunay_not_required():
    """Planar validity must not be rejected solely for cocircularity without Delaunay."""
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    result = triangulate_2d(
        square, degeneracy_policy=DegeneracyPolicy.REJECT, require_delaunay=False
    )
    assert result.ok is True
    delaunay = next(d for d in result.diagnostics if d.layer == "delaunay_empty_circle")
    assert delaunay.status == "skipped"
    planar = next(d for d in result.diagnostics if d.layer == "planar_hull_triangulation")
    assert planar.ok is True


def test_hull_cycle_and_boundary_incidences():
    pts = [(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)]
    result = triangulate_2d(pts, degeneracy_policy="lexicographic_tiebreak")
    assert result.ok
    assert set(result.hull_cycle) == {0, 1, 2, 3}
    # Interior point must be covered
    covered = {v for t in result.simplices for v in t}
    assert covered == {0, 1, 2, 3, 4}


def test_supplied_overlapping_square_mesh_rejected():
    """Hermes / Revision-8-style adversarial *lead* (independently verified).

    Points [(0,0),(1,0),(1,1),(0,1)] with faces [(0,1,2),(0,1,3)] have crossing
    diagonals and overlapping interiors. Area/Euler counts can look fine; planar
    embedding checks must still reject. This does **not** claim triangulate_2d
    produced that mesh.
    """
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    faces = [(0, 1, 2), (0, 1, 3)]
    report = validate_planar_mesh(square, faces, check_delaunay=False)
    assert report.ok is False
    planar = next(d for d in report.diagnostics if d.layer == "planar_hull_triangulation")
    assert planar.ok is False
    assert any("crossing" in i or "overlap" in i or "boundary" in i for i in report.issues)


def test_valid_diagonal_square_accepted_by_validator():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    faces = [(0, 1, 2), (0, 2, 3)]
    report = validate_planar_mesh(
        square, faces, check_delaunay=True, degeneracy_policy="lexicographic_tiebreak"
    )
    assert report.ok is True


def test_orient_and_incircle_exact_signs():
    a = (Fraction(0), Fraction(0))
    b = (Fraction(1), Fraction(0))
    c = (Fraction(0), Fraction(1))
    assert orient2d(a, b, c) == 1
    assert orient2d(a, c, b) == -1
    assert orient2d(a, b, (Fraction(2), Fraction(0))) == 0
    assert incircle(a, b, c, (Fraction(1, 2), Fraction(1, 2))) == 1
    assert incircle(a, b, c, (Fraction(2), Fraction(2))) == -1


def test_result_to_dict_json_safe_keys():
    result = triangulate_2d([(0, 0), (1, 0), (0, 1)])
    payload = result.to_dict()
    assert payload["scientific_pass"] is False
    assert payload["ok"] is True
    assert "0,1" in payload["edge_incidences"] or len(payload["edge_incidences"]) >= 1


def test_no_coordinate_mutation():
    pts = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.25, 0.25]]
    snapshot = [row[:] for row in pts]
    triangulate_2d(pts, degeneracy_policy="lexicographic_tiebreak")
    assert pts == snapshot


def test_numpy_coords_supported():
    np = pytest.importorskip("numpy")
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=float)
    result = triangulate_2d(coords, require_delaunay=False)
    assert result.ok is True


@pytest.mark.parametrize(
    "bad_faces",
    [
        [(0, 1, True)],
        [(0, 1, False)],
        [(0, 1, -1)],
        [(0, 1, 99)],
        [(0, 1, 0.5)],
        [(0, 1, 1)],  # repeated vertex
    ],
)
def test_malformed_simplex_indices_fail_closed(bad_faces):
    pts = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    report = validate_planar_mesh(pts, bad_faces, check_delaunay=False)
    assert report.ok is False
    assert report.status == "rejected"
    assert report.failure_kind == FailureKind.MALFORMED_INPUT.value
    assert any(report.diagnostics) and report.diagnostics[0].layer == "input_validation"
    # Never IndexError / negative wrap; structured issues only.
    blob = " ".join(report.issues)
    assert "IndexError" not in blob


def test_counterexample_a_valid_mesh_and_omitted_crossing_leads():
    """Independently check Antigravity Counterexample A fixtures against production API."""
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.5, 0.5)]
    valid = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    assert validate_planar_mesh(points, valid, check_delaunay=False).ok is True
    # Crossing chords fixture A3-style: diagonals of the square without interior vertex use
    # is Counterexample B; with interior omitted, overlapping diagonals still fail planar.
    assert (
        validate_planar_mesh(
            points[:4], [(0, 1, 2), (0, 1, 3)], check_delaunay=False
        ).ok
        is False
    )


def test_user_counterexample_a_overlap_despite_positive_areas():
    """Square + interior (2,1): positive areas can coexist with overlap — must reject.

    Vertices: (0,0),(4,0),(4,4),(0,4),(2,1)
    Triangles: (0,1,2),(0,1,4),(1,2,4),(0,4,3)
    """
    points = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (2.0, 1.0)]
    faces = [(0, 1, 2), (0, 1, 4), (1, 2, 4), (0, 4, 3)]
    # Recompute areas independently (do not trust fixture prose).
    areas = [_exact_signed_area(points, t) for t in faces]
    assert areas == [Fraction(8), Fraction(2), Fraction(4), Fraction(4)]
    assert sum(areas) == Fraction(18)  # exceeds hull area 16 due to overlap
    assert all(a > 0 for a in areas)
    report = validate_planar_mesh(points, faces, check_delaunay=False)
    assert report.ok is False
    assert report.status == "rejected"
    assert report.failure_kind == FailureKind.INVALID_PLANAR_EMBEDDING.value
    diags = {d.layer: d for d in report.diagnostics}
    assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok is True
    assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok is False
    assert any("edge crossing" in i or "overlapping triangle" in i for i in report.issues)


def test_user_counterexample_b_full_validator_bypass():
    """Interior (3,1): area-sum==16 and D1@D0==0, yet crossings / non-hull boundary.

    Vertices: (0,0),(4,0),(4,4),(0,4),(3,1)
    Triangles: (0,1,3),(0,1,4),(1,2,4),(2,0,4)
    """
    points = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (3.0, 1.0)]
    faces = [(0, 1, 3), (0, 1, 4), (1, 2, 4), (2, 0, 4)]
    areas = [_exact_signed_area(points, t) for t in faces]
    assert areas == [Fraction(8), Fraction(2), Fraction(2), Fraction(4)]
    assert sum(areas) == Fraction(16)  # equals hull area yet still invalid
    # Independent crossing check: open segments (0,2) and (1,3) meet at (2,2).
    a0 = (Fraction(0), Fraction(0))
    a2 = (Fraction(4), Fraction(4))
    a1 = (Fraction(4), Fraction(0))
    a3 = (Fraction(0), Fraction(4))
    assert orient2d(a0, a2, a1) * orient2d(a0, a2, a3) < 0
    assert orient2d(a1, a3, a0) * orient2d(a1, a3, a2) < 0
    report = validate_planar_mesh(points, faces, check_delaunay=False)
    assert report.ok is False
    assert report.failure_kind == FailureKind.INVALID_PLANAR_EMBEDDING.value
    diags = {d.layer: d for d in report.diagnostics}
    assert diags[ClaimLayer.ABSTRACT_CHAIN.value].ok is True
    assert diags[ClaimLayer.ABSTRACT_CHAIN.value].detail == "D1 @ D0 == 0"
    assert diags[ClaimLayer.PLANAR_HULL_TRIANGULATION.value].ok is False
    assert any("boundary edges" in i for i in report.issues)
    assert any("edge crossing" in i for i in report.issues)
    assert any("overlapping triangle" in i for i in report.issues)


def test_oob_and_integral_float_indices_fail_closed_phrases():
    """Failing-contract probe: OOB/float indices before dereference; no IndexError."""
    pts = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    oob = validate_planar_mesh(pts, [(0, 1, 99)], check_delaunay=False)
    assert oob.ok is False
    assert oob.failure_kind == FailureKind.MALFORMED_INPUT.value
    blob = " ".join(oob.issues)
    assert "out-of-range index" in blob
    assert "out of range for n_points" in blob  # phrase shared with #421 adversarial suite
    # Integral-valued floats are still floats — reject before casting.
    integral_float = validate_planar_mesh(pts, [(0, 1, 2.0)], check_delaunay=False)
    assert integral_float.ok is False
    assert any("floating-point simplex index" in i for i in integral_float.issues)


def test_counterexample_b_rejected_as_supplied_mesh():
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    faces = [(0, 1, 2), (0, 1, 3)]
    report = validate_planar_mesh(points, faces, check_delaunay=False)
    assert report.ok is False
    assert report.failure_kind == FailureKind.INVALID_PLANAR_EMBEDDING.value
    planar = next(d for d in report.diagnostics if d.layer == "planar_hull_triangulation")
    assert planar.ok is False


def test_failure_kind_malformed_vs_delaunay():
    pts = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    bad_idx = validate_planar_mesh(pts, [(0, 1, 99)], check_delaunay=False)
    assert bad_idx.failure_kind == FailureKind.MALFORMED_INPUT.value
    assert any("out-of-range index" in i for i in bad_idx.issues)

    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    faces = [(0, 1, 2), (0, 2, 3)]
    delaunay_fail = validate_planar_mesh(
        square, faces, check_delaunay=True, degeneracy_policy="reject"
    )
    assert delaunay_fail.ok is False
    assert delaunay_fail.failure_kind == FailureKind.DELAUNAY_POLICY_FAILURE.value
    planar_ok = validate_planar_mesh(square, faces, check_delaunay=False)
    assert planar_ok.ok is True
    assert planar_ok.failure_kind == FailureKind.NONE.value


def test_near_collinear_and_edge_touch_degeneracy():
    # Near-collinear but exact-rational nonzero area: accepted as planar when valid.
    tri_ok = validate_planar_mesh(
        [(0.0, 0.0), (2.0, 0.0), (1.0, 1e-9)],
        [(0, 1, 2)],
        check_delaunay=False,
    )
    assert tri_ok.ok is True

    # Vertex 1 lies on open edge (0,2) of a coarse triangle — reject.
    touch = validate_planar_mesh(
        [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (1.0, 1.0)],
        [(0, 2, 3)],
        check_delaunay=False,
    )
    assert touch.ok is False
    assert touch.failure_kind == FailureKind.INVALID_PLANAR_EMBEDDING.value
    assert any("vertex-on-edge" in i or "uncovered" in i for i in touch.issues)


def test_non_delaunay_valid_planar_accepted_when_delaunay_disabled():
    points = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.5, 1.5)]
    faces = [(0, 1, 2), (0, 2, 3)]
    planar = validate_planar_mesh(points, faces, check_delaunay=False)
    assert planar.ok is True
    with_delaunay = validate_planar_mesh(
        points, faces, check_delaunay=True, degeneracy_policy="reject"
    )
    # Planar embedding holds; empty-circle fails independently.
    planar_layer = next(
        d for d in with_delaunay.diagnostics if d.layer == "planar_hull_triangulation"
    )
    delaunay_layer = next(
        d for d in with_delaunay.diagnostics if d.layer == "delaunay_empty_circle"
    )
    assert planar_layer.ok is True
    assert delaunay_layer.ok is False
    assert with_delaunay.ok is False
    assert with_delaunay.failure_kind == FailureKind.DELAUNAY_POLICY_FAILURE.value


def test_empty_mesh_with_fewer_than_three_points_rejected():
    """Empty simplices must not certify a planar hull triangulation for n<3."""
    for coords in ([], [(0.0, 0.0)], [(0.0, 0.0), (1.0, 0.0)]):
        report = validate_planar_mesh(coords, [], check_delaunay=False)
        assert report.ok is False
        assert report.status == "rejected"
        assert report.scientific_pass is False
        assert report.failure_kind == FailureKind.MALFORMED_INPUT.value
        assert any(
            "need at least 3" in issue or "duplicate coordinates" in issue
            for issue in report.issues
        )


def test_validate_planar_mesh_rejects_duplicate_coordinates():
    """Duplicates are invalid inputs for validate_planar_mesh, matching triangulate_2d."""
    coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, 0.0)]
    faces = [(0, 1, 2)]
    report = validate_planar_mesh(coords, faces, check_delaunay=False)
    assert report.ok is False
    assert report.status == "rejected"
    assert report.failure_kind == FailureKind.MALFORMED_INPUT.value
    assert any("duplicate coordinates" in issue for issue in report.issues)
    input_layer = next(d for d in report.diagnostics if d.layer == "input_validation")
    assert input_layer.ok is False
