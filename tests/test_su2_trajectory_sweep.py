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


@pytest.mark.parametrize("corruption", ["history", "final_field"])
def test_nonfinite_solver_output_is_rejected_with_point_id(monkeypatch, corruption):
    import field_theory.su2.trajectory_sweep as sweep_module

    field, velocity = _field_and_velocity()
    original_solver = evolve_lorentzian_skyrme

    def corrupting_solver(*args, **kwargs):
        trajectory = original_solver(*args, **kwargs)
        if corruption == "history":
            values = list(trajectory.total_energy_history)
            values[-1] = float("nan")
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
    assert "non-finite" in str(error.value.__cause__)



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
