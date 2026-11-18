"""Fixed-box spatial refinement gate for Lorentzian SU(2) evolution.

This couples dt to h for a bounded continuum-style refinement experiment;
it is not a pure spatial truncation study or a continuum solution certificate.
"""
from __future__ import annotations

import math

import numpy as np

from field_theory.su2 import (
    SU2GridField,
    compute_lorentzian_diagnostics,
    evolve_lorentzian_skyrme,
)


def _smooth_periodic_state(samples: int, box_length: float = 2.0 * np.pi):
    spacing = box_length / samples
    coordinate = np.arange(samples, dtype=np.float64) * spacing
    x, y, z = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")

    unnormalized = np.stack(
        (
            np.ones_like(x),
            0.25 * np.sin(x),
            0.25 * np.sin(y),
            0.25 * np.sin(z),
        ),
        axis=-1,
    )
    field_values = unnormalized / np.linalg.norm(
        unnormalized, axis=-1, keepdims=True
    )
    field = SU2GridField(
        field_values,
        spacing=(spacing, spacing, spacing),
        boundary="periodic",
    )

    raw_velocity = np.zeros_like(field_values)
    raw_velocity[..., 1] = 0.020 * np.sin(y + z)
    raw_velocity[..., 2] = 0.018 * np.cos(z + x)
    raw_velocity[..., 3] = 0.016 * np.sin(x - y)
    velocity = raw_velocity - np.sum(
        raw_velocity * field_values, axis=-1, keepdims=True
    ) * field_values
    return field, velocity


def _rms_difference(coarse: np.ndarray, fine_on_coarse: np.ndarray) -> float:
    delta = np.asarray(coarse) - np.asarray(fine_on_coarse)
    return float(np.sqrt(np.mean(np.sum(delta * delta, axis=-1))))


def _order(coarse_error: float, fine_error: float) -> float:
    assert math.isfinite(coarse_error) and coarse_error > 0.0
    assert math.isfinite(fine_error) and fine_error > 0.0
    return math.log2(coarse_error / fine_error)


def test_fixed_box_space_time_refinement_is_second_order_like():
    """Compare n=8,16,32 at fixed box and T, with dt proportional to h."""
    box_length = 2.0 * np.pi
    final_time = 0.2
    grid_sizes = (8, 16, 32)
    steps_by_grid = (4, 8, 16)
    trajectories = []
    initial_energies = []
    spacings = []

    for samples, steps in zip(grid_sizes, steps_by_grid):
        field, velocity = _smooth_periodic_state(samples, box_length)
        spacing = box_length / samples
        dt = final_time / steps
        spacings.append(spacing)

        initial = compute_lorentzian_diagnostics(
            field, velocity, f_pi=1.0, e=1.0
        )
        initial_energies.append(initial.total_energy)
        trajectory = evolve_lorentzian_skyrme(
            field,
            velocity,
            dt=dt,
            steps=steps,
            save_every=steps,
            f_pi=1.0,
            e=1.0,
            damping=0.0,
        )
        trajectories.append(trajectory)

        assert samples**3 <= 32_768
        assert trajectory.termination == "completed"
        assert trajectory.linearized_cfl_indicator < 2.5
        assert math.isfinite(trajectory.time_kinetic_min_eigenvalue_history[-1])
        assert trajectory.time_kinetic_min_eigenvalue_history[-1] > 0.0
        assert math.isfinite(trajectory.time_kinetic_max_condition_history[-1])
        assert trajectory.max_unit_norm_error < 1.0e-10
        assert trajectory.max_tangency_error < 1.0e-10
        assert all(
            math.isfinite(value)
            for value in trajectory.energy_balance_residual_history
        )

    # Each finer grid has twice as many nodes per axis, so every second node
    # coincides with a node of the preceding grid.
    field_differences = []
    velocity_differences = []
    for coarse_index in range(2):
        coarse_field = trajectories[coarse_index].fields[-1].components
        fine_field = trajectories[coarse_index + 1].fields[-1].components
        coarse_velocity = trajectories[coarse_index].velocities[-1]
        fine_velocity = trajectories[coarse_index + 1].velocities[-1]
        restriction = (slice(None, None, 2),) * 3 + (slice(None),)
        field_differences.append(
            _rms_difference(coarse_field, fine_field[restriction])
        )
        velocity_differences.append(
            _rms_difference(coarse_velocity, fine_velocity[restriction])
        )

    field_order = _order(*field_differences)
    velocity_order = _order(*velocity_differences)
    # Forward-link discretization with dt/h fixed showed approximately second-
    # order behavior in the design probe; retain margin for the coupled gate.
    assert field_order > 1.3, (
        f"field refinement order={field_order}, differences={field_differences}"
    )
    assert velocity_order > 1.3, (
        f"velocity refinement order={velocity_order}, differences={velocity_differences}"
    )

    energy_differences = [
        abs(initial_energies[index] - initial_energies[index + 1])
        for index in range(2)
    ]
    energy_order = _order(*energy_differences)
    assert energy_order > 1.0, (
        f"initial energy refinement order={energy_order}, "
        f"differences={energy_differences}"
    )

    energy_residuals = [
        abs(item.energy_balance_residual_history[-1]) for item in trajectories
    ]
    residual_tolerance = 2.0e-5 * max(1.0, abs(initial_energies[0]))
    assert max(energy_residuals) < residual_tolerance, (
        f"energy-balance residuals={energy_residuals}, "
        f"tolerance={residual_tolerance}"
    )
    print(
        "fixed-box refinement: "
        f"n={grid_sizes}, h={spacings}, steps={steps_by_grid}, "
        f"field_differences={field_differences}, field_order={field_order}, "
        f"velocity_differences={velocity_differences}, "
        f"velocity_order={velocity_order}, initial_energies={initial_energies}, "
        f"energy_order={energy_order}, energy_balance_residuals={energy_residuals}"
    )
