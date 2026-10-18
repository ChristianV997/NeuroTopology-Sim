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
    DegeneracyPolicy,
    incircle,
    orient2d,
    triangulate_2d,
    validate_planar_mesh,
)


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


def test_square_cocircular_reject_vs_lex():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    rejected = triangulate_2d(square, degeneracy_policy=DegeneracyPolicy.REJECT)
    assert rejected.ok is False
    allowed = triangulate_2d(
        square, degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK
    )
    assert allowed.ok is True
    assert len(allowed.simplices) == 2
    # Boundary edges have incidence 1; diagonal incidence 2
    ones = [e for e, c in allowed.edge_incidences.items() if c == 1]
    twos = [e for e, c in allowed.edge_incidences.items() if c == 2]
    assert len(ones) == 4
    assert len(twos) == 1


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
