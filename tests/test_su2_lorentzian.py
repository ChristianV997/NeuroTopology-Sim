import numpy as np
import pytest

from field_theory.su2 import SU2GridField
from field_theory.su2.lorentzian import (
    compute_lorentzian_diagnostics,
    evolve_lorentzian_skyrme,
    linearized_lattice_frequency,
)
from field_theory.su2.nearest_neighbor import compute_nearest_neighbor_diagnostics


def _texture(samples=4, amplitude=0.25):
    x = np.arange(samples)[:, None, None]
    y = np.arange(samples)[None, :, None]
    z = np.arange(samples)[None, None, :]
    theta = amplitude * np.sin(2.0 * np.pi * x / samples)
    psi = amplitude * np.sin(2.0 * np.pi * y / samples)
    theta, psi, _ = np.broadcast_arrays(theta, psi, z)
    q = np.stack(
        (
            np.cos(theta),
            np.sin(theta) * np.cos(psi),
            np.sin(theta) * np.sin(psi),
            np.zeros_like(theta),
        ),
        axis=-1,
    )
    field = SU2GridField(q, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    speed = 0.04 * np.sin(2.0 * np.pi * z / samples)
    velocity = np.zeros_like(q)
    velocity[..., 3] = speed
    return field, velocity


def test_full_lorentzian_energy_has_sigma_and_time_space_skyrme_terms():
    field, velocity = _texture()
    f_pi, e = 1.3, 0.8
    diagnostics = compute_lorentzian_diagnostics(
        field, velocity, f_pi=f_pi, e=e
    )
    static = compute_nearest_neighbor_diagnostics(field, f_pi=f_pi, e=e)
    d_volume = np.prod(field.spacing)
    expected_sigma = 0.125 * f_pi**2 * d_volume * np.sum(velocity**2)
    differences = tuple(
        (np.roll(field.components, -1, axis=axis) - field.components)
        / field.spacing[axis]
        for axis in range(3)
    )
    expected_skyrme = 0.0
    for gradient in differences:
        wedge = velocity[..., :, None] * gradient[..., None, :] - gradient[..., :, None] * velocity[..., None, :]
        expected_skyrme += 0.25 / (e**2) * d_volume * np.sum(wedge**2)

    assert diagnostics.energy_sigma == pytest.approx(static.energy_sigma)
    assert diagnostics.energy_skyrme == pytest.approx(static.energy_skyrme)
    assert diagnostics.kinetic_sigma == pytest.approx(expected_sigma)
    assert diagnostics.kinetic_skyrme == pytest.approx(expected_skyrme)
    assert diagnostics.kinetic_skyrme > 0.0
    assert diagnostics.total_energy == pytest.approx(
        static.energy_total + expected_sigma + expected_skyrme
    )


def test_constant_field_has_no_quartic_time_space_kinetic_energy():
    values = np.zeros((3, 3, 3, 4), dtype=float)
    values[..., 0] = 1.0
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    velocity = np.zeros_like(values)
    velocity[..., 1] = 0.1
    diagnostics = compute_lorentzian_diagnostics(field, velocity)
    assert diagnostics.kinetic_sigma > 0.0
    assert diagnostics.kinetic_skyrme == pytest.approx(0.0, abs=1e-15)


def test_vacuum_linearized_lattice_dispersion_matches_forward_link_symbol():
    actual = linearized_lattice_frequency(
        spacing=(0.5, 1.0, 2.0), wave_number=(1.1, 0.7, 0.4)
    )
    expected = np.sqrt(
        sum(
            4.0 * np.sin(k * h / 2.0) ** 2 / h**2
            for k, h in zip((1.1, 0.7, 0.4), (0.5, 1.0, 2.0))
        )
    )
    assert actual == pytest.approx(expected)


def test_uniform_field_follows_the_analytic_s3_geodesic_with_fourth_order_refinement():
    values = np.zeros((3, 3, 3, 4), dtype=float)
    values[..., 0] = 1.0
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    speed = 0.3
    velocity = np.zeros_like(values)
    velocity[..., 1] = speed
    coarse = evolve_lorentzian_skyrme(
        field, velocity, dt=0.04, steps=10, save_every=10
    )
    fine = evolve_lorentzian_skyrme(
        field, velocity, dt=0.02, steps=20, save_every=20
    )
    time = 0.4
    expected = np.zeros_like(values)
    expected[..., 0] = np.cos(speed * time)
    expected[..., 1] = np.sin(speed * time)
    coarse_error = np.linalg.norm(coarse.fields[-1].components - expected)
    fine_error = np.linalg.norm(fine.fields[-1].components - expected)
    assert fine_error < coarse_error / 10.0


def test_full_lorentzian_solver_preserves_s3_and_energy_under_refinement():
    field, velocity = _texture(samples=3, amplitude=0.5)
    coarse = evolve_lorentzian_skyrme(
        field, velocity, dt=0.04, steps=10, save_every=10
    )
    fine = evolve_lorentzian_skyrme(
        field, velocity, dt=0.02, steps=20, save_every=20
    )
    assert coarse.hyperbolicity_status == "not_certified"
    for result in (coarse, fine):
        assert result.termination == "completed"
        assert result.max_unit_norm_error < 1e-10
        assert result.max_tangency_error < 1e-10
        assert result.total_energy_history[-1] == pytest.approx(
            result.total_energy_history[0], rel=2e-4, abs=2e-7
        )
    coarse_drift = abs(coarse.total_energy_history[-1] - coarse.total_energy_history[0])
    fine_drift = abs(fine.total_energy_history[-1] - fine.total_energy_history[0])
    assert fine_drift < coarse_drift / 10.0


def test_damping_energy_balance_is_reported_separately():
    field, velocity = _texture(samples=3, amplitude=0.1)
    result = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=20, save_every=5, damping=0.2
    )
    assert np.all(np.diff(result.dissipated_energy_history) >= -1e-13)
    assert result.dissipated_energy_history[-1] > 0.0
    assert np.max(np.abs(result.energy_balance_residual_history)) < 2e-5


def test_resource_limits_fail_before_evolution():
    field, velocity = _texture(samples=3)
    with pytest.raises(ValueError, match="snapshot|memory|limit"):
        evolve_lorentzian_skyrme(
            field,
            velocity,
            dt=0.001,
            steps=100,
            save_every=1,
            max_snapshot_bytes=1,
        )


def test_fixed_vacuum_boundary_and_custom_pinned_sites_stay_frozen():
    periodic, velocity = _texture(samples=3, amplitude=0.1)
    q = periodic.components.copy()
    q[[0, -1], :, :, :] = (1.0, 0.0, 0.0, 0.0)
    q[:, [0, -1], :, :] = (1.0, 0.0, 0.0, 0.0)
    q[:, :, [0, -1], :] = (1.0, 0.0, 0.0, 0.0)
    field = SU2GridField(q, spacing=periodic.spacing, boundary="fixed_vacuum")
    boundary_velocity = velocity.copy()
    boundary_velocity[[0, -1], :, :, :] = 0.0
    boundary_velocity[:, [0, -1], :, :] = 0.0
    boundary_velocity[:, :, [0, -1], :] = 0.0
    result = evolve_lorentzian_skyrme(
        field, boundary_velocity, dt=0.001, steps=2, save_every=2
    )
    assert np.array_equal(result.fields[-1].components[[0, -1], :, :, :], q[[0, -1], :, :, :])
    assert np.max(np.abs(result.velocities[-1][[0, -1], :, :, :])) == 0.0

    periodic, velocity = _texture(samples=3, amplitude=0.1)
    fixed = np.zeros(periodic.components.shape[:3], dtype=bool)
    fixed[1, 1, 1] = True
    pinned_value = periodic.components[1, 1, 1].copy()
    pinned_velocity = velocity.copy()
    pinned_velocity[fixed] = 0.0
    result = evolve_lorentzian_skyrme(
        periodic,
        pinned_velocity,
        dt=0.001,
        steps=2,
        fixed_mask=fixed,
    )
    assert np.array_equal(result.fields[-1].components[fixed], pinned_value[None, :])
    assert np.array_equal(result.velocities[-1][fixed], np.zeros((1, 4)))


def test_rejects_nontangent_or_malformed_initial_velocity():
    field, velocity = _texture(samples=3)
    bad = velocity.copy()
    bad[..., 0] = 0.2
    with pytest.raises(ValueError, match="tangent"):
        evolve_lorentzian_skyrme(field, bad, dt=0.001, steps=1)
    with pytest.raises(ValueError, match="matching"):
        evolve_lorentzian_skyrme(field, velocity[..., :3], dt=0.001, steps=1)
    bad = velocity.copy()
    bad[0, 0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        evolve_lorentzian_skyrme(field, bad, dt=0.001, steps=1)


def test_rejects_dt_above_declared_vacuum_linearized_rk4_limit():
    field, velocity = _texture(samples=3)
    with pytest.raises(ValueError, match="CFL"):
        evolve_lorentzian_skyrme(field, velocity, dt=1.0, steps=1)

