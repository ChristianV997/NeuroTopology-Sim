"""Deterministic synthetic tests for SU(2) relaxation sweeps."""

import builtins
import json
import re

import numpy as np
import pytest

import field_theory.su2.parameter_sweep as parameter_sweep
from field_theory.su2 import SU2GridField
from field_theory.su2.parameter_sweep import (
    MAX_SWEEP_CANDIDATE_ATTEMPTS,
    MAX_SWEEP_POINTS,
    NearestNeighborSweepSpec,
    run_nearest_neighbor_sweep,
)
from field_theory.su2.sweep_visualization import (
    SweepVisualizationUnavailable,
    plot_nearest_neighbor_sweep,
)


def _small_periodic_field() -> SU2GridField:
    nx, ny, nz = 5, 4, 4
    x, y, z = np.meshgrid(
        np.arange(nx) / nx,
        np.arange(ny) / ny,
        np.arange(nz) / nz,
        indexing="ij",
    )
    phase = 0.25 * np.sin(2.0 * np.pi * x) + 0.1 * np.cos(2.0 * np.pi * y)
    values = np.zeros((nx, ny, nz, 4), dtype=np.float64)
    values[..., 0] = np.cos(phase)
    values[..., 1] = np.sin(phase)
    return SU2GridField(values, spacing=(0.4, 0.5, 0.5), boundary="periodic")


def _spec() -> NearestNeighborSweepSpec:
    return NearestNeighborSweepSpec(
        inverse_length_scale_values=(0.8, 1.0),
        energy_prefactor_values=(0.9,),
        initial_dimensionless_step_values=(1.0e-4,),
        max_iterations_values=(1,),
        dimensionless_gradient_tolerance=1.0e-12,
        max_backtracks=8,
    )


def test_sweep_json_is_deterministic_complete_and_finite(tmp_path):
    field = _small_periodic_field()
    first = run_nearest_neighbor_sweep(field, _spec())
    repeated = run_nearest_neighbor_sweep(field, _spec())

    serialized = first.to_json()
    assert serialized == repeated.to_json()
    written_path = first.write_json(tmp_path / "nested" / "sweep.json")
    assert written_path.read_text(encoding="utf-8") == serialized + "\n"
    payload = json.loads(
        serialized,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    assert payload["schema_version"] == "1.1.0"
    assert payload["algorithm_id"] == "su2-nearest-neighbor-relaxation-v1"
    assert payload["input"]["boundary"] == "periodic"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["input"]["checksum_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload["sweep_id"])
    assert len(payload["points"]) == 2
    assert payload["spec"]["planned_work"] == {
        "unit": "line_search_candidate_step",
        "upper_bound": 18,
        "limit": MAX_SWEEP_CANDIDATE_ATTEMPTS,
        "excludes_gradient_and_curvature_probes": True,
        "not_a_wall_time_or_memory_bound": True,
    }
    assert payload["convergence_claim"] == "NOT_ESTABLISHED"
    assert payload["claim_scope"] == "bounded_optimizer_behavior_only"
    assert payload["scientific_status"] == "NOT_ASSESSED"
    assert payload["energy_output"] == {
        "conversion": "model_energy=energy_prefactor*normalized_solver_energy",
        "unit_status": "not_assessed",
    }
    first_parameters = payload["points"][0]["parameters"]
    assert first_parameters["normalized_solver_f_pi"] == pytest.approx(np.sqrt(0.8))
    assert first_parameters["normalized_solver_e"] == pytest.approx(np.sqrt(0.8))
    for point in payload["points"]:
        assert point["execution_status"] == "completed"
        assert point["energy_history"]
        assert point["topological_charge_history"]
        assert np.all(np.isfinite(point["energy_history"]))
        assert np.all(np.isfinite(point["topological_charge_history"]))
        assert point["minimum_certified"] is False
        assert point["iterations"] <= 1
        assert "finite_difference_step" not in point["parameters"]


def test_sweep_order_and_parameter_metadata_follow_declared_grid_order():
    result = run_nearest_neighbor_sweep(_small_periodic_field(), _spec())
    assert [point.parameters.inverse_length_scale for point in result.points] == [0.8, 1.0]
    assert [point.point_id for point in result.points] == ["point-0000", "point-0001"]
    first = result.points[0].parameters
    assert first.energy_prefactor == 0.9
    assert first.f_pi == pytest.approx(np.sqrt(0.8 * 0.9))
    assert first.e == pytest.approx(np.sqrt(0.8 / 0.9))
    assert first.f_pi / first.e == pytest.approx(0.9)
    assert first.f_pi * first.e == pytest.approx(0.8)
    assert first.input_domain_extent == pytest.approx((2.0, 2.0, 2.0))
    assert first.dimensionless_spacing == pytest.approx((0.32, 0.4, 0.4))
    assert first.dimensionless_domain_extent == pytest.approx((1.6, 1.6, 1.6))
    assert result.points[1].parameters.dimensionless_spacing == pytest.approx(
        (0.4, 0.5, 0.5)
    )
    assert result.points[1].parameters.dimensionless_domain_extent == pytest.approx(
        (2.0, 2.0, 2.0)
    )
    assert first.initial_dimensionless_step == pytest.approx(1.0e-4)
    assert first.solver_initial_step == pytest.approx(1.0e-4)
    assert first.dimensionless_gradient_tolerance == pytest.approx(1.0e-12)
    assert first.solver_gradient_tolerance == pytest.approx(1.0e-12)
    assert first.normalized_solver_f_pi == pytest.approx(np.sqrt(0.8))
    assert first.normalized_solver_e == pytest.approx(np.sqrt(0.8))
    assert result.points[0].parameters.max_iterations == 1


def test_sweep_does_not_mutate_the_shared_input_field():
    field = _small_periodic_field()
    before = field.components.tobytes()
    run_nearest_neighbor_sweep(field, _spec())
    assert field.components.tobytes() == before
    with pytest.raises(ValueError):
        field.components.flat[0] = 0.0


def test_energy_prefactor_changes_only_energy_scale_at_fixed_dimensionless_geometry():
    field = _small_periodic_field()
    spec = NearestNeighborSweepSpec(
        inverse_length_scale_values=(1.0,),
        energy_prefactor_values=(1.0e-12, 0.25, 4.0),
        initial_dimensionless_step_values=(1.0e-4,),
        max_iterations_values=(3,),
        dimensionless_gradient_tolerance=1.0e-12,
        max_backtracks=8,
    )
    result = run_nearest_neighbor_sweep(field, spec)
    baseline = result.points[1]
    for point in result.points:
        assert point.parameters.dimensionless_spacing == baseline.parameters.dimensionless_spacing
        assert point.parameters.dimensionless_domain_extent == (
            baseline.parameters.dimensionless_domain_extent
        )
        np.testing.assert_allclose(
            np.asarray(point.energy_history) / point.parameters.energy_prefactor,
            np.asarray(baseline.energy_history) / baseline.parameters.energy_prefactor,
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        np.testing.assert_allclose(
            point.topological_charge_history,
            baseline.topological_charge_history,
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        assert point.final_field_checksum_sha256 == baseline.final_field_checksum_sha256
        assert point.iterations == baseline.iterations == 3
        assert point.termination == baseline.termination == "iteration_limit"
        assert point.stationarity_status == baseline.stationarity_status
        assert point.parameters.normalized_solver_f_pi == pytest.approx(1.0)
        assert point.parameters.normalized_solver_e == pytest.approx(1.0)


def test_energy_prefactor_preserves_trajectory_at_nonunit_inverse_length_scale():
    field = _small_periodic_field()
    spec = NearestNeighborSweepSpec(
        inverse_length_scale_values=(0.7,),
        energy_prefactor_values=(1.0e-12, 0.25, 4.0),
        initial_dimensionless_step_values=(1.0e-4,),
        max_iterations_values=(3,),
        dimensionless_gradient_tolerance=1.0e-12,
        max_backtracks=8,
    )
    result = run_nearest_neighbor_sweep(field, spec)
    baseline = result.points[1]

    # Lambda is held at a non-unit value; only mu changes here. No trajectory
    # invariance across distinct lambda values is asserted.
    for point in result.points:
        assert point.parameters.inverse_length_scale == pytest.approx(0.7)
        assert point.parameters.dimensionless_spacing == baseline.parameters.dimensionless_spacing
        assert point.parameters.dimensionless_domain_extent == (
            baseline.parameters.dimensionless_domain_extent
        )
        np.testing.assert_allclose(
            np.asarray(point.energy_history) / point.parameters.energy_prefactor,
            np.asarray(baseline.energy_history) / baseline.parameters.energy_prefactor,
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        np.testing.assert_allclose(
            point.topological_charge_history,
            baseline.topological_charge_history,
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        assert point.final_field_checksum_sha256 == baseline.final_field_checksum_sha256
        assert point.iterations == baseline.iterations == 3
        assert point.termination == baseline.termination == "iteration_limit"
        assert point.stationarity_status == baseline.stationarity_status
        assert point.parameters.normalized_solver_f_pi == pytest.approx(np.sqrt(0.7))
        assert point.parameters.normalized_solver_e == pytest.approx(np.sqrt(0.7))


def test_curvature_metadata_is_rescaled_with_model_energy_prefactor():
    values = np.zeros((3, 3, 3, 4), dtype=np.float64)
    values[..., 0] = 1.0
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    spec = NearestNeighborSweepSpec(
        inverse_length_scale_values=(1.0,),
        energy_prefactor_values=(1.0e-12, 1.0),
        max_iterations_values=(1,),
    )
    low_scale, unit_scale = run_nearest_neighbor_sweep(field, spec).points
    low_curvature = low_scale.curvature_diagnostics
    unit_curvature = unit_scale.curvature_diagnostics
    assert low_scale.termination == unit_scale.termination == "gradient_tolerance"
    assert low_curvature is not None and unit_curvature is not None
    assert low_curvature.assessment == unit_curvature.assessment
    assert low_curvature.negative_curvature_tolerance == pytest.approx(
        1.0e-12 * unit_curvature.negative_curvature_tolerance
    )
    assert low_curvature.most_negative_directional_curvature == pytest.approx(
        1.0e-12 * unit_curvature.most_negative_directional_curvature
    )


def test_model_energy_rescaling_rejects_underflow_and_overflow():
    with pytest.raises(FloatingPointError, match="underflowed"):
        parameter_sweep._rescale_energy(1.0e-320, 1.0e-12, "test energy")
    with pytest.raises(FloatingPointError, match="not finite"):
        parameter_sweep._rescale_energy(1.0e308, 1.0e12, "test energy")


def test_model_energy_rescaling_rejects_nonzero_subnormal_outputs():
    with pytest.raises(FloatingPointError, match="subnormal"):
        parameter_sweep._rescale_energy(1.0e-300, 1.0e-10, "test energy")


def test_sweep_rejects_cartesian_product_above_fixed_point_limit():
    with pytest.raises(ValueError, match="sweep exceeds the maximum point count"):
        too_many = NearestNeighborSweepSpec(
            inverse_length_scale_values=tuple(
                1.0 + index for index in range(16)
            ),
            energy_prefactor_values=tuple(1.0 + index for index in range(17)),
            initial_dimensionless_step_values=(1.0e-4,),
            max_iterations_values=(1,),
        )
        run_nearest_neighbor_sweep(_small_periodic_field(), too_many)


def test_sweep_bounds_axis_materialization_before_cartesian_product_check():
    consumed = 0

    def unbounded_values():
        nonlocal consumed
        while True:
            consumed += 1
            yield float(consumed)

    with pytest.raises(ValueError, match="maximum axis size"):
        NearestNeighborSweepSpec(inverse_length_scale_values=unbounded_values())
    assert consumed == MAX_SWEEP_POINTS + 1


def test_sweep_work_budget_rejects_before_solver_calls(monkeypatch):
    calls = []

    def solver_spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("solver must not run for an over-budget sweep")

    monkeypatch.setattr(parameter_sweep, "relax_skyrme_field_nearest_neighbor", solver_spy)
    with pytest.raises(ValueError, match="candidate-attempt work budget"):
        NearestNeighborSweepSpec(
            max_iterations_values=(MAX_SWEEP_CANDIDATE_ATTEMPTS,),
            max_backtracks=1,
        )
    assert calls == []


def test_sweep_work_budget_accepts_exact_limit():
    spec = NearestNeighborSweepSpec(
        max_iterations_values=(MAX_SWEEP_CANDIDATE_ATTEMPTS,),
        max_backtracks=0,
    )
    assert spec.candidate_attempt_upper_bound == MAX_SWEEP_CANDIDATE_ATTEMPTS


def test_runner_rechecks_work_budget_before_solver_calls(monkeypatch):
    calls = []

    def solver_spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("solver must not run for an over-budget sweep")

    monkeypatch.setattr(parameter_sweep, "relax_skyrme_field_nearest_neighbor", solver_spy)
    spec = _spec()
    object.__setattr__(spec, "max_iterations_values", (MAX_SWEEP_CANDIDATE_ATTEMPTS,))
    object.__setattr__(spec, "max_backtracks", 1)
    with pytest.raises(ValueError, match="candidate-attempt work budget"):
        run_nearest_neighbor_sweep(_small_periodic_field(), spec)
    assert calls == []


def test_plot_reports_missing_optional_matplotlib_without_importing_it_eagerly(
    monkeypatch, tmp_path
):
    result = run_nearest_neighbor_sweep(_small_periodic_field(), _spec())
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError("synthetic optional dependency absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    path = tmp_path / "sweep.png"
    with pytest.raises(SweepVisualizationUnavailable, match="optional matplotlib"):
        plot_nearest_neighbor_sweep(result, path)
    assert not path.exists()


def test_plot_is_headless_when_optional_matplotlib_is_available(tmp_path):
    pytest.importorskip("matplotlib")
    result = run_nearest_neighbor_sweep(_small_periodic_field(), _spec())
    path = tmp_path / "plots" / "sweep.png"
    returned = plot_nearest_neighbor_sweep(result, path)
    assert returned == path
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
