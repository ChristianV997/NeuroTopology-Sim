"""Coupled space-time refinement gate for the Lorentzian SU(2) solver.

The fixed-box sequence refines space and time together (dt proportional to h).
Per-grid temporal comparisons are used to check that this temporal contribution
is small relative to each intergrid difference before reporting a spatial order.
This is one smooth synthetic fixture, not a continuum or PDE-stability proof.
"""
from __future__ import annotations

import math

import numpy as np

from field_theory.su2 import (
    SU2GridField,
    compute_lorentzian_diagnostics,
    evolve_lorentzian_skyrme,
)


_GRID_SIZES = (8, 16, 32)
_FINAL_TIME = 0.2
_TEMPORAL_REFINEMENTS = (1, 2, 4)
_CUMULATIVE_STAGE_SITE_BUDGET = 20_000_000
_SOLVER_STAGE_SITE_CAP = 40_000_000
_MAX_GRID_NODES = 32_768


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


def _observed_order(coarse_error: float, fine_error: float) -> float:
    assert math.isfinite(coarse_error) and coarse_error > 0.0
    assert math.isfinite(fine_error) and fine_error > 0.0
    return math.log2(coarse_error / fine_error)


def _assert_finite_trajectory(trajectory) -> None:
    assert trajectory.termination == "completed"
    assert math.isfinite(trajectory.linearized_cfl_indicator)
    assert trajectory.linearized_cfl_indicator < 2.5
    assert math.isfinite(trajectory.time_kinetic_min_eigenvalue_history[-1])
    assert trajectory.time_kinetic_min_eigenvalue_history[-1] > 0.0
    assert math.isfinite(trajectory.time_kinetic_max_condition_history[-1])
    assert math.isfinite(trajectory.max_unit_norm_error)
    assert trajectory.max_unit_norm_error < 1.0e-10
    assert math.isfinite(trajectory.max_tangency_error)
    assert trajectory.max_tangency_error < 1.0e-10
    assert all(
        math.isfinite(value)
        for value in trajectory.energy_balance_residual_history
    )
    assert all(
        np.all(np.isfinite(snapshot.components))
        for snapshot in trajectory.fields
    )
    assert all(np.all(np.isfinite(velocity)) for velocity in trajectory.velocities)


def test_fixed_box_refinement_separates_temporal_contamination():
    """Check dt refinement on each grid before comparing intergrid solutions."""
    box_length = 2.0 * np.pi
    # dt_h = 0.4/n gives (n, base steps) = (8,4), (16,8), (32,16).
    # The three runs on each grid use dt_h, dt_h/2, and dt_h/4.
    run_plan = tuple(
        (samples, samples // 2 * refinement)
        for samples in _GRID_SIZES
        for refinement in _TEMPORAL_REFINEMENTS
    )
    cumulative_stage_site_work = sum(
        4 * samples**3 * steps for samples, steps in run_plan
    )
    assert cumulative_stage_site_work == 15_654_912
    assert cumulative_stage_site_work <= _CUMULATIVE_STAGE_SITE_BUDGET
    assert max(
        4 * samples**3 * steps for samples, steps in run_plan
    ) <= _SOLVER_STAGE_SITE_CAP
    assert max(samples**3 for samples in _GRID_SIZES) <= _MAX_GRID_NODES

    trajectories = {}
    initial_energies = {}
    time_steps = {}

    for samples in _GRID_SIZES:
        field, velocity = _smooth_periodic_state(samples, box_length)
        initial = compute_lorentzian_diagnostics(
            field, velocity, f_pi=1.0, e=1.0
        )
        assert math.isfinite(initial.total_energy)
        initial_energies[samples] = initial.total_energy

        base_steps = samples // 2
        grid_runs = []
        for refinement in _TEMPORAL_REFINEMENTS:
            steps = base_steps * refinement
            dt = _FINAL_TIME / steps
            assert math.isclose(
                steps * dt, _FINAL_TIME, rel_tol=0.0, abs_tol=1.0e-15
            )
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
            _assert_finite_trajectory(trajectory)
            grid_runs.append(trajectory)
            time_steps[(samples, refinement)] = dt
        trajectories[samples] = grid_runs

    # Estimate temporal endpoint differences separately at each fixed grid.
    # The finer pair (dt_h/2 vs dt_h/4) estimates residual temporal error in
    # the dt_h/4 state used for all intergrid comparisons.
    temporal_field_differences = {}
    temporal_velocity_differences = {}
    for samples, grid_runs in trajectories.items():
        temporal_field_differences[samples] = [
            _rms_difference(
                grid_runs[index].fields[-1].components,
                grid_runs[index + 1].fields[-1].components,
            )
            for index in range(2)
        ]
        temporal_velocity_differences[samples] = [
            _rms_difference(
                grid_runs[index].velocities[-1],
                grid_runs[index + 1].velocities[-1],
            )
            for index in range(2)
        ]

    # Compare dt_h/4 endpoints at coincident nodes. Every second fine-grid
    # sample coincides with the corresponding coarse-grid coordinate.
    field_spatial_differences = []
    velocity_spatial_differences = []
    for coarse_index in range(len(_GRID_SIZES) - 1):
        coarse_n = _GRID_SIZES[coarse_index]
        fine_n = _GRID_SIZES[coarse_index + 1]
        coarse_fine_time = trajectories[coarse_n][-1]
        fine_fine_time = trajectories[fine_n][-1]
        restriction = (slice(None, None, 2),) * 3 + (slice(None),)
        field_spatial_differences.append(
            _rms_difference(
                coarse_fine_time.fields[-1].components,
                fine_fine_time.fields[-1].components[restriction],
            )
        )
        velocity_spatial_differences.append(
            _rms_difference(
                coarse_fine_time.velocities[-1],
                fine_fine_time.velocities[-1][restriction],
            )
        )

    temporal_field_to_spatial = []
    temporal_velocity_to_spatial = []
    for pair_index in range(len(_GRID_SIZES) - 1):
        coarse_n = _GRID_SIZES[pair_index]
        fine_n = _GRID_SIZES[pair_index + 1]
        field_space = field_spatial_differences[pair_index]
        velocity_space = velocity_spatial_differences[pair_index]
        assert math.isfinite(field_space) and field_space > 0.0
        assert math.isfinite(velocity_space) and velocity_space > 0.0

        field_temporal_estimate = max(
            temporal_field_differences[coarse_n][-1],
            temporal_field_differences[fine_n][-1],
        )
        velocity_temporal_estimate = max(
            temporal_velocity_differences[coarse_n][-1],
            temporal_velocity_differences[fine_n][-1],
        )
        temporal_field_to_spatial.append(field_temporal_estimate / field_space)
        temporal_velocity_to_spatial.append(
            velocity_temporal_estimate / velocity_space
        )

    assert max(temporal_field_to_spatial) <= 0.10, (
        "temporal field differences exceed 10% of intergrid differences; "
        "no spatial-order estimate is justified: "
        f"ratios={temporal_field_to_spatial}, "
        f"temporal={temporal_field_differences}, "
        f"spatial={field_spatial_differences}"
    )
    assert max(temporal_velocity_to_spatial) <= 0.10, (
        "temporal velocity differences exceed 10% of intergrid differences; "
        "no spatial-order estimate is justified: "
        f"ratios={temporal_velocity_to_spatial}, "
        f"temporal={temporal_velocity_differences}, "
        f"spatial={velocity_spatial_differences}"
    )

    # Require decreasing intergrid differences, but do not impose a universal
    # order: the forward-link quartic term can alter leading spatial error.
    assert field_spatial_differences[1] < field_spatial_differences[0], (
        f"field intergrid differences did not decrease: {field_spatial_differences}"
    )
    assert velocity_spatial_differences[1] < velocity_spatial_differences[0], (
        "velocity intergrid differences did not decrease: "
        f"{velocity_spatial_differences}"
    )
    field_order = _observed_order(*field_spatial_differences)
    velocity_order = _observed_order(*velocity_spatial_differences)

    initial_energy_differences = [
        abs(
            initial_energies[_GRID_SIZES[index]]
            - initial_energies[_GRID_SIZES[index + 1]]
        )
        for index in range(len(_GRID_SIZES) - 1)
    ]
    energy_order = None
    if all(
        math.isfinite(value) and value > 0.0
        for value in initial_energy_differences
    ):
        # Report the observed order only; do not presume second-order behavior.
        energy_order = _observed_order(*initial_energy_differences)

    energy_balance_residuals = {
        samples: abs(grid_runs[-1].energy_balance_residual_history[-1])
        for samples, grid_runs in trajectories.items()
    }
    residual_tolerance = 2.0e-5 * max(
        1.0, abs(initial_energies[_GRID_SIZES[0]])
    )
    assert all(math.isfinite(value) for value in energy_balance_residuals.values())
    assert max(energy_balance_residuals.values()) < residual_tolerance, (
        "energy-balance residual monitor exceeded tolerance: "
        f"residuals={energy_balance_residuals}, tolerance={residual_tolerance}"
    )

    print(
        "fixed-box coupled space-time refinement: "
        f"n={_GRID_SIZES}, dt={time_steps}, "
        f"cumulative_stage_site_work={cumulative_stage_site_work}, "
        f"temporal_field_differences={temporal_field_differences}, "
        f"temporal_velocity_differences={temporal_velocity_differences}, "
        f"temporal_field_to_spatial={temporal_field_to_spatial}, "
        f"temporal_velocity_to_spatial={temporal_velocity_to_spatial}, "
        f"field_spatial_differences={field_spatial_differences}, "
        f"field_observed_order={field_order}, "
        f"velocity_spatial_differences={velocity_spatial_differences}, "
        f"velocity_observed_order={velocity_order}, "
        f"initial_energies={initial_energies}, "
        f"initial_energy_differences={initial_energy_differences}, "
        f"initial_energy_observed_order={energy_order}, "
        f"energy_balance_residuals={energy_balance_residuals}"
    )
