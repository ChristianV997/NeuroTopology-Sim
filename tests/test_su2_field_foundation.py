"""Synthetic contract tests for the exploratory static SU(2) field."""
import numpy as np
import pytest

from field_theory.su2 import SU2GridField, fixed_axis, hedgehog, vacuum


def test_vacuum_and_matrix_invariants():
    field = vacuum((5, 6, 7), spacing=(0.5, 1, 2))
    matrix = field.matrices()
    np.testing.assert_allclose(matrix @ matrix.conj().swapaxes(-1, -2), np.broadcast_to(np.eye(2), matrix.shape))
    np.testing.assert_allclose(np.linalg.det(matrix), 1)
    assert field.spacing == (0.5, 1.0, 2.0)
    assert not field.components.flags.writeable


def test_fixed_axis_lift_and_input_copy():
    theta = np.linspace(-np.pi, np.pi, 125).reshape(5, 5, 5)
    field = fixed_axis(theta, axis=(1, 2, 3))
    np.testing.assert_allclose(field.components[..., 0], np.cos(theta))
    np.testing.assert_allclose(np.sum(field.components**2, axis=-1), 1, atol=1e-14)
    before = field.components.copy()
    theta[:] = 0
    np.testing.assert_array_equal(field.components, before)
    matrix = field.matrices()
    np.testing.assert_allclose(matrix @ matrix.conj().swapaxes(-1, -2), np.broadcast_to(np.eye(2), matrix.shape), atol=1e-14)
    np.testing.assert_allclose(np.linalg.det(matrix), 1, atol=1e-14)


@pytest.mark.parametrize("shape", [(17, 17, 17), (16, 18, 20)])
def test_hedgehog_is_unit_and_has_vacuum_boundary(shape):
    field = hedgehog(shape, radius=5, spacing=(1, 1, 1))
    n = field.components
    np.testing.assert_allclose(np.sum(n**2, axis=-1), 1, atol=1e-14)
    for axis in range(3):
        for index in (0, -1):
            face = np.take(n, index, axis=axis)
            np.testing.assert_allclose(face, np.broadcast_to([1, 0, 0, 0], face.shape), atol=1e-14)
    assert np.min(n[..., 0]) < 0


@pytest.mark.parametrize("radius", [0, -1, 8, np.nan, np.inf])
def test_hedgehog_rejects_invalid_radius(radius):
    with pytest.raises(ValueError):
        hedgehog((17, 17, 17), radius=radius)


def test_rejects_malformed_fields():
    with pytest.raises(ValueError):
        SU2GridField(np.zeros((3, 3, 3, 4)))
    with pytest.raises(ValueError):
        fixed_axis(np.zeros((3, 3, 3)), axis=(0, 0, 0))
    with pytest.raises(ValueError):
        fixed_axis(np.full((3, 3, 3), np.nan))
    with pytest.raises(ValueError):
        vacuum((3, 3, 3), spacing=(1, 0, 1))
    with pytest.raises(ValueError):
        vacuum((3, 3, 3), boundary="unknown")

