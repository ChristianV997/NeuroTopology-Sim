import numpy as np
import pytest

from field_theory.su2.local_symbol import analyze_local_skyrme_principal_symbol


FIELD = np.array([1.0, 0.0, 0.0, 0.0])


def analyze(*, velocity=None, gradients=None, covector=(1.0, 0.0, 0.0), f_pi=1.0, e=1.0,
            field=FIELD):
    if velocity is None:
        velocity = np.zeros(4)
    if gradients is None:
        gradients = np.zeros((3, 4))
    return analyze_local_skyrme_principal_symbol(
        field,
        velocity,
        gradients,
        covector,
        f_pi=f_pi,
        e=e,
    )


def assert_root_multiset(actual, expected, atol=2e-9):
    remaining = list(actual)
    assert len(remaining) == len(expected)
    for target in expected:
        index = min(range(len(remaining)), key=lambda i: abs(remaining[i] - target))
        assert abs(remaining.pop(index) - target) <= atol


def test_vacuum_has_three_copies_of_each_unit_characteristic_speed():
    result = analyze(covector=(2.0, -3.0, 6.0))

    assert result.scope == "continuum_local_tangent_symbol_one_point_one_direction_only"
    assert result.status == "real_roots_at_sampled_direction"
    assert result.general_system_hyperbolicity_status == "not_certified"
    assert result.time_kinetic_min_eigenvalue == pytest.approx(0.25)
    assert_root_multiset(result.characteristic_speeds, [-1.0] * 3 + [1.0] * 3)


@pytest.mark.parametrize(
    "speed, expected_transverse",
    [
        (0.4, 0.6),
        (0.6, 1j * np.sqrt(0.44)),
    ],
)
def test_zero_spatial_gradient_recovers_uniform_geodesic_speeds(speed, expected_transverse):
    result = analyze(velocity=[0.0, speed, 0.0, 0.0])

    assert result.general_system_hyperbolicity_status == "not_certified"
    assert_root_multiset(
        result.characteristic_speeds,
        [-1.0, 1.0, -expected_transverse, -expected_transverse,
         expected_transverse, expected_transverse],
    )


def test_mixed_collinear_background_exposes_complex_roots_missed_by_geodesic_screen():
    # n=(cos(v*t+g*x), sin(v*t+g*x), 0, 0) has V=v*e1 and G1=g*e1.
    result = analyze(
        velocity=[0.0, 1.2, 0.0, 0.0],
        gradients=[[0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0],
                   [0.0, 0.0, 0.0, 0.0]],
    )

    assert result.status == "nonreal_roots_detected"
    assert result.general_system_hyperbolicity_status == "not_certified"
    assert_root_multiset(
        result.characteristic_speeds,
        [
            -1.0,
            1.0,
            complex(-0.96, -np.sqrt(0.19) / 2.5),
            complex(-0.96, -np.sqrt(0.19) / 2.5),
            complex(-0.96, np.sqrt(0.19) / 2.5),
            complex(-0.96, np.sqrt(0.19) / 2.5),
        ],
    )


def test_reversing_spatial_covector_reverses_all_characteristic_speeds():
    args = dict(
        velocity=[0.0, 0.8, 0.0, 0.0],
        gradients=[[0.0, 0.4, 0.0, 0.0], [0.0, 0.0, 0.3, 0.0],
                   [0.0, 0.0, 0.0, 0.2]],
    )
    forward = analyze(**args, covector=(1.0, 2.0, -1.0))
    reverse = analyze(**args, covector=(-1.0, -2.0, 1.0))

    assert_root_multiset(reverse.characteristic_speeds, [-x for x in forward.characteristic_speeds])


def test_positive_covector_rescaling_does_not_change_speeds():
    args = dict(
        velocity=[0.0, 0.8, 0.0, 0.0],
        gradients=[[0.0, 0.4, 0.0, 0.0], [0.0, 0.0, 0.3, 0.0],
                   [0.0, 0.0, 0.0, 0.2]],
    )
    one = analyze(**args, covector=(1.0, 2.0, -1.0))
    scaled = analyze(**args, covector=(10.0, 20.0, -10.0))

    assert_root_multiset(scaled.characteristic_speeds, one.characteristic_speeds)


def _plane_rotation(i, j, angle):
    matrix = np.eye(4)
    c, s = np.cos(angle), np.sin(angle)
    matrix[i, i] = c
    matrix[j, j] = c
    matrix[i, j] = -s
    matrix[j, i] = s
    return matrix


def test_internal_orthogonal_rotation_preserves_root_multiset():
    field = np.array([1.0, 0.0, 0.0, 0.0])
    velocity = np.array([0.0, 0.8, 0.0, 0.0])
    gradients = np.array(
        [[0.0, 0.4, 0.0, 0.0], [0.0, 0.0, 0.3, 0.0], [0.0, 0.0, 0.0, 0.2]]
    )
    rotation = _plane_rotation(0, 2, 0.37) @ _plane_rotation(1, 3, -0.61)
    original = analyze(field=field, velocity=velocity, gradients=gradients,
                       covector=(1.0, 2.0, -1.0))
    rotated = analyze(field=rotation @ field, velocity=rotation @ velocity,
                      gradients=gradients @ rotation.T, covector=(1.0, 2.0, -1.0))

    assert_root_multiset(rotated.characteristic_speeds, original.characteristic_speeds)


def test_time_kinetic_block_matches_solver_hessian_formula():
    velocity = np.array([0.0, 0.4, 0.2, 0.0])
    gradients = np.array(
        [[0.0, 0.3, -0.1, 0.0], [0.0, 0.0, 0.2, 0.1], [0.0, -0.1, 0.0, 0.2]]
    )
    result = analyze(velocity=velocity, gradients=gradients, f_pi=1.2, e=0.8)
    alpha = 1.2**2 / 4.0
    beta = 1.0 / 0.8**2
    tangent_gradients = gradients[:, 1:]
    matrix = alpha * np.eye(3)
    for gradient in tangent_gradients:
        matrix += beta * (
            np.dot(gradient, gradient) * np.eye(3) - np.outer(gradient, gradient)
        )

    assert result.time_kinetic_min_eigenvalue == pytest.approx(
        np.linalg.eigvalsh(matrix)[0]
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"field": [1.0, 0.0, 0.0]}, "field"),
        ({"field": [2.0, 0.0, 0.0, 0.0]}, "unit norm"),
        ({"field": [True, False, False, False]}, "field"),
        ({"field": [1.0 + 0.0j, 0.0, 0.0, 0.0]}, "field"),
        ({"velocity": [np.nan, 0.0, 0.0, 0.0]}, "finite"),
        ({"velocity": [0.1, 0.0, 0.0, 0.0]}, "tangent"),
        ({"velocity": [True, False, False, False]}, "velocity"),
        ({"velocity": [1.0 + 0.0j, 0.0, 0.0, 0.0]}, "velocity"),
        ({"gradients": [[0.1, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0]]}, "tangent"),
        ({"gradients": [[0.0, np.inf, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0]]}, "finite"),
        ({"gradients": np.zeros((2, 4))}, "shape"),
        ({"covector": [0.0, 0.0, 0.0]}, "nonzero"),
        ({"covector": [1.0, np.inf, 0.0]}, "finite"),
        ({"covector": [True, False, False]}, "covector"),
        ({"f_pi": 0.0}, "f_pi"),
        ({"f_pi": True}, "f_pi"),
        ({"e": -1.0}, "e"),
        ({"e": "1.0"}, "e"),
    ],
)
def test_rejects_invalid_inputs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        analyze(**kwargs)


def test_rejects_finite_inputs_that_overflow_the_symbol():
    with pytest.raises((ValueError, FloatingPointError), match="finite|range|symbol"):
        analyze(velocity=[0.0, 1.0e200, 0.0, 0.0])


def test_inputs_are_not_mutated():
    field = FIELD.copy()
    velocity = np.array([0.0, 0.4, 0.0, 0.0])
    gradients = np.zeros((3, 4))
    covector = np.array([1.0, 2.0, -1.0])
    before = [x.copy() for x in (field, velocity, gradients, covector)]

    analyze(field=field, velocity=velocity, gradients=gradients, covector=covector)

    for actual, expected in zip((field, velocity, gradients, covector), before):
        np.testing.assert_array_equal(actual, expected)



def test_threshold_keeps_zero_speed_multiplicity_and_flags_defective_reduction():
    result = analyze(velocity=[0.0, 0.5, 0.0, 0.0])

    assert_root_multiset(result.characteristic_speeds, [-1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    assert result.eigenvector_condition_warning is True
    assert result.status == "numerically_unresolved"
    assert result.general_system_hyperbolicity_status == "not_certified"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"f_pi": 1.0e308},
        {"f_pi": 1.0e-300},
        {"e": 1.0e-320},
        {"e": 1.0e308},
    ],
)
def test_rejects_positive_couplings_outside_representable_symbol_range(kwargs):
    with pytest.raises(ValueError, match="finite diagnostic range"):
        analyze(**kwargs)


@pytest.mark.parametrize(
    "normal_component, accepted",
    [(1.5e-10, True), (2.5e-10, False)],
)
def test_velocity_tangency_tolerance_scales_with_velocity_norm(normal_component, accepted):
    velocity = [normal_component, 2.0, 0.0, 0.0]
    if accepted:
        result = analyze(velocity=velocity)
        assert result.max_derivative_tangency_residual == pytest.approx(normal_component)
    else:
        with pytest.raises(ValueError, match="tangent"):
            analyze(velocity=velocity)
