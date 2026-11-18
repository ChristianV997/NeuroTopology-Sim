"""Synthetic tests for constrained relaxation to explicit cold release."""
from __future__ import annotations

import json

import numpy as np
import pytest

from field_theory.su2 import SU2GridField
import field_theory.su2.relaxation_release as release_module
from field_theory.su2.relaxation_release import run_relaxation_then_cold_release


def _anchored_seed():
    shape = (7, 7, 7)
    values = np.zeros(shape + (4,), dtype=np.float64)
    values[..., 0] = 1.0
    center = (3, 3, 3)
    angle = 0.3
    values[center] = (np.cos(angle), np.sin(angle), 0.0, 0.0)
    field = SU2GridField(values, spacing=(0.7, 0.8, 0.9), boundary="fixed_vacuum")
    mask = np.zeros(shape, dtype=bool)
    mask[2:5, 2:5, 2:5] = True
    return field, mask


def _run(field, mask, **kwargs):
    params = {
        "fixed_mask": mask,
        "max_iterations": 2,
        "max_backtracks": 2,
        "dt": 1.0e-4,
        "steps": 2,
        "save_every": 1,
    }
    params.update(kwargs)
    return run_relaxation_then_cold_release(field, **params)


def test_real_optimizer_to_lorentzian_cold_release_path_is_finite_and_compact():
    field, mask = _anchored_seed()
    result = _run(field, mask, f_pi=1.2, e=0.9, anchor_policy="cold_release")

    assert result.status == "COMPLETED"
    assert result.relaxation_termination == "gradient_tolerance"
    assert result.relaxation_stationarity_status == "first_order_stationary"
    assert result.relaxation_minimum_certified is False
    assert result.anchor_policy == "cold_release"
    assert result.fixed_site_count == 27
    assert result.released_anchor_count == 27
    assert result.initial_velocity_max_abs == 0.0
    assert result.outer_boundary_policy == "fixed_vacuum_outer_faces_remain_clamped"
    assert result.time_history == (0.0, 1.0e-4, 2.0e-4)
    assert result.initial_static_potential_energy == result.initial_lorentzian_total_energy
    assert result.initial_energy_difference == 0.0
    assert len(result.total_energy_history) == 3
    assert len(result.potential_energy_history) == 3
    assert len(result.kinetic_energy_history) == 3
    assert len(result.dissipated_energy_history) == 3
    assert len(result.energy_balance_residual_history) == 3
    assert len(result.approximate_charge_history) == 3
    assert result.approximate_charge_interpretation.startswith("approximate lattice degree")
    assert result.scientific_pass is False
    assert result.data_mode == "synthetic_dimensionless"
    payload = json.loads(result.to_json())
    assert payload["status"] == "COMPLETED"
    assert "fields" not in payload
    assert "snapshots" not in payload


def test_cold_release_drops_only_interior_anchor_mask_and_keeps_outer_faces(monkeypatch):
    field, mask = _anchored_seed()
    real_evolve = release_module.evolve_lorentzian_skyrme
    seen = {}

    def capture_and_run(field, velocity, **kwargs):
        seen["mask"] = kwargs["fixed_mask"]
        trajectory = real_evolve(field, velocity, **kwargs)
        seen["final"] = trajectory.fields[-1]
        return trajectory

    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", capture_and_run)
    result = _run(field, mask, anchor_policy="cold_release")

    assert result.status == "COMPLETED"
    assert seen["mask"] is None
    final = seen["final"].components
    vacuum = np.array([1.0, 0.0, 0.0, 0.0])
    assert np.array_equal(final[0, :, :, :], np.broadcast_to(vacuum, final[0, :, :, :].shape))
    assert np.array_equal(final[-1, :, :, :], np.broadcast_to(vacuum, final[-1, :, :, :].shape))
    assert np.allclose(np.linalg.norm(final, axis=-1), 1.0, rtol=0.0, atol=1e-12)



def test_cold_release_moves_while_retained_anchor_stays_fixed(monkeypatch):
    field, mask = _anchored_seed()
    field = SU2GridField(
        field.components, spacing=(1.0, 1.0, 1.0), boundary="fixed_vacuum"
    )
    real_evolve = release_module.evolve_lorentzian_skyrme
    runs = {}

    def capture_and_run(field, velocity, **kwargs):
        policy = "released" if kwargs["fixed_mask"] is None else "retained"
        trajectory = real_evolve(field, velocity, **kwargs)
        runs[policy] = {
            "mask": kwargs["fixed_mask"],
            "velocity": np.array(velocity, copy=True),
            "initial": trajectory.fields[0].components.copy(),
            "final": trajectory.fields[-1].components.copy(),
        }
        return trajectory

    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", capture_and_run)
    common = {
        "f_pi": 1.0,
        "e": 1.0,
        "dt": 1.0e-3,
        "steps": 1,
        "save_every": 1,
        "damping": 0.0,
    }
    released = _run(field, mask, anchor_policy="cold_release", **common)
    retained = _run(field, mask, anchor_policy="retain", **common)

    assert released.status == retained.status == "COMPLETED"
    assert released.released_anchor_count == 27
    assert retained.released_anchor_count == 0
    assert runs["released"]["mask"] is None
    np.testing.assert_array_equal(runs["retained"]["mask"], mask)
    np.testing.assert_array_equal(runs["released"]["velocity"], np.zeros_like(field.components))
    np.testing.assert_array_equal(runs["retained"]["velocity"], np.zeros_like(field.components))

    center = (3, 3, 3)
    released_motion = np.linalg.norm(
        runs["released"]["final"][center] - runs["released"]["initial"][center]
    )
    assert released_motion > 1.0e-9
    np.testing.assert_array_equal(
        runs["retained"]["final"][mask], runs["retained"]["initial"][mask]
    )

    vacuum = np.array([1.0, 0.0, 0.0, 0.0])
    for policy in ("released", "retained"):
        final = runs[policy]["final"]
        for axis in range(3):
            for side in (0, -1):
                face = np.take(final, side, axis=axis)
                assert np.array_equal(face, np.broadcast_to(vacuum, face.shape))
        assert np.allclose(np.linalg.norm(final, axis=-1), 1.0, rtol=0.0, atol=1e-12)

def test_retain_policy_passes_the_same_interior_mask_to_evolution(monkeypatch):
    field, mask = _anchored_seed()
    real_evolve = release_module.evolve_lorentzian_skyrme
    seen = {}

    def capture_and_run(field, velocity, **kwargs):
        seen["mask"] = np.array(kwargs["fixed_mask"], copy=True)
        return real_evolve(field, velocity, **kwargs)

    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", capture_and_run)
    result = _run(field, mask, anchor_policy="retain")

    assert result.status == "COMPLETED"
    assert result.anchor_policy == "retain"
    assert result.released_anchor_count == 0
    np.testing.assert_array_equal(seen["mask"], mask)


def test_unconverged_relaxation_withholds_evolution_by_default(monkeypatch):
    field, _ = _anchored_seed()
    fixed_mask = np.zeros(field.components.shape[:3], dtype=bool)
    fixed_mask[1, 3, 3] = True

    def fail_if_called(*args, **kwargs):
        pytest.fail("nonconverged relaxation must not evolve by default")

    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", fail_if_called)
    result = run_relaxation_then_cold_release(
        field,
        fixed_mask=fixed_mask,
        max_iterations=1,
        gradient_tolerance=1.0e-15,
        dt=1.0e-4,
        steps=2,
    )
    assert result.status == "NOT_CONVERGED"
    assert result.trajectory_termination == "not_run"
    assert result.time_history == ()
    assert result.final_field_sha256 is None
    assert result.relaxation_termination == "iteration_limit"
    assert result.fixed_site_count == 1
    assert result.released_anchor_count == 0


def test_explicit_nonconverged_continuation_remains_labeled(monkeypatch):
    field, _ = _anchored_seed()
    real_evolve = release_module.evolve_lorentzian_skyrme
    seen = {}

    def capture_and_run(field, velocity, **kwargs):
        seen["velocity_max"] = float(np.max(np.abs(velocity)))
        return real_evolve(field, velocity, **kwargs)

    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", capture_and_run)
    result = run_relaxation_then_cold_release(
        field,
        max_iterations=1,
        gradient_tolerance=1.0e-15,
        dt=1.0e-4,
        steps=2,
        allow_nonconverged=True,
    )
    assert result.status == "NOT_CONVERGED_EXPLORATORY_CONTINUATION"
    assert result.relaxation_termination == "iteration_limit"
    assert seen["velocity_max"] == 0.0


def test_budget_and_invalid_mask_fail_before_relaxation(monkeypatch):
    field, mask = _anchored_seed()

    def fail_if_called(*args, **kwargs):
        pytest.fail("preflight/validation must run before optimization")

    monkeypatch.setattr(
        release_module, "relax_skyrme_field_nearest_neighbor", fail_if_called
    )
    with pytest.raises(ValueError, match="max_relaxation_node_visits"):
        _run(field, mask, max_relaxation_node_visits=1)
    with pytest.raises(ValueError, match="max_rk_stage_site_evaluations"):
        _run(field, mask, max_rk_stage_site_evaluations=1)
    with pytest.raises(ValueError, match="aggregate snapshot budget"):
        _run(field, mask, max_snapshot_bytes=1)
    outer_mask = mask.copy()
    outer_mask[0, 3, 3] = True
    with pytest.raises(ValueError, match="interior anchors"):
        _run(field, outer_mask)
    with pytest.raises(ValueError, match="fixed_vacuum"):
        periodic = SU2GridField(
            field.components, spacing=field.spacing, boundary="periodic"
        )
        _run(periodic, np.zeros(mask.shape, dtype=bool))


def test_repeat_runs_have_identical_finite_serialization():
    field, mask = _anchored_seed()
    first = _run(field, mask)
    second = _run(field, mask)
    assert first.to_json() == second.to_json()
    decoded = json.loads(first.to_json())
    assert decoded["scientific_pass"] is False
    assert all(np.isfinite(value) for value in decoded["total_energy_history"])


def test_release_and_retention_use_same_grid_and_initial_zero_velocity_energy():
    field, mask = _anchored_seed()
    released = _run(field, mask, f_pi=1.4, e=0.8, anchor_policy="cold_release")
    retained = _run(field, mask, f_pi=1.4, e=0.8, anchor_policy="retain")

    assert released.spacing == retained.spacing == field.spacing
    assert released.boundary == retained.boundary == "fixed_vacuum"
    assert released.f_pi == retained.f_pi == 1.4
    assert released.e == retained.e == 0.8
    assert released.initial_static_potential_energy == released.initial_lorentzian_total_energy
    assert retained.initial_static_potential_energy == retained.initial_lorentzian_total_energy


def test_optimizer_final_field_is_handed_to_evolution_without_a_second_relaxation(monkeypatch):
    field, mask = _anchored_seed()
    real_relax = release_module.relax_skyrme_field_nearest_neighbor
    real_evolve = release_module.evolve_lorentzian_skyrme
    seen = {"relax_calls": 0, "field": None}

    def relax_once(*args, **kwargs):
        seen["relax_calls"] += 1
        result = real_relax(*args, **kwargs)
        seen["field"] = result.field
        return result

    def evolve_handoff(field, velocity, **kwargs):
        assert seen["relax_calls"] == 1
        assert field is seen["field"]
        return real_evolve(field, velocity, **kwargs)

    monkeypatch.setattr(release_module, "relax_skyrme_field_nearest_neighbor", relax_once)
    monkeypatch.setattr(release_module, "evolve_lorentzian_skyrme", evolve_handoff)
    result = _run(field, mask)

    assert result.status == "COMPLETED"
    assert seen["relax_calls"] == 1


def test_dimensioned_input_is_rejected_as_outside_synthetic_contract():
    field, mask = _anchored_seed()
    dimensioned = SU2GridField(
        field.components, spacing=field.spacing, boundary="fixed_vacuum", length_unit="m"
    )
    with pytest.raises(ValueError, match="dimensionless"):
        _run(dimensioned, mask)


@pytest.mark.parametrize("value", [True, "0.001", float("nan"), float("inf")])
def test_invalid_numeric_controls_fail_closed_before_optimization(monkeypatch, value):
    field, mask = _anchored_seed()

    def fail_if_called(*args, **kwargs):
        pytest.fail("invalid numeric controls must fail before optimization")

    monkeypatch.setattr(
        release_module, "relax_skyrme_field_nearest_neighbor", fail_if_called
    )
    with pytest.raises(ValueError):
        _run(field, mask, dt=value)
