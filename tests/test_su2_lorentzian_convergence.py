"""Temporal convergence regression for the projected Lorentzian SU(2) solver.

This checks finite-grid time refinement only; it does not establish spatial
convergence, PDE well-posedness, or physical calibration.
"""
from __future__ import annotations

import math

import numpy as np

from field_theory.su2 import SU2GridField, evolve_lorentzian_skyrme


def _smooth_periodic_state(samples: int = 4):
    phase = 2.0 * np.pi * np.arange(samples) / samples
    x, y, z = np.meshgrid(phase, phase, phase, indexing="ij")
    pion = np.stack(
        (
            0.08 * np.sin(x) + 0.02 * np.cos(y + z),
            0.07 * np.sin(y) + 0.02 * np.cos(z - x),
            0.06 * np.sin(z) + 0.02 * np.cos(x + y),
        ),
        axis=-1,
    )
    sigma = np.sqrt(1.0 - np.sum(pion * pion, axis=-1, keepdims=True))
    components = np.concatenate((sigma, pion), axis=-1)
    field = SU2GridField(
        components, spacing=(1.0, 1.0, 1.0), boundary="periodic"
    )

    raw_velocity = np.zeros_like(components)
    raw_velocity[..., 1] = 0.025 * np.cos(y)
    raw_velocity[..., 2] = 0.020 * np.sin(z)
    raw_velocity[..., 3] = 0.015 * np.cos(x + y)
    velocity = raw_velocity - np.sum(
        raw_velocity * components, axis=-1, keepdims=True
    ) * components
    return field, velocity


def _rms_state_error(left: np.ndarray, right: np.ndarray) -> float:
    difference = np.asarray(left) - np.asarray(right)
    return float(np.sqrt(np.mean(np.sum(difference * difference, axis=-1))))


def _observed_orders(errors: list[float]) -> tuple[float, float]:
    assert all(math.isfinite(error) and error > 0.0 for error in errors), errors
    return (
        math.log2(errors[0] / errors[1]),
        math.log2(errors[1] / errors[2]),
    )


def test_projected_solver_temporal_refinement_converges_at_fixed_final_time():
    """Compare three dt values with a dt/8 reference, including energy balance.

    The broad lower bound is deliberately below classical RK4 order: stage and
    endpoint projection may alter the observed order. The test requires
    superlinear finite-grid convergence, not fourth-order behavior.
    """
    field, velocity = _smooth_periodic_state()
    final_time = 0.2
    coarse_dt = 0.04
    time_steps = (coarse_dt, coarse_dt / 2.0, coarse_dt / 4.0, coarse_dt / 8.0)
    trajectories = []
    for dt in time_steps:
        steps = round(final_time / dt)
        assert steps * dt == final_time
        trajectories.append(
            evolve_lorentzian_skyrme(
                field,
                velocity,
                dt=dt,
                steps=steps,
                save_every=steps,
                f_pi=1.0,
                e=1.0,
                damping=0.12,
            )
        )

    reference = trajectories[-1]
    field_errors = [
        _rms_state_error(item.fields[-1].components, reference.fields[-1].components)
        for item in trajectories[:-1]
    ]
    velocity_errors = [
        _rms_state_error(item.velocities[-1], reference.velocities[-1])
        for item in trajectories[:-1]
    ]
    field_orders = _observed_orders(field_errors)
    velocity_orders = _observed_orders(velocity_errors)

    assert min(field_orders) > 1.0, f"field observed orders={field_orders}, errors={field_errors}"
    assert min(velocity_orders) > 1.0, (
        f"velocity observed orders={velocity_orders}, errors={velocity_errors}"
    )

    energy_residuals = [
        abs(item.energy_balance_residual_history[-1]) for item in trajectories
    ]
    initial_energy = abs(trajectories[0].total_energy_history[0])
    residual_tolerance = 2.0e-6 * max(1.0, initial_energy)
    assert all(math.isfinite(value) for value in energy_residuals)
    assert max(energy_residuals) < residual_tolerance, (
        f"energy residuals={energy_residuals}, tolerance={residual_tolerance}"
    )

    residual_floor = 128.0 * np.finfo(np.float64).eps * max(1.0, initial_energy)
    if min(energy_residuals[:3]) > residual_floor:
        energy_orders = _observed_orders(energy_residuals[:3])
        assert min(energy_orders) > 0.5, (
            f"energy-balance residual observed orders={energy_orders}, "
            f"residuals={energy_residuals}"
        )
    else:
        # At roundoff scale, an order estimate is not meaningful.
        assert energy_residuals[-1] <= residual_tolerance
