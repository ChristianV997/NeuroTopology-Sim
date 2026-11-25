"""Signed 3-cell / face-bundle cancellation vs absolute 'appears twice'."""

from __future__ import annotations

import pytest

from tools.batch2_chain_complex_audit.complex import (
    absolute_edge_counts,
    assert_signed_cell_boundary_cancels,
    signed_edge_boundary_of_faces,
)
from tools.batch2_chain_complex_audit.errors import CellSpecError


def test_absolute_twice_is_insufficient_when_signs_agree():
    """Two faces can cover every edge twice in absolute count yet fail to cancel.

    Classic counterexample: both faces use the shared edge with the same sign.
    Absolute counts look like a closed surface link; signed sum does not vanish.
    """
    # 3 edges forming a triangle; two identical oriented face boundaries
    # Face A: +e0 +e1 +e2
    # Face B: +e0 +e1 +e2  (same orientation — NOT opposite)
    faces = [
        [(0, +1), (1, +1), (2, +1)],
        [(0, +1), (1, +1), (2, +1)],
    ]
    abs_counts = absolute_edge_counts(faces, n_edges=3)
    assert abs_counts == [2, 2, 2]  # "each active edge appears twice" — PASSES
    signed = signed_edge_boundary_of_faces(faces, n_edges=3)
    assert signed == [2, 2, 2]  # does NOT cancel
    with pytest.raises(CellSpecError, match="does not cancel"):
        assert_signed_cell_boundary_cancels(faces, n_edges=3)


def test_opposite_orientations_cancel_signed():
    faces = [
        [(0, +1), (1, +1), (2, +1)],
        [(0, -1), (1, -1), (2, -1)],
    ]
    assert absolute_edge_counts(faces, n_edges=3) == [2, 2, 2]
    assert signed_edge_boundary_of_faces(faces, n_edges=3) == [0, 0, 0]
    assert_signed_cell_boundary_cancels(faces, n_edges=3)  # no raise


def test_tetrahedron_style_four_faces_signed_edge_shadow():
    """Boundary of a tet projected to edges: each edge appears in 2 faces, opposite.

    Tet [0,1,2,3] edges 0..5:
      e0=(0,1), e1=(0,2), e2=(0,3), e3=(1,2), e4=(1,3), e5=(2,3)
    Faces with induced edge signs (relative to stored orientation src→dst):
      f012: +e0 +e3 -e1
      f013: +e0 +e4 -e2
      f023: +e1 +e5 -e2
      f123: +e3 +e5 -e4
    Summing all four (which is NOT ∂ of a single oriented 2-chain identity,
    but the edge-shadow of ∂∂ of the 3-cell after composing) — here we only
    check a consistently opposite pairing on a closed band of two faces.
    """
    # Closed band around edge e0 using faces f012 and opposite of a duplicate
    # that reverses e0: minimal unit for the audit claim.
    band = [
        [(0, +1), (3, +1), (1, -1)],  # f012
        [(0, -1), (3, -1), (1, +1)],  # opposite copy
    ]
    assert absolute_edge_counts(band, n_edges=6)[:4] == [2, 2, 0, 2]
    assert_signed_cell_boundary_cancels(band, n_edges=6)


def test_partial_absolute_coverage_still_fails_signed():
    """One edge covered twice with agreeing signs; others once — both checks fail."""
    faces = [
        [(0, +1), (1, +1)],
        [(0, +1), (2, +1)],
    ]
    assert absolute_edge_counts(faces, n_edges=3) == [2, 1, 1]
    signed = signed_edge_boundary_of_faces(faces, n_edges=3)
    assert signed[0] == 2
    with pytest.raises(CellSpecError):
        assert_signed_cell_boundary_cancels(faces, n_edges=3)
