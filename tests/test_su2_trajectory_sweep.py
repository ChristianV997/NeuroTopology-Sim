import json
from copy import copy
from dataclasses import replace

import numpy as np
import pytest

from field_theory.su2 import SU2GridField
from field_theory.su2.lorentzian import evolve_lorentzian_skyrme
from field_theory.su2.trajectory_sweep import (
    LorentzianSweepSpec,
    run_lorentzian_sweep,
)
from field_theory.su2.trajectory_visualization import (
    build_lorentzian_sweep_plot_data,
    build_lorentzian_trajectory_plot_data,
    plot_lorentzian_field_slices,
    plot_lorentzian_sweep,
    plot_lorentzian_trajectory,
)


def _field_and_velocity(size=3, spacing=(1.0, 1.0, 1.0)):
    coordinate = np.arange(size, dtype=float)
    theta = 0.2 * np.sin(2.0 * np.pi * coordinate / size)[:, None, None]
    theta = np.broadcast_to(theta, (size, size, size)).copy()
    components = np.zeros((size, size, size, 4), dtype=float)
    components[..., 0] = np.cos(theta)
    components[..., 1] = np.sin(theta)
    velocity = np.zeros_like(components)
    velocity[..., 0] = -0.03 * np.sin(theta)
    velocity[..., 1] = 0.03 * np.cos(theta)
    return (
        SU2GridField(components, spacing=spacing, boundary="periodic"),
        velocity,
    )


def _compact_hedgehog_field_and_velocity(spacing=1.0):
    """Small periodic 3-D texture with vacuum at the boundary seam."""
    size = 17
    coordinate = np.arange(size, dtype=float) - size // 2
    x, y, z = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")
    radius = np.sqrt(x * x + y * y + z * z)
    profile = np.pi * (1.0 - np.minimum(radius / 5.0, 1.0)) ** 3
    scaled_radius = np.minimum(radius / 5.0, 1.0)
    profile *= 1.0 + 2.0 * scaled_radius + 3.0 * scaled_radius**2

    radial = np.zeros_like(radius)
    nonzero = radius > 0.0
    radial[nonzero] = np.sin(profile[nonzero]) / radius[nonzero]
    components = np.stack(
        (np.cos(profile), radial * x, radial * y, radial * z), axis=-1
    )
    components[radius == 0.0] = (-1.0, 0.0, 0.0, 0.0)
    field = SU2GridField(
        components,
        spacing=(spacing, spacing, spacing),
        boundary="periodic",
    )

    tangent = np.stack(
        (
            -components[..., 1],
            components[..., 0],
            np.zeros_like(radius),
            np.zeros_like(radius),
        ),
        axis=-1,
    )
    velocity = 0.03 * (1.0 - components[..., 0] ** 2)[..., None] * tangent
    return field, velocity


def test_dt_sweep_uses_common_final_time_and_deterministic_strict_json(tmp_path):
    field, velocity = _field_and_velocity()
    spec = LorentzianSweepSpec(
        dt_values=(0.001, 0.002),
        final_time=0.002,
    )
    first = run_lorentzian_sweep(field, velocity, spec)
    second = run_lorentzian_sweep(field, velocity, spec)

    assert spec.rk_stage_site_work(27) == 4 * 27 * (2 + 1)
    assert spec.record_site_visits(27) == 27 * (3 + 2)
    assert first.points[0].dimensionless_dt_proxy == pytest.approx(0.001)
    assert first.points[0].inverse_length_scale_proxy == pytest.approx(1.0)
    assert first.points[0].dimensionless_final_time_proxy == pytest.approx(0.002)
    assert first.points[0].dimensionless_initial_velocity_rms_proxy == pytest.approx(0.03)
    assert first.points[0].dimensionless_initial_velocity_max_proxy == pytest.approx(0.03)
    assert first.sweep_id == second.sweep_id
    assert first.to_json() == second.to_json()
    parsed = json.loads(first.to_json())
    assert parsed["scientific_status"] == "NOT_ASSESSED"
    assert parsed["convergence_claim"] == "NOT_ESTABLISHED"
    assert parsed["field_snapshots_included"] is False
    assert len(first.points) == 2
    for point in first.points:
        assert point.time_history[0] == 0.0
        assert point.time_history[-1] == pytest.approx(spec.final_time)
        assert len(point.time_history) <= spec.max_saved_snapshots_per_point
        history_lengths = {
            len(point.energy_sigma_history),
            len(point.energy_skyrme_history),
            len(point.kinetic_sigma_history),
            len(point.kinetic_skyrme_history),
            len(point.total_energy_history),
            len(point.dissipated_energy_history),
            len(point.energy_balance_residual_history),
            len(point.approximate_charge_history),
            len(point.time_kinetic_min_eigenvalue_history),
            len(point.time_kinetic_max_condition_history),
        }
        assert history_lengths == {len(point.time_history)}
        assert point.hyperbolicity_status == "not_certified"

    written = first.write_json(tmp_path / "nested" / "sweep.json")
    assert written.read_text(encoding="utf-8") == first.to_json() + "\n"



def test_equal_inverse_length_scale_has_expected_energy_prefactor_covariance():
    field, velocity = _field_and_velocity()
    first = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=3, save_every=1,
        f_pi=1.0, e=1.0, damping=0.1,
    )
    second = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=3, save_every=1,
        f_pi=2.0, e=0.5, damping=0.1,
    )

    for field_a, field_b in zip(first.fields, second.fields):
        np.testing.assert_allclose(
            field_a.components, field_b.components, rtol=1e-10, atol=1e-12
        )
    for velocity_a, velocity_b in zip(first.velocities, second.velocities):
        np.testing.assert_allclose(
            velocity_a, velocity_b, rtol=1e-10, atol=1e-12
        )
    np.testing.assert_allclose(
        second.total_energy_history,
        4.0 * np.asarray(first.total_energy_history),
        rtol=1e-10,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        second.dissipated_energy_history,
        4.0 * np.asarray(first.dissipated_energy_history),
        rtol=1e-10,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        second.approximate_charge_history,
        first.approximate_charge_history,
        rtol=1e-10,
        atol=1e-12,
    )


def test_cross_inverse_length_scale_mapped_histories_are_covariant():
    base_field, base_velocity = _compact_hedgehog_field_and_velocity()
    scaled_field, scaled_velocity = _compact_hedgehog_field_and_velocity(
        spacing=0.5
    )
    np.testing.assert_array_equal(
        scaled_field.components, base_field.components
    )
    scaled_velocity *= 2.0

    # lambda=e*f_pi doubles, mu=f_pi/e doubles: preserve dimensionless
    # geometry and horizon by halving lengths and times, and scale v,gamma
    # with lambda. The finite-grid classical trajectory should map covariantly up to floating-point error.
    base = evolve_lorentzian_skyrme(
        base_field,
        base_velocity,
        dt=0.001,
        steps=3,
        save_every=1,
        f_pi=1.0,
        e=1.0,
        damping=0.1,
    )
    scaled = evolve_lorentzian_skyrme(
        scaled_field,
        scaled_velocity,
        dt=0.0005,
        steps=3,
        save_every=1,
        f_pi=2.0,
        e=1.0,
        damping=0.2,
    )

    np.testing.assert_allclose(
        scaled.time_history,
        np.asarray(base.time_history) / 2.0,
        rtol=1e-12,
        atol=1e-15,
    )
    for field_base, field_scaled in zip(base.fields, scaled.fields):
        np.testing.assert_allclose(
            field_scaled.components,
            field_base.components,
            rtol=1e-10,
            atol=1e-12,
        )
    for velocity_base, velocity_scaled in zip(base.velocities, scaled.velocities):
        np.testing.assert_allclose(
            velocity_scaled,
            2.0 * velocity_base,
            rtol=1e-10,
            atol=1e-12,
        )

    for name in (
        "energy_sigma_history",
        "energy_skyrme_history",
        "kinetic_sigma_history",
        "kinetic_skyrme_history",
        "total_energy_history",
        "dissipated_energy_history",
        "energy_balance_residual_history",
    ):
        np.testing.assert_allclose(
            getattr(scaled, name),
            2.0 * np.asarray(getattr(base, name)),
            rtol=1e-9,
            atol=1e-12,
        )
    # This compact 3-D texture gives a nonzero but noninteger finite-grid
    # charge; only scale covariance, not quantization or conservation, is tested.
    assert abs(base.approximate_charge_history[0]) > 0.5
    assert abs(scaled.approximate_charge_history[0]) > 0.5
    np.testing.assert_allclose(
        scaled.approximate_charge_history,
        base.approximate_charge_history,
        rtol=1e-10,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        scaled.time_kinetic_min_eigenvalue_history,
        4.0 * np.asarray(base.time_kinetic_min_eigenvalue_history),
        rtol=1e-9,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        scaled.time_kinetic_max_condition_history,
        base.time_kinetic_max_condition_history,
        rtol=1e-9,
        atol=1e-12,
    )
    assert scaled.cell_volume == pytest.approx(base.cell_volume / 8.0)
    assert scaled.linearized_cfl_indicator == pytest.approx(
        base.linearized_cfl_indicator
    )


def test_work_budget_rejects_before_any_solver_call(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    spec = LorentzianSweepSpec(
        f_pi_values=(1.0, 1.1),
        dt_values=(0.001,),
        final_time=0.002,
        max_total_rk_stage_site_evaluations=431,
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("work-budget preflight must reject before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="max_total_rk_stage_site_evaluations"):
        run_lorentzian_sweep(field, velocity, spec)


def test_record_site_visit_budget_rejects_before_any_solver_call(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    spec = LorentzianSweepSpec(
        damping_values=(0.0, 0.1),
        dt_values=(0.001,),
        final_time=0.002,
        max_total_record_site_visits=161,
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("record-site preflight must reject before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="max_total_record_site_visits"):
        run_lorentzian_sweep(field, velocity, spec)


def test_damping_step_limit_rejects_before_any_solver_call(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    spec = LorentzianSweepSpec(
        damping_values=(30.0,),
        dt_values=(0.1,),
        final_time=0.1,
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("damping-step preflight must reject before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="max_linearized_damping_step"):
        run_lorentzian_sweep(field, velocity, spec)


def test_snapshot_memory_budget_rejects_before_any_solver_call(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    spec = LorentzianSweepSpec(
        dt_values=(0.001,),
        final_time=0.1,
        max_snapshot_bytes_per_point=1,
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("snapshot-memory preflight must reject before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="max_snapshot_bytes_per_point"):
        run_lorentzian_sweep(field, velocity, spec)


def test_cfl_preflight_rejects_before_any_solver_call(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity(spacing=(0.1, 0.1, 0.1))
    spec = LorentzianSweepSpec(
        dt_values=(0.1,),
        final_time=0.1,
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("CFL preflight must reject before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="max_linearized_cfl"):
        run_lorentzian_sweep(field, velocity, spec)


def test_invalid_velocity_is_rejected_before_evolution(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    bad = velocity.copy()
    bad[..., 0] += 0.1

    def fail_if_called(*args, **kwargs):
        pytest.fail("invalid velocity must be rejected before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="tangent to S3"):
        run_lorentzian_sweep(
            field,
            bad,
            LorentzianSweepSpec(dt_values=(0.001,), final_time=0.002),
        )




def test_timestep_endpoint_tolerance_matches_preflight_ratio_tolerance():
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(dt_values=(0.33333333334,), final_time=1.0),
    )
    point = result.points[0]
    assert point.steps == 3
    assert point.time_history[-1] == pytest.approx(1.00000000002, rel=1e-12)



def test_underflowed_positive_scale_proxy_rejected_before_evolution(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity(spacing=(2e-308, 1.0, 1.0))

    def fail_if_called(*args, **kwargs):
        pytest.fail("underflowed scale proxy must be rejected before evolution")

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", fail_if_called)
    with pytest.raises(ValueError, match="underflowed to zero"):
        run_lorentzian_sweep(
            field,
            velocity,
            LorentzianSweepSpec(
                f_pi_values=(1e-10,),
                e_values=(1e-10,),
                dt_values=(1e-308,),
                final_time=1e-308,
            ),
        )


@pytest.mark.parametrize(("corruption", "error_fragment"), [("history", "non-finite"), ("final_field", "non-finite"), ("string_history", "numeric")])
def test_invalid_solver_output_is_rejected_with_point_id(monkeypatch, corruption, error_fragment):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    original_solver = evolve_lorentzian_skyrme

    def corrupting_solver(*args, **kwargs):
        trajectory = original_solver(*args, **kwargs)
        if corruption == "history":
            values = list(trajectory.total_energy_history)
            values[-1] = float("nan")
            return replace(trajectory, total_energy_history=tuple(values))
        if corruption == "string_history":
            values = list(trajectory.total_energy_history)
            values[-1] = str(values[-1])
            return replace(trajectory, total_energy_history=tuple(values))
        bad_field = copy(trajectory.fields[-1])
        components = np.array(bad_field.components, copy=True)
        components[0, 0, 0, 0] = np.nan
        object.__setattr__(bad_field, "components", components)
        return replace(
            trajectory,
            fields=(*trajectory.fields[:-1], bad_field),
        )

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", corrupting_solver)
    with pytest.raises(RuntimeError, match="point-0000") as error:
        run_lorentzian_sweep(
            field,
            velocity,
            LorentzianSweepSpec(dt_values=(0.001,), final_time=0.001),
        )
    assert isinstance(error.value.__cause__, ValueError)
    assert error_fragment in str(error.value.__cause__)



@pytest.mark.parametrize("metadata_name", ["steps", "save_every"])
def test_solver_output_rejects_boolean_integer_metadata(monkeypatch, metadata_name):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    original_solver = sweep_module.evolve_lorentzian_skyrme

    def boolean_metadata_solver(*args, **kwargs):
        trajectory = original_solver(*args, **kwargs)
        return replace(trajectory, **{metadata_name: True})

    monkeypatch.setattr(
        sweep_module, "evolve_lorentzian_skyrme", boolean_metadata_solver
    )
    with pytest.raises(RuntimeError, match="point-0000") as error:
        run_lorentzian_sweep(
            field,
            velocity,
            LorentzianSweepSpec(dt_values=(0.001,), final_time=0.001),
        )
    assert isinstance(error.value.__cause__, ValueError)
    assert "metadata" in str(error.value.__cause__)


def test_sweep_plot_data_requires_single_parameter_axis():
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(
            damping_values=(0.0, 0.1),
            dt_values=(0.001, 0.002),
            final_time=0.002,
        ),
    )
    with pytest.raises(ValueError, match="one varying parameter"):
        build_lorentzian_sweep_plot_data(result, x_parameter="damping")


def test_sweep_plot_data_is_dimensionless_and_axis_keyed():
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(
            damping_values=(0.0, 0.1),
            dt_values=(0.001,),
            final_time=0.002,
        ),
    )
    data = build_lorentzian_sweep_plot_data(result, x_parameter="damping")
    assert data["x_parameter"] == "damping"
    assert data["x_values"] == [0.0, 0.1]
    assert [curve["x_value"] for curve in data["curves"]] == [0.0, 0.1]
    assert data["claim_scope"] == "dimensionless_finite_grid_diagnostics_only"


@pytest.mark.parametrize(
    ("metadata_name", "bad_value"),
    [
        ("dt", "0.001"),
        ("dt", float("nan")),
        ("dt", 0.0),
        ("steps", True),
        ("steps", 2.0),
        ("save_every", False),
        ("save_every", 3),
        ("damping", False),
        ("damping", -0.1),
        ("linearized_cfl_indicator", True),
        ("linearized_cfl_indicator", float("inf")),
    ],
)
def test_trajectory_plot_data_rejects_coerced_metadata(metadata_name, bad_value):
    field, velocity = _field_and_velocity()
    trajectory = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=2, save_every=1
    )
    malformed = replace(trajectory, **{metadata_name: bad_value})
    with pytest.raises(ValueError):
        build_lorentzian_trajectory_plot_data(malformed)


@pytest.mark.parametrize(
    ("metadata_name", "bad_value"),
    [
        ("f_pi", "1.0"),
        ("f_pi", float("nan")),
        ("e", True),
        ("e", -1.0),
        ("damping", False),
        ("damping", -0.1),
        ("dt", "0.001"),
        ("dt", 0.0),
    ],
)
def test_sweep_plot_data_rejects_coerced_point_metadata(metadata_name, bad_value):
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(
            damping_values=(0.0, 0.1), dt_values=(0.001,), final_time=0.002
        ),
    )
    malformed_point = replace(result.points[0], **{metadata_name: bad_value})
    malformed = replace(result, points=(malformed_point, result.points[1]))
    with pytest.raises(ValueError, match="real numeric scalar"):
        build_lorentzian_sweep_plot_data(malformed, x_parameter="damping")


@pytest.mark.parametrize("plot_kind", ["trajectory", "sweep"])
def test_plot_data_rejects_off_cadence_time_samples(plot_kind):
    field, velocity = _field_and_velocity()
    if plot_kind == "trajectory":
        trajectory = evolve_lorentzian_skyrme(
            field, velocity, dt=0.001, steps=2, save_every=1
        )
        malformed = replace(
            trajectory, time_history=(0.0, 0.0005, 0.002)
        )
        with pytest.raises(ValueError, match="dt, steps, and save_every"):
            build_lorentzian_trajectory_plot_data(malformed)
        return

    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(dt_values=(0.001,), final_time=0.002),
    )
    point = replace(result.points[0], time_history=(0.0, 0.0005, 0.002))
    malformed_result = replace(result, points=(point,))
    with pytest.raises(ValueError, match="dt, steps, and save_every"):
        build_lorentzian_sweep_plot_data(
            malformed_result, x_parameter="dt"
        )


def test_sweep_plot_data_rejects_point_final_time_mismatch():
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(dt_values=(0.001,), final_time=0.002),
    )
    malformed_point = replace(result.points[0], final_time=0.003)
    malformed = replace(result, points=(malformed_point,))
    with pytest.raises(ValueError, match="does not match its spec"):
        build_lorentzian_sweep_plot_data(malformed, x_parameter="dt")


def test_trajectory_plot_data_uses_explicit_diagnostic_labels():
    field, velocity = _field_and_velocity()
    trajectory = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=2, save_every=1
    )
    data = build_lorentzian_trajectory_plot_data(trajectory)
    assert data["hyperbolicity_status"] == "not_certified"
    assert data["charge_label"] == "approximate finite-grid topological charge"
    assert data["energy_unit_status"] == "not_assessed"
    assert len(data["time"]) == len(data["total_energy"])


def test_headless_plot_renderers_write_files_when_matplotlib_is_available(
    tmp_path,
):
    pytest.importorskip("matplotlib")
    field, velocity = _field_and_velocity()
    trajectory = evolve_lorentzian_skyrme(
        field, velocity, dt=0.001, steps=2, save_every=1
    )
    sweep = run_lorentzian_sweep(
        field,
        velocity,
        LorentzianSweepSpec(
            damping_values=(0.0, 0.1),
            dt_values=(0.001,),
            final_time=0.002,
        ),
    )

    trajectory_png = plot_lorentzian_trajectory(
        trajectory, tmp_path / "trajectory.png"
    )
    slices_png = plot_lorentzian_field_slices(
        trajectory, tmp_path / "slices.png", component=1, slice_axis=2
    )
    sweep_png = plot_lorentzian_sweep(
        sweep, tmp_path / "sweep.png", x_parameter="damping"
    )
    assert trajectory_png.is_file() and trajectory_png.stat().st_size > 0
    assert slices_png.is_file() and slices_png.stat().st_size > 0
    assert sweep_png.is_file() and sweep_png.stat().st_size > 0

def test_solver_output_times_must_match_requested_save_cadence(monkeypatch):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    original_solver = evolve_lorentzian_skyrme

    def shifted_time_solver(*args, **kwargs):
        trajectory = original_solver(*args, **kwargs)
        return replace(trajectory, time_history=(0.0, 0.002, 0.005))

    monkeypatch.setattr(sweep_module, "evolve_lorentzian_skyrme", shifted_time_solver)
    spec = LorentzianSweepSpec(
        dt_values=(0.001,), final_time=0.005, max_saved_snapshots_per_point=3
    )
    with pytest.raises(RuntimeError, match="point-0000") as error:
        run_lorentzian_sweep(field, velocity, spec)
    assert "save cadence" in str(error.value.__cause__)


@pytest.mark.parametrize(
    "bad_history",
    [("0.0", "1.0", "2.0"), (False, True, False), (0.0, True, 2.0)],
    ids=["numeric-strings", "booleans", "mixed-boolean"],
)
def test_trajectory_plot_data_rejects_coerced_history_types(bad_history):
    field, velocity = _field_and_velocity()
    trajectory = evolve_lorentzian_skyrme(field, velocity, dt=0.001, steps=2, save_every=1)
    malformed = replace(trajectory, total_energy_history=bad_history)
    with pytest.raises(ValueError, match="finite numeric history"):
        build_lorentzian_trajectory_plot_data(malformed)


@pytest.mark.parametrize(
    "bad_history",
    [("0.0", "1.0", "2.0"), (False, True, False), (0.0, True, 2.0)],
    ids=["numeric-strings", "booleans", "mixed-boolean"],
)
def test_sweep_plot_data_rejects_coerced_history_types(bad_history):
    field, velocity = _field_and_velocity()
    result = run_lorentzian_sweep(
        field, velocity,
        LorentzianSweepSpec(damping_values=(0.0, 0.1), dt_values=(0.001,), final_time=0.002),
    )
    points = (replace(result.points[0], total_energy_history=bad_history), result.points[1])
    malformed = replace(result, points=points)
    with pytest.raises(ValueError, match="finite numeric history"):
        build_lorentzian_sweep_plot_data(malformed, x_parameter="damping")
