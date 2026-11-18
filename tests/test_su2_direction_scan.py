import numpy as np
import pytest

from field_theory.su2.direction_scan import (
    MAX_DIRECTIONS_HARD_LIMIT,
    scan_local_skyrme_principal_symbol_directions,
)
from field_theory.su2.local_symbol import analyze_local_skyrme_principal_symbol


FIELD = np.array([1.0, 0.0, 0.0, 0.0])


def ambient(tangent):
    return np.array([0.0, *tangent], dtype=float)


def scan(velocity=None, gradients=None, **kwargs):
    if velocity is None:
        velocity = np.zeros(4)
    if gradients is None:
        gradients = np.zeros((3, 4))
    return scan_local_skyrme_principal_symbol_directions(
        FIELD,
        velocity,
        gradients,
        f_pi=1.0,
        e=1.0,
        **kwargs,
    )


def assert_root_multiset(actual, expected, atol=2e-9):
    remaining = list(actual)
    assert len(remaining) == len(expected)
    for target in expected:
        index = min(range(len(remaining)), key=lambda i: abs(remaining[i] - target))
        assert abs(remaining.pop(index) - target) <= atol


def test_vacuum_scan_is_finite_discovery_not_a_hyperbolicity_certificate():
    result = scan(max_directions=12, max_refinement_levels=2)

    assert result.scope == "finite_nested_icosphere_discovery_only"
    assert result.status == "no_nonreal_roots_sampled"
    assert result.sample_count == 12
    assert result.nonreal_sample_count == 0
    assert all(sample.status == "real_roots_at_sampled_direction" for sample in result.samples)
    assert all(len(sample.characteristic_speeds) == 6 for sample in result.samples)
    assert not hasattr(result, "hyperbolicity_certified")


def test_antipodal_scan_samples_reverse_root_multisets_for_nonzero_mixing():
    velocity = ambient([0.10, 0.05, 0.0])
    gradients = np.stack(
        [ambient([0.03, 0.02, 0.0]), ambient([0.0, 0.01, 0.02]), np.zeros(4)]
    )
    result = scan(velocity, gradients, max_directions=12, max_refinement_levels=0)

    for sample in result.samples:
        opposite = next(
            candidate
            for candidate in result.samples
            if np.allclose(candidate.direction, -np.asarray(sample.direction), atol=1e-15)
        )
        assert_root_multiset(
            opposite.characteristic_speeds,
            [-root for root in sample.characteristic_speeds],
            atol=2e-8,
        )


def test_spatial_rotation_covariance_matches_the_wrapped_public_analyzer():
    velocity = ambient([0.10, 0.05, -0.02])
    gradients = np.stack(
        [
            ambient([0.02, 0.04, 0.01]),
            ambient([-0.01, 0.03, 0.02]),
            ambient([0.03, 0.0, -0.02]),
        ]
    )
    direction = np.array([1.0, 2.0, -1.0])
    direction /= np.linalg.norm(direction)
    angle = 0.37
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )

    original = analyze_local_skyrme_principal_symbol(
        FIELD, velocity, gradients, direction, f_pi=1.0, e=1.0
    )
    rotated = analyze_local_skyrme_principal_symbol(
        FIELD,
        velocity,
        rotation @ gradients,
        rotation @ direction,
        f_pi=1.0,
        e=1.0,
    )

    assert original.status == rotated.status
    assert_root_multiset(rotated.characteristic_speeds, original.characteristic_speeds, atol=2e-8)


def test_known_nonreal_jet_is_reported_and_refinement_stays_within_budget():
    result = scan(
        velocity=ambient([0.6, 0.0, 0.0]),
        max_directions=42,
        max_refinement_levels=5,
    )

    assert result.status == "nonreal_roots_sampled"
    assert result.nonreal_sample_count > 0
    assert result.sample_count == 42
    assert result.sample_count <= result.max_directions
    assert result.refinement_levels_completed == 1
    assert result.termination_reason == "direction_budget_exhausted"


def test_repeated_threshold_roots_remain_explicitly_unresolved():
    result = scan(
        velocity=ambient([0.5, 0.0, 0.0]),
        max_directions=12,
        max_refinement_levels=1,
    )

    assert result.status == "numerically_unresolved_samples"
    assert result.unresolved_sample_count > 0
    assert result.sample_count == 12
    assert result.termination_reason == "direction_budget_exhausted"


def test_scan_order_and_results_are_deterministic():
    kwargs = {
        "velocity": ambient([0.6, 0.0, 0.0]),
        "max_directions": 42,
        "max_refinement_levels": 2,
    }
    first = scan(**kwargs)
    second = scan(**kwargs)

    assert first == second
    assert first.sample_count <= MAX_DIRECTIONS_HARD_LIMIT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_directions": 11},
        {"max_directions": True},
        {"max_directions": MAX_DIRECTIONS_HARD_LIMIT + 1},
        {"max_refinement_levels": -1},
        {"max_refinement_levels": True},
    ],
)
def test_invalid_scan_budgets_fail_closed(kwargs):
    with pytest.raises(ValueError):
        scan(**kwargs)


def test_invalid_shared_jet_fails_closed_instead_of_returning_a_partial_scan():
    with pytest.raises(ValueError, match="field must have shape"):
        scan(velocity=np.zeros(3), max_directions=12)
