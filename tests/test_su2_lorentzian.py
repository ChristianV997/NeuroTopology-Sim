import numpy as np
import pytest

from field_theory.su2 import SU2GridField
import field_theory.su2.lorentzian as lorentzian_module
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


def test_aggregate_rk_stage_site_budget_fails_before_evolution(monkeypatch):
    field, velocity = _texture(samples=3)

    def fail_if_rhs_runs(*args, **kwargs):
        pytest.fail("work budget must reject before calling the evolution RHS")

    monkeypatch.setattr(
        lorentzian_module, "_acceleration_and_dissipation", fail_if_rhs_runs
    )
    # 3^3 sites * 2 steps * 4 RK stages = 216 evaluations.
    with pytest.raises(ValueError, match="max_rk_stage_site_evaluations"):
        evolve_lorentzian_skyrme(
            field,
            velocity,
            dt=0.001,
            steps=2,
            max_rk_stage_site_evaluations=215,
        )


def test_midrun_failure_reports_the_current_integration_step(monkeypatch):
    field, velocity = _texture(samples=3)
    original = lorentzian_module._acceleration_and_dissipation
    calls = 0

    def fail_on_first_stage_of_second_step(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            raise FloatingPointError("injected stage failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        lorentzian_module,
        "_acceleration_and_dissipation",
        fail_on_first_stage_of_second_step,
    )
    with pytest.raises(FloatingPointError, match="failed at step 2"):
        evolve_lorentzian_skyrme(
            field, velocity, dt=0.001, steps=3, save_every=3
        )


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


def _independent_forward_gradients(q, spacing, boundary):
    gradients = []
    for axis, step in enumerate(spacing):
        difference = np.roll(q, -1, axis=axis) - q
        if boundary == "fixed_vacuum":
            selector = [slice(None)] * 4
            selector[axis] = -1
            difference[tuple(selector)] = 0.0
        gradients.append(difference / step)
    return tuple(gradients)


def _independent_lagrangian(q, velocity, spacing, boundary, f_pi, e):
    field = SU2GridField(q, spacing=spacing, boundary=boundary)
    gradients = _independent_forward_gradients(q, spacing, boundary)
    cell_volume = float(np.prod(spacing))
    kinetic = (f_pi**2 / 8.0) * cell_volume * float(np.sum(velocity**2))
    for gradient in gradients:
        v2 = np.sum(velocity**2, axis=-1)
        g2 = np.sum(gradient**2, axis=-1)
        vg = np.sum(velocity * gradient, axis=-1)
        kinetic += cell_volume / (2.0 * e**2) * float(
            np.sum(v2 * g2 - vg**2)
        )
    potential = compute_nearest_neighbor_diagnostics(
        field, f_pi=f_pi, e=e
    )
    return kinetic - potential.energy_sigma - potential.energy_skyrme


def _independent_momentum(q, velocity, spacing, boundary, f_pi, e):
    gradients = _independent_forward_gradients(q, spacing, boundary)
    momentum = (f_pi**2 / 4.0) * velocity.copy()
    for gradient in gradients:
        g2 = np.sum(gradient**2, axis=-1, keepdims=True)
        vg = np.sum(velocity * gradient, axis=-1, keepdims=True)
        momentum += (g2 * velocity - vg * gradient) / e**2
    return float(np.prod(spacing)) * momentum


def _geodesic_position(q, velocity, delta_t):
    speed = np.linalg.norm(velocity, axis=-1, keepdims=True)
    angle = delta_t * speed
    scale = np.divide(
        np.sin(angle),
        speed,
        out=np.full_like(speed, delta_t),
        where=speed > 0.0,
    )
    return np.cos(angle) * q + scale * velocity


def _great_circle_perturbation(q, site, tangent_direction, epsilon):
    varied = q.copy()
    norm = float(np.linalg.norm(tangent_direction))
    angle = epsilon * norm
    varied[site] = (
        np.cos(angle) * q[site]
        + (np.sin(angle) / norm) * tangent_direction
    )
    return varied


@pytest.mark.parametrize("boundary", ["periodic", "fixed_vacuum"])
def test_acceleration_satisfies_discrete_lagrange_dalembert_residual(boundary):
    """Check the assembled force against independent action differences.

    The test differentiates the scalar discrete Lagrangian and canonical
    momentum independently, then checks the tangent Euler--Lagrange residual.
    It covers both periodic links and the fixed-vacuum boundary quadrature.
    """
    samples = 5
    spacing = (0.7, 0.9, 1.1)
    coordinates = np.linspace(0.0, 1.0, samples)
    x, y, z = np.meshgrid(coordinates, coordinates, coordinates, indexing="ij")
    if boundary == "periodic":
        phase_x = 2.0 * np.pi * np.arange(samples) / samples
        phase_y = 2.0 * np.pi * np.arange(samples) / samples
        phase_z = 2.0 * np.pi * np.arange(samples) / samples
        x, y, z = np.meshgrid(phase_x, phase_y, phase_z, indexing="ij")
        envelope = np.ones_like(x)
    else:
        envelope = (
            np.sin(np.pi * x) ** 2
            * np.sin(np.pi * y) ** 2
            * np.sin(np.pi * z) ** 2
        )

    pion = np.stack(
        (
            0.16 * envelope * np.sin(x),
            0.13 * envelope * np.cos(y),
            0.10 * envelope * np.sin(z),
        ),
        axis=-1,
    )
    q = np.concatenate(
        (np.sqrt(1.0 - np.sum(pion**2, axis=-1, keepdims=True)), pion),
        axis=-1,
    )
    fixed = np.zeros(q.shape[:3], dtype=bool)
    if boundary == "fixed_vacuum":
        fixed[[0, -1], :, :] = True
        fixed[:, [0, -1], :] = True
        fixed[:, :, [0, -1]] = True

    rng = np.random.default_rng(8421)
    raw_velocity = rng.normal(0.0, 0.015, size=q.shape)
    velocity = raw_velocity - np.sum(
        raw_velocity * q, axis=-1, keepdims=True
    ) * q
    velocity[fixed] = 0.0
    field = SU2GridField(q, spacing=spacing, boundary=boundary)
    f_pi, e, damping = 1.2, 0.85, 0.17
    active = ~fixed
    acceleration, _, _, _ = lorentzian_module._acceleration_and_dissipation(
        field,
        velocity,
        f_pi=f_pi,
        e=e,
        damping=damping,
        fixed_mask=fixed,
        active=active,
        cell_volume=float(np.prod(spacing)),
    )

    site = (2, 2, 2)
    delta_t = 2.0e-5
    q_time_plus = _geodesic_position(q, velocity, delta_t)
    q_time_minus = _geodesic_position(q, velocity, -delta_t)
    momentum_time_derivative = (
        _independent_momentum(
            q_time_plus, velocity, spacing, boundary, f_pi, e
        )
        - _independent_momentum(
            q_time_minus, velocity, spacing, boundary, f_pi, e
        )
    ) / (2.0 * delta_t)
    momentum_time_derivative += _independent_momentum(
        q, acceleration, spacing, boundary, f_pi, e
    )
    momentum = _independent_momentum(q, velocity, spacing, boundary, f_pi, e)
    residual = momentum_time_derivative + damping * momentum

    epsilon = 2.0e-5
    checked_directions = 0
    for component in range(4):
        direction = np.eye(4)[component] - q[site][component] * q[site]
        if np.linalg.norm(direction) < 1.0e-8:
            continue
        q_plus = _great_circle_perturbation(q, site, direction, epsilon)
        q_minus = _great_circle_perturbation(q, site, direction, -epsilon)
        partial_lagrangian = (
            _independent_lagrangian(
                q_plus, velocity, spacing, boundary, f_pi, e
            )
            - _independent_lagrangian(
                q_minus, velocity, spacing, boundary, f_pi, e
            )
        ) / (2.0 * epsilon)
        np.testing.assert_allclose(
            float(np.dot(residual[site], direction)),
            partial_lagrangian,
            rtol=3.0e-4,
            atol=2.0e-6,
        )
        checked_directions += 1
    assert checked_directions >= 3

