"""Synthetic tests for the discrete SU(2) Skyrme relaxation prototype."""

import numpy as np
import pytest

from field_theory.su2 import hedgehog, vacuum
from field_theory.su2.relaxation import relax_skyrme_field


def _small_hedgehog():
    return hedgehog(
        (5, 5, 5),
        radius=0.8,
        spacing=(0.5, 0.5, 0.5),
        length_unit="toy_length",
    )


def test_vacuum_is_a_discrete_stationary_point_without_mutation():
    initial = vacuum((5, 5, 5), spacing=(0.5, 0.5, 0.5))
    before = initial.components.copy()

    result = relax_skyrme_field(initial)

    assert result.termination == "gradient_tolerance"
    assert result.iterations == 0
    assert result.energy_history == (0.0,)
    assert result.topological_charge_history == (0.0,)
    np.testing.assert_array_equal(result.field.components, before)
    assert not result.field.components.flags.writeable


def test_hedgehog_relaxation_lowers_energy_and_preserves_field_constraints():
    initial = _small_hedgehog()
    before = initial.components.copy()

    result = relax_skyrme_field(
        initial,
        max_iterations=2,
        initial_step=1.0e-4,
        finite_difference_step=1.0e-5,
        gradient_tolerance=1.0e-10,
    )

    assert result.iterations >= 1
    assert result.energy_history[0] > result.energy_history[-1]
    assert np.all(np.diff(result.energy_history) < 0.0)
    assert len(result.topological_charge_history) == len(result.energy_history)
    assert np.all(np.isfinite(result.topological_charge_history))
    np.testing.assert_array_equal(initial.components, before)
    np.testing.assert_allclose(np.sum(result.field.components**2, axis=-1), 1.0, atol=1.0e-14)
    for axis in range(3):
        for index in (0, -1):
            np.testing.assert_array_equal(
                np.take(result.field.components, index, axis=axis),
                np.take(initial.components, index, axis=axis),
            )
    assert result.field.spacing == initial.spacing
    assert result.field.length_unit == initial.length_unit


def test_repeated_run_is_deterministic():
    initial = _small_hedgehog()
    kwargs = dict(max_iterations=1, initial_step=1.0e-4, finite_difference_step=1.0e-5)

    first = relax_skyrme_field(initial, **kwargs)
    second = relax_skyrme_field(initial, **kwargs)

    np.testing.assert_array_equal(first.field.components, second.field.components)
    assert first.energy_history == second.energy_history
    assert first.topological_charge_history == second.topological_charge_history
    assert first.termination == second.termination


def test_periodic_checkerboard_is_only_discrete_stationarity():
    field = np.zeros((4, 4, 4, 4), dtype=np.float64)
    field[..., 0] = ((-1.0) ** np.arange(4))[:, None, None]
    from field_theory.su2.field import SU2GridField

    initial = SU2GridField(field, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    result = relax_skyrme_field(initial)

    assert result.termination == "gradient_tolerance"
    assert result.iterations == 0
    assert result.energy_history == (0.0,)
    # The code reports stationarity of its centered finite-grid objective only.
    assert not np.array_equal(initial.components[0], initial.components[1])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_iterations": True},
        {"max_backtracks": -1},
        {"initial_step": 0.0},
        {"finite_difference_step": np.nan},
        {"gradient_tolerance": False},
        {"e": 0.0},
    ],
)
def test_invalid_solver_parameters_fail_closed(kwargs):
    with pytest.raises(ValueError):
        relax_skyrme_field(_small_hedgehog(), **kwargs)


def test_rejects_non_field_input():
    with pytest.raises(ValueError, match="SU2GridField"):
        relax_skyrme_field(np.zeros((3, 3, 3, 4)))  # type: ignore[arg-type]
