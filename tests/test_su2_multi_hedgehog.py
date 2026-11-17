"""Synthetic contract tests for pointwise products of SU(2) hedgehog fields."""

import numpy as np
import pytest

from field_theory.su2 import multi_hedgehog
from field_theory.su2.nearest_neighbor import compute_nearest_neighbor_diagnostics


def test_product_matches_ordered_matrix_multiplication_and_isorotation():
    shape = (17, 17, 17)
    centers = ((-2.4, 0.0, 0.0), (2.4, 0.0, 0.0))
    radii = (1.4, 1.4)
    angle = np.pi / 3.0
    rotation = (np.cos(angle / 2.0), 0.0, 0.0, np.sin(angle / 2.0))

    left = multi_hedgehog(
        shape, centers=(centers[0],), radii=(radii[0],), spacing=(0.5, 0.5, 0.5)
    )
    right_rotated = multi_hedgehog(
        shape,
        centers=(centers[1],),
        radii=(radii[1],),
        spacing=(0.5, 0.5, 0.5),
        isorotations=(rotation,),
    )
    combined = multi_hedgehog(
        shape,
        centers=centers,
        radii=radii,
        spacing=(0.5, 0.5, 0.5),
        isorotations=((1.0, 0.0, 0.0, 0.0), rotation),
    )

    expected = left.matrices() @ right_rotated.matrices()
    np.testing.assert_allclose(combined.matrices(), expected, atol=2e-14, rtol=2e-14)
    assert combined.spacing == (0.5, 0.5, 0.5)
    assert combined.length_unit == "dimensionless"
    assert combined.boundary == "fixed_vacuum"


def test_isorotation_matches_direct_conjugation_and_is_a_proper_rotation():
    shape = (9, 9, 9)
    center = ((0.0, 0.0, 0.0),)
    radius = (1.5,)
    angle = np.pi / 2.0
    rotation = np.asarray(((np.cos(angle / 2.0), 0.0, 0.0, np.sin(angle / 2.0)),))
    base = multi_hedgehog(shape, centers=center, radii=radius, spacing=(0.5,) * 3)
    turned = multi_hedgehog(
        shape, centers=center, radii=radius, spacing=(0.5,) * 3, isorotations=rotation
    )

    g0, g1, g2, g3 = rotation[0]
    group_matrix = np.asarray(
        [[g0 + 1j * g3, g2 + 1j * g1], [-g2 + 1j * g1, g0 - 1j * g3]]
    )
    direct = group_matrix @ base.matrices() @ group_matrix.conj().T
    np.testing.assert_allclose(turned.matrices(), direct, atol=2e-14, rtol=2e-14)

    pauli = np.asarray(
        [
            [[0, 1], [1, 0]],
            [[0, -1j], [1j, 0]],
            [[1, 0], [0, -1]],
        ],
        dtype=np.complex128,
    )
    induced = np.empty((3, 3), dtype=np.float64)
    for source_axis in range(3):
        image = group_matrix @ (1j * pauli[source_axis]) @ group_matrix.conj().T
        for target_axis in range(3):
            induced[target_axis, source_axis] = (
                np.trace(pauli[target_axis] @ image).imag / 2.0
            )
    np.testing.assert_allclose(induced.T @ induced, np.eye(3), atol=2e-14)
    assert np.linalg.det(induced) == pytest.approx(1.0, abs=2e-14)
    np.testing.assert_allclose(
        induced,
        (
            (np.cos(angle), np.sin(angle), 0.0),
            (-np.sin(angle), np.cos(angle), 0.0),
            (0.0, 0.0, 1.0),
        ),
        atol=2e-14,
    )


def test_product_is_deterministic_unit_valued_and_has_exact_vacuum_faces():
    generic_rotation = np.asarray(
        (0.07449520394891201, -0.20598548088715687, -0.16276489009038167, -0.9620436771821552)
    )
    generic_rotation /= np.linalg.norm(generic_rotation)
    kwargs = dict(
        centers=((-2.5, 0.0, 0.0), (2.5, 0.0, 0.0)),
        radii=(1.5, 1.5),
        spacing=(0.5, 0.75, 1.0),
        isorotations=((1.0, 0.0, 0.0, 0.0), tuple(generic_rotation)),
        length_unit="mm",
    )
    first = multi_hedgehog((19, 15, 11), **kwargs)
    repeated = multi_hedgehog((19, 15, 11), **kwargs)
    np.testing.assert_array_equal(first.components, repeated.components)
    np.testing.assert_allclose(np.sum(first.components**2, axis=-1), 1.0, atol=2e-14)
    for axis in range(3):
        for index in (0, -1):
            face = np.take(first.components, index, axis=axis)
            np.testing.assert_array_equal(
                face, np.broadcast_to((1.0, 0.0, 0.0, 0.0), face.shape)
            )
    assert first.length_unit == "mm"
    assert not first.components.flags.writeable


def test_well_separated_charge_approaches_additive_continuum_value_under_refinement():
    # Each factor's continuum degree is -1 in this orientation. The sampled
    # lattice estimate need not be integer or exactly additive at finite h.
    errors_from_additive_value = []
    for step, size in ((1.0, 17), (0.5, 33), (0.25, 65)):
        kwargs = dict(spacing=(step,) * 3, length_unit="dimensionless")
        left = multi_hedgehog((size,) * 3, centers=((-4.0, 0.0, 0.0),), radii=(3.0,), **kwargs)
        right = multi_hedgehog((size,) * 3, centers=((4.0, 0.0, 0.0),), radii=(3.0,), **kwargs)
        combined = multi_hedgehog(
            (size,) * 3,
            centers=((-4.0, 0.0, 0.0), (4.0, 0.0, 0.0)),
            radii=(3.0, 3.0),
            **kwargs,
        )
        q_left = compute_nearest_neighbor_diagnostics(left).topological_charge
        q_right = compute_nearest_neighbor_diagnostics(right).topological_charge
        q_combined = compute_nearest_neighbor_diagnostics(combined).topological_charge
        assert np.isfinite(q_left) and np.isfinite(q_right)
        errors_from_additive_value.append(abs(q_combined + 2.0))
        assert np.isfinite(q_combined)
    assert errors_from_additive_value[2] < errors_from_additive_value[1]
    assert errors_from_additive_value[1] < errors_from_additive_value[0]
    assert errors_from_additive_value[2] < 0.25


def test_overlaps_are_rejected_by_default_and_available_explicitly():
    args = ((13, 13, 13),)
    kwargs = dict(centers=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), radii=(2.0, 2.0))
    with pytest.raises(ValueError, match="overlap"):
        multi_hedgehog(*args, **kwargs)
    field = multi_hedgehog(*args, **kwargs, allow_overlaps=True)
    assert field.components.shape == (13, 13, 13, 4)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"centers": (), "radii": ()},
        {"centers": ((0.0, 0.0),), "radii": (1.0,)},
        {"centers": ((0.0, 0.0, np.nan),), "radii": (1.0,)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (0.0,)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (np.inf,)},
        {"centers": ((True, 0.0, 0.0),), "radii": (1.0,)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (True,)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (1.0,), "isorotations": ((1.0, 0.0, 0.0),)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (1.0,), "isorotations": ((2.0, 0.0, 0.0, 0.0),)},
        {"centers": ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0)), "radii": (1.0,)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (1.0,), "isorotations": ((1.0, 0.0, np.nan, 0.0),)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (1.0,), "isorotations": ((True, 0.0, 0.0, 0.0),)},
        {"centers": ((0.0, 0.0, 0.0),), "radii": (1.0,), "allow_overlaps": 1},
        {"centers": ((4.0, 0.0, 0.0),), "radii": (2.0,)},
    ],
)
def test_rejects_malformed_nonfinite_or_out_of_grid_inputs(kwargs):
    with pytest.raises(ValueError):
        multi_hedgehog((13, 13, 13), **kwargs)

