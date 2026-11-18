import numpy as np
import pytest

from field_theory.su2.hyperbolicity import (
    analyze_uniform_geodesic_transverse_symbol,
)


@pytest.mark.parametrize(
    "speed, expected_margin, expected_status",
    [
        (0.4, 0.36, "real_for_uniform_geodesic_transverse_sector"),
        (0.5, 0.0, "threshold_for_uniform_geodesic_transverse_sector"),
        (0.6, -0.44, "nonreal_for_uniform_geodesic_transverse_sector"),
    ],
)
def test_uniform_geodesic_transverse_principal_symbol(speed, expected_margin, expected_status):
    result = analyze_uniform_geodesic_transverse_symbol(
        np.array([1.0, 0.0, 0.0, 0.0]),
        np.array([0.0, speed, 0.0, 0.0]),
        f_pi=1.0,
        e=1.0,
    )

    assert result.scope == "homogeneous_geodesic_transverse_principal_symbol_only"
    assert result.status == expected_status
    assert result.transverse_speed_squared == pytest.approx(expected_margin)
    assert result.normalized_time_gradient == pytest.approx(2.0 * speed)
    assert result.classification_tolerance > 0.0
    assert result.local_time_kinetic_hessian_min_eigenvalue == pytest.approx(0.25)
    assert result.full_system_hyperbolicity_status == "not_assessed"

    if expected_margin > 0.0:
        root = np.sqrt(expected_margin)
        assert result.transverse_principal_roots_per_unit_wavenumber == pytest.approx(
            (-root, root)
        )
    elif expected_margin < 0.0:
        root = np.sqrt(-expected_margin)
        assert result.transverse_principal_roots_per_unit_wavenumber == pytest.approx(
            (-1j * root, 1j * root)
        )
    else:
        assert result.transverse_principal_roots_per_unit_wavenumber == (0j, 0j)


def test_diagnostic_is_rotation_invariant_and_does_not_mutate_inputs():
    field = np.array([0.0, 0.0, 1.0, 0.0])
    velocity = np.array([0.0, 0.4, 0.0, 0.0])
    field_before = field.copy()
    velocity_before = velocity.copy()

    result = analyze_uniform_geodesic_transverse_symbol(
        field, velocity, f_pi=1.0, e=1.0
    )

    assert result.transverse_speed_squared == pytest.approx(0.36)
    np.testing.assert_array_equal(field, field_before)
    np.testing.assert_array_equal(velocity, velocity_before)


def test_zero_speed_has_unit_transverse_principal_speed():
    result = analyze_uniform_geodesic_transverse_symbol(
        [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0],
        f_pi=2.0, e=3.0,
    )

    assert result.background_speed == 0.0
    assert result.critical_speed == pytest.approx(3.0)
    assert result.normalized_time_gradient == 0.0
    assert result.transverse_speed_squared == 1.0
    assert result.transverse_principal_roots_per_unit_wavenumber == (-1.0, 1.0)


@pytest.mark.parametrize(
    "field, velocity, f_pi, e, message",
    [
        ([1.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, 1.0, "field must be"),
        ([2.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, 1.0, "unit norm"),
        ([np.nan, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, 1.0, "finite"),
        ([True, False, False, False], [0.0, 0.1, 0.0, 0.0], 1.0, 1.0, "field must be"),
        ([1.0 + 0.0j, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, 1.0, "field must be"),
        ([1.0, 0.0, 0.0, 0.0], [0.1, 0.0, 0.0, 0.0], 1.0, 1.0, "tangent"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, np.inf, 0.0, 0.0], 1.0, 1.0, "finite"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], True, 1.0, "f_pi"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], "1.0", 1.0, "f_pi"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, 0.0, "e"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1.0, -1.0, "e"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1e308, 1e308, "finite positive diagnostic scales"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.0, 0.0], 1e-300, 1e-300, "finite positive diagnostic scales"),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 1e200, 0.0, 0.0], 1.0, 1.0, "finite diagnostic range"),
    ],
)
def test_rejects_inputs_outside_diagnostic_domain(field, velocity, f_pi, e, message):
    with pytest.raises(ValueError, match=message):
        analyze_uniform_geodesic_transverse_symbol(
            field, velocity, f_pi=f_pi, e=e
        )


def test_threshold_status_uses_only_a_small_floating_point_sign_tolerance():
    eps = np.finfo(float).eps
    near = analyze_uniform_geodesic_transverse_symbol(
        [1.0, 0.0, 0.0, 0.0], [0.0, 0.5 * (1.0 + 8 * eps), 0.0, 0.0],
        f_pi=1.0, e=1.0,
    )
    beyond = analyze_uniform_geodesic_transverse_symbol(
        [1.0, 0.0, 0.0, 0.0], [0.0, 0.5 * (1.0 + 256 * eps), 0.0, 0.0],
        f_pi=1.0, e=1.0,
    )

    assert near.status == "threshold_for_uniform_geodesic_transverse_sector"
    assert near.transverse_speed_squared < 0.0
    assert beyond.status == "nonreal_for_uniform_geodesic_transverse_sector"

