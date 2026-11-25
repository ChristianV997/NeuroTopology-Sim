"""Malformed input rejection for the independent oracle."""

from __future__ import annotations

import pytest

from tools.batch2_chain_complex_audit.complex import (
    FiniteChainComplex,
    validate_orientation_signs,
)
from tools.batch2_chain_complex_audit.errors import (
    CellSpecError,
    DuplicateError,
    EndpointError,
    FaceSpecError,
    OrientationError,
)


def test_negative_edge_endpoint():
    with pytest.raises(EndpointError, match="negative"):
        FiniteChainComplex(n_vertices=2, edges=((-1, 0),))


def test_out_of_range_edge_endpoint():
    with pytest.raises(EndpointError, match="out-of-range"):
        FiniteChainComplex(n_vertices=2, edges=((0, 2),))


def test_self_loop_rejected():
    with pytest.raises(EndpointError, match="self-loop"):
        FiniteChainComplex(n_vertices=2, edges=((1, 1),))


def test_duplicate_edges_rejected():
    with pytest.raises(DuplicateError, match="duplicate edge"):
        FiniteChainComplex(n_vertices=3, edges=((0, 1), (1, 0)))


def test_negative_face_vertex():
    with pytest.raises(EndpointError, match="out of range"):
        FiniteChainComplex(
            n_vertices=3,
            edges=((0, 1), (1, 2), (2, 0)),
            faces=((-1, 0, 1),),
        )


def test_out_of_range_face_vertex():
    with pytest.raises(EndpointError, match="out of range"):
        FiniteChainComplex(
            n_vertices=3,
            edges=((0, 1), (1, 2), (2, 0)),
            faces=((0, 1, 3),),
        )


def test_repeated_vertices_in_face():
    with pytest.raises(FaceSpecError, match="repeated vertices"):
        FiniteChainComplex(
            n_vertices=3,
            edges=((0, 1), (1, 2), (2, 0)),
            faces=((0, 0, 1),),
        )


def test_duplicate_faces_rejected():
    with pytest.raises(DuplicateError, match="duplicate face"):
        FiniteChainComplex(
            n_vertices=3,
            edges=((0, 1), (1, 2), (2, 0)),
            faces=((0, 1, 2), (2, 0, 1)),
        )


def test_missing_face_edge():
    with pytest.raises(FaceSpecError, match="missing edge"):
        FiniteChainComplex(
            n_vertices=3,
            edges=((0, 1), (1, 2)),  # missing (2,0)
            faces=((0, 1, 2),),
        )


def test_invalid_orientation_signs():
    with pytest.raises(OrientationError):
        validate_orientation_signs([1, 0, -1])
    with pytest.raises(OrientationError):
        validate_orientation_signs([2])


def test_duplicate_faces_in_cell_via_repeated_vertices():
    with pytest.raises(CellSpecError, match="repeated vertices"):
        FiniteChainComplex(
            n_vertices=4,
            edges=(
                (0, 1), (0, 2), (0, 3),
                (1, 2), (1, 3), (2, 3),
            ),
            faces=(
                (0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3),
            ),
            cells=((0, 1, 2, 2),),
        )


def test_cell_missing_face():
    with pytest.raises(CellSpecError, match="missing face"):
        FiniteChainComplex(
            n_vertices=4,
            edges=(
                (0, 1), (0, 2), (0, 3),
                (1, 2), (1, 3), (2, 3),
            ),
            faces=(
                (0, 1, 2), (0, 1, 3), (0, 2, 3),
                # missing (1,2,3)
            ),
            cells=((0, 1, 2, 3),),
        )


def test_duplicate_cells_rejected():
    with pytest.raises(DuplicateError, match="duplicate cell"):
        FiniteChainComplex(
            n_vertices=4,
            edges=(
                (0, 1), (0, 2), (0, 3),
                (1, 2), (1, 3), (2, 3),
            ),
            faces=(
                (0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3),
            ),
            cells=((0, 1, 2, 3), (3, 2, 1, 0)),
        )


def test_out_of_range_cell_vertex():
    with pytest.raises(EndpointError, match="out of range"):
        FiniteChainComplex(
            n_vertices=4,
            edges=(
                (0, 1), (0, 2), (0, 3),
                (1, 2), (1, 3), (2, 3),
            ),
            faces=(
                (0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3),
            ),
            cells=((0, 1, 2, 4),),
        )
