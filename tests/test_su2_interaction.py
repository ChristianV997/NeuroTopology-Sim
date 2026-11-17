"""Synthetic tests for static two-hedgehog product-ansatz excess energies."""

import hashlib
import json

import numpy as np
import pytest

from field_theory.su2.generators import multi_hedgehog
from field_theory.su2.interaction import evaluate_two_hedgehog_interaction
from field_theory.su2.nearest_neighbor import compute_nearest_neighbor_diagnostics
from field_theory.su2.constrained_interaction import (
    run_constrained_two_hedgehog_relaxation,
    serialize_constrained_result,
)


def test_excess_components_are_direct_diagnostic_subtractions_and_metadata_is_checksummed():
    shape = (17, 17, 17)
    spacing = (0.5, 0.5, 0.5)
    radius = 1.5
    separation = (2.4, 0.8, 0.0)
    angle = np.pi / 2.0
    relative_rotation = (np.cos(angle / 2.0), 0.0, 0.0, np.sin(angle / 2.0))
    result = evaluate_two_hedgehog_interaction(
        shape=shape,
        spacing=spacing,
        radius=radius,
        separation_vector=separation,
        relative_isorotation=relative_rotation,
        f_pi=1.25,
        e=0.8,
        code_revision="test-revision",
    )

    centers = ((-separation[0] / 2.0, -separation[1] / 2.0, 0.0),
               (separation[0] / 2.0, separation[1] / 2.0, 0.0))
    first = multi_hedgehog(
        shape,
        centers=(centers[0],),
        radii=(radius,),
        spacing=spacing,
        isorotations=((1.0, 0.0, 0.0, 0.0),),
    )
    second = multi_hedgehog(
        shape,
        centers=(centers[1],),
        radii=(radius,),
        spacing=spacing,
        isorotations=(relative_rotation,),
    )
    pair = multi_hedgehog(
        shape,
        centers=centers,
        radii=(radius, radius),
        spacing=spacing,
        isorotations=((1.0, 0.0, 0.0, 0.0), relative_rotation),
        allow_overlaps=True,
    )
    diag_a = compute_nearest_neighbor_diagnostics(first, f_pi=1.25, e=0.8)
    diag_b = compute_nearest_neighbor_diagnostics(second, f_pi=1.25, e=0.8)
    diag_pair = compute_nearest_neighbor_diagnostics(pair, f_pi=1.25, e=0.8)

    assert result.energy_a.energy_sigma == diag_a.energy_sigma
    assert result.energy_b.energy_skyrme == diag_b.energy_skyrme
    assert result.energy_pair.topological_charge == diag_pair.topological_charge
    assert result.delta_energy_sigma == pytest.approx(
        diag_pair.energy_sigma - diag_a.energy_sigma - diag_b.energy_sigma, abs=1e-14
    )
    assert result.delta_energy_skyrme == pytest.approx(
        diag_pair.energy_skyrme - diag_a.energy_skyrme - diag_b.energy_skyrme, abs=1e-14
    )
    assert result.delta_energy_total == pytest.approx(
        diag_pair.energy_total - diag_a.energy_total - diag_b.energy_total, abs=1e-14
    )
    assert result.delta_energy_total == pytest.approx(
        result.delta_energy_sigma + result.delta_energy_skyrme, abs=2e-14
    )
    assert result.v_h == pytest.approx(result.delta_energy_total / result.energy_scale)
    assert result.energy_a.topological_charge == diag_a.topological_charge
    assert result.energy_b.topological_charge == diag_b.topological_charge
    assert result.energy_pair.topological_charge == diag_pair.topological_charge

    metadata = json.loads(result.input_metadata_json)
    assert metadata["box_extent"] == [8.0, 8.0, 8.0]
    assert metadata["dimensionless_controls"]["lambda"] == pytest.approx(1.0)
    assert metadata["dimensionless_controls"]["E0"] == pytest.approx(1.5625)
    assert metadata["dimensionless_controls"]["rho"] == pytest.approx(1.5)
    assert metadata["dimensionless_controls"]["s"] == pytest.approx(
        np.linalg.norm(separation) / radius
    )
    assert metadata["composition_order"] == "U_A * (G U_B G†)"
    assert result.input_sha256 == hashlib.sha256(
        result.input_metadata_json.encode("utf-8")
    ).hexdigest()
    json.dumps(result.to_dict(), sort_keys=True, allow_nan=False)


def test_nonunit_lambda_normalization_matches_independent_diagnostic_subtractions():
    shape = (17, 17, 17)
    spacing = (0.5, 0.5, 0.5)
    radius = 1.5
    separation = (2.4, 0.8, 0.0)
    f_pi = 2.0
    e = 1.0
    lambda_value = e * f_pi
    result = evaluate_two_hedgehog_interaction(
        shape=shape,
        spacing=spacing,
        radius=radius,
        separation_vector=separation,
        f_pi=f_pi,
        e=e,
    )

    centers = ((-separation[0] / 2.0, -separation[1] / 2.0, 0.0),
               (separation[0] / 2.0, separation[1] / 2.0, 0.0))
    first = multi_hedgehog(
        shape, centers=(centers[0],), radii=(radius,), spacing=spacing
    )
    second = multi_hedgehog(
        shape, centers=(centers[1],), radii=(radius,), spacing=spacing
    )
    pair = multi_hedgehog(
        shape,
        centers=centers,
        radii=(radius, radius),
        spacing=spacing,
        allow_overlaps=True,
    )

    # Recompute the geometry-only sums at unit couplings: these diagnostics
    # equal S2/8 and S4/2, respectively, on the same supplied grid.
    unit_a = compute_nearest_neighbor_diagnostics(first, f_pi=1.0, e=1.0)
    unit_b = compute_nearest_neighbor_diagnostics(second, f_pi=1.0, e=1.0)
    unit_pair = compute_nearest_neighbor_diagnostics(pair, f_pi=1.0, e=1.0)
    delta_s2_over_8 = (
        unit_pair.energy_sigma - unit_a.energy_sigma - unit_b.energy_sigma
    )
    delta_s4_over_2 = (
        unit_pair.energy_skyrme - unit_a.energy_skyrme - unit_b.energy_skyrme
    )
    expected_lambda_form = (
        lambda_value * delta_s2_over_8 + delta_s4_over_2 / lambda_value
    )

    # Independently recompute the actual-coupling energies and divide their
    # pair-minus-singles difference by E0=f_pi/e.
    actual_a = compute_nearest_neighbor_diagnostics(first, f_pi=f_pi, e=e)
    actual_b = compute_nearest_neighbor_diagnostics(second, f_pi=f_pi, e=e)
    actual_pair = compute_nearest_neighbor_diagnostics(pair, f_pi=f_pi, e=e)
    expected_energy_ratio = (
        actual_pair.energy_total - actual_a.energy_total - actual_b.energy_total
    ) / (f_pi / e)

    assert lambda_value == 2.0
    assert result.energy_scale == pytest.approx(f_pi / e)
    assert json.loads(result.input_metadata_json)["dimensionless_controls"]["lambda"] == 2.0
    assert result.v_h == pytest.approx(expected_energy_ratio, abs=1e-14)
    assert result.v_h == pytest.approx(expected_lambda_form, abs=1e-14)
    # This fixture distinguishes the required lambda=2 formula from the
    # mistaken lambda=1 weighting; the test would fail under that substitution.
    lambda_one_value = delta_s2_over_8 + delta_s4_over_2
    assert abs(expected_lambda_form - lambda_one_value) > 1.0e-4


@pytest.mark.parametrize(
    "shape,spacing,separation,radius",
    [
        ((33, 33, 33), (0.5, 0.5, 0.5), (8.0, 0.0, 0.0), 1.5),
        ((25, 17, 13), (1.0, 2.0, 1.5), (6.0, 8.0, 0.0), 1.0),
    ],
)
def test_stencil_disjoint_pairs_have_zero_excess_with_isotropic_and_anisotropic_grids(
    shape, spacing, separation, radius
):
    result = evaluate_two_hedgehog_interaction(
        shape=shape, spacing=spacing, radius=radius, separation_vector=separation
    )
    assert result.stencil_overlap is False
    assert result.delta_energy_sigma == pytest.approx(0.0, abs=1e-12)
    assert result.delta_energy_skyrme == pytest.approx(0.0, abs=1e-12)
    assert result.delta_energy_total == pytest.approx(0.0, abs=1e-12)


def test_disjoint_supports_sharing_anisotropic_quartic_diagonal_stencil_are_not_isolated():
    result = evaluate_two_hedgehog_interaction(
        shape=(12, 12, 9),
        spacing=(1.0, 2.0, 1.0),
        radius=0.9,
        separation_vector=(1.0, -2.0, 0.0),
    )
    metadata = json.loads(result.input_metadata_json)
    assert metadata["separation_distance"] > 2.0 * metadata["radius"]
    assert result.stencil_overlap is True
    assert np.all(
        np.isfinite(
            (
                result.energy_a.energy_total,
                result.energy_b.energy_total,
                result.energy_pair.energy_total,
                result.delta_energy_total,
            )
        )
    )


def test_overlapping_oriented_pair_is_finite_and_deterministic():
    kwargs = dict(
        shape=(17, 17, 17),
        spacing=(0.5, 0.75, 1.0),
        radius=1.5,
        separation_vector=(2.0, 0.5, 0.0),
        relative_isorotation=(np.cos(np.pi / 6.0), 0.0, 0.0, np.sin(np.pi / 6.0)),
    )
    first = evaluate_two_hedgehog_interaction(**kwargs)
    repeated = evaluate_two_hedgehog_interaction(**kwargs)
    assert first == repeated
    assert first.stencil_overlap is True
    assert first.input_sha256 == repeated.input_sha256
    assert np.all(
        np.isfinite(
            (
                first.energy_a.energy_total,
                first.energy_b.energy_total,
                first.energy_pair.energy_total,
                first.delta_energy_sigma,
                first.delta_energy_skyrme,
                first.v_h,
            )
        )
    )


def test_axis_permutation_preserves_energy_for_consistently_permuted_anisotropic_grid():
    shape = (33, 25, 21)
    spacing = (0.5, 0.75, 1.0)
    separation = (2.0, 3.0, 1.0)
    rotation = (np.cos(np.pi / 6.0), 0.0, np.sin(np.pi / 6.0), 0.0)
    original = evaluate_two_hedgehog_interaction(
        shape=shape,
        spacing=spacing,
        radius=1.2,
        separation_vector=separation,
        relative_isorotation=rotation,
    )
    # (x,y,z)->(y,z,x) is an orientation-preserving cyclic permutation.
    permutation = (1, 2, 0)
    permuted = evaluate_two_hedgehog_interaction(
        shape=tuple(shape[axis] for axis in permutation),
        spacing=tuple(spacing[axis] for axis in permutation),
        radius=1.2,
        separation_vector=tuple(separation[axis] for axis in permutation),
        relative_isorotation=rotation,
    )
    for name in ("energy_a", "energy_b", "energy_pair"):
        first_energy = getattr(original, name)
        permuted_energy = getattr(permuted, name)
        np.testing.assert_allclose(
            (
                first_energy.energy_sigma,
                first_energy.energy_skyrme,
                first_energy.energy_total,
                first_energy.topological_charge,
            ),
            (
                permuted_energy.energy_sigma,
                permuted_energy.energy_skyrme,
                permuted_energy.energy_total,
                permuted_energy.topological_charge,
            ),
            rtol=1e-11,
            atol=1e-11,
        )
    assert original.stencil_overlap == permuted.stencil_overlap


def test_refinement_records_fixed_physical_box_without_assuming_monotonic_energy():
    coarse = evaluate_two_hedgehog_interaction(
        shape=(17, 17, 17),
        spacing=(1.0, 1.0, 1.0),
        radius=1.5,
        separation_vector=(2.0, 1.0, 0.0),
    )
    fine = evaluate_two_hedgehog_interaction(
        shape=(33, 33, 33),
        spacing=(0.5, 0.5, 0.5),
        radius=1.5,
        separation_vector=(2.0, 1.0, 0.0),
    )
    coarse_metadata = json.loads(coarse.input_metadata_json)
    fine_metadata = json.loads(fine.input_metadata_json)
    assert coarse_metadata["box_extent"] == fine_metadata["box_extent"] == [16.0] * 3
    assert coarse_metadata["grid_node_count"] < fine_metadata["grid_node_count"]
    for result in (coarse, fine):
        assert np.all(
            np.isfinite(
                (
                    result.energy_pair.energy_total,
                    result.delta_energy_total,
                    result.v_h,
                )
            )
        )
    # This is reporting/convergence coverage only; no monotonic trend is assumed.


@pytest.mark.parametrize(
    "kwargs",
    [
        {"radius": 0.0},
        {"radius": np.nan},
        {"separation_vector": (np.inf, 0.0, 0.0)},
        {"relative_isorotation": (1.0, 0.0, np.nan, 0.0)},
        {"relative_isorotation": (True, 0.0, 0.0, 0.0)},
        {"relative_isorotation": (2.0, 0.0, 0.0, 0.0)},
        {"f_pi": 0.0},
        {"f_pi": True},
        {"f_pi": 1.0e308, "e": 1.0e308},
        {"f_pi": np.nan},
        {"e": 0.0},
        {"e": np.inf},
        {"spacing": (1.0, 0.0, 1.0)},
    ],
)
def test_rejects_invalid_geometry_or_couplings(kwargs):
    arguments = dict(
        shape=(17, 17, 17),
        spacing=(0.5, 0.5, 0.5),
        radius=1.0,
        separation_vector=(4.0, 0.0, 0.0),
    )
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        evaluate_two_hedgehog_interaction(**arguments)


def test_rejects_supports_that_do_not_strictly_fit_inside_every_face():
    with pytest.raises(ValueError, match="fit"):
        evaluate_two_hedgehog_interaction(
            shape=(9, 9, 9),
            spacing=(0.5, 0.5, 0.5),
            radius=1.0,
            separation_vector=(2.0, 0.0, 0.0),
        )



def _constrained_run_kwargs():
    return {
        "shape": (17, 17, 17),
        "spacing": (0.25, 0.25, 0.25),
        "radius": 0.8,
        "separation_vector": (1.5, 0.0, 0.0),
        "relative_isorotation": (0.7071067811865476, 0.0, 0.0, 0.7071067811865476),
        "anchor_radius": 0.3,
        "code_revision": "a" * 40,
        "max_iterations": 1,
        "initial_step": 1.0e-4,
        "gradient_tolerance": 1.0e-16,
        "max_backtracks": 2,
    }


def test_constrained_pair_run_is_deterministic_and_withholds_unconverged_comparison():
    first = run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())
    second = run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())

    assert serialize_constrained_result(first) == serialize_constrained_result(second)
    assert first["evidence_class"] == "synthetic_constrained_lattice_optimization"
    assert first["scientific_pass"] is False
    assert first["claim_scope"] == (
        "finite-grid, finite-box excess energy conditional on the specified frozen anchor patches"
    )
    assert first["status"] == "COMPARISON_WITHHELD"
    assert first["comparison"]["final_pair_minus_isolated_energy"] is None
    assert max(first["input"]["anchor_pair_isolated_max_abs_deviation"]) <= (
        first["input"]["anchor_pair_isolated_match_abs_tolerance"]
    )
    assert all(
        run["constraints"]["fixed_sites_unchanged"]
        for run in first["runs"].values()
    )
    assert all(run["minimum_certified"] is False for run in first["runs"].values())


def test_initial_pair_minus_isolated_arithmetic_matches_recorded_initial_energies():
    result = run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())
    runs = result["runs"]
    expected = (
        runs["pair"]["initial_energy"]
        - runs["isolated_a"]["initial_energy"]
        - runs["isolated_b"]["initial_energy"]
    )
    assert result["comparison"]["initial_pair_minus_isolated_energy"] == pytest.approx(expected)


def test_constrained_pair_rejects_overlapping_anchor_patches_and_nonfinite_inputs():
    kwargs = _constrained_run_kwargs()
    kwargs["separation_vector"] = (1.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="anchor patches"):
        run_constrained_two_hedgehog_relaxation(**kwargs)

    kwargs = _constrained_run_kwargs()
    kwargs["spacing"] = (float("nan"), 0.25, 0.25)
    with pytest.raises(ValueError):
        run_constrained_two_hedgehog_relaxation(**kwargs)


def test_constrained_pair_enforces_bounded_iteration_and_work_limits():
    kwargs = _constrained_run_kwargs()
    kwargs["max_iterations"] = 101
    with pytest.raises(ValueError, match="max_iterations"):
        run_constrained_two_hedgehog_relaxation(**kwargs)


def test_constrained_pair_rejects_excessive_estimated_work():
    kwargs = _constrained_run_kwargs()
    kwargs["shape"] = (32, 32, 32)
    kwargs["max_iterations"] = 100
    kwargs["max_backtracks"] = 12
    with pytest.raises(ValueError, match="estimated work"):
        run_constrained_two_hedgehog_relaxation(**kwargs)


def test_serializer_rejects_mutated_result_with_stale_checksum():
    result = run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())
    mutated = dict(result)
    mutated["status"] = "ALTERED_AFTER_HASHING"

    with pytest.raises(ValueError, match="checksum"):
        serialize_constrained_result(mutated)


def test_component_charge_drift_is_not_labeled_sector_confidence():
    result = run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())

    for run in result["runs"].values():
        assert "charge_drift_status" in run
        assert "topological_sector_confidence" not in run
        assert run["charge_drift_status"] in {
            "DRIFT_WITHIN_DECLARED_SCREEN",
            "DRIFT_EXCEEDS_DECLARED_SCREEN",
        }


def test_success_path_uses_final_energies_with_nonidentity_rotation(monkeypatch):
    """Use controlled diagnostics to verify final-energy subtraction independently."""
    from types import SimpleNamespace

    from field_theory.su2 import constrained_interaction as runner

    initial_energies = (100.0, 20.0, 200.0)  # isolated A, isolated B, pair
    final_energies = (11.0, 3.0, 42.0)
    diagnostic_energies = iter((100.0, 11.0, 20.0, 3.0, 200.0, 42.0))
    relaxation_index = iter(range(3))

    def diagnostics_stub(field, *, f_pi, e):
        return SimpleNamespace(
            energy_total=next(diagnostic_energies),
            topological_charge=0.0,
        )

    def converged_stub(field, *, f_pi, e, **kwargs):
        index = next(relaxation_index)
        return SimpleNamespace(
            field=field,
            energy_history=(initial_energies[index], final_energies[index]),
            topological_charge_history=(0.0, 0.0),
            iterations=1,
            termination="gradient_tolerance",
            stationarity_status="first_order_stationary",
            curvature_diagnostics=None,
        )

    monkeypatch.setattr(runner, "compute_nearest_neighbor_diagnostics", diagnostics_stub)
    monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", converged_stub)
    result = runner.run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())

    assert result["status"] == "COMPARISON_AVAILABLE"
    assert result["input"]["relative_isorotation_used"] != [1.0, 0.0, 0.0, 0.0]
    assert result["comparison"]["initial_pair_minus_isolated_energy"] == pytest.approx(80.0)
    assert result["comparison"]["final_pair_minus_isolated_energy"] == pytest.approx(28.0)
    assert result["comparison"]["final_pair_minus_isolated_energy"] != pytest.approx(
        result["comparison"]["initial_pair_minus_isolated_energy"]
    )


def test_constrained_pair_rejects_anchor_mismatch_above_tolerance(monkeypatch):
    from field_theory.su2 import constrained_interaction as runner

    original = runner.multi_hedgehog
    call_count = 0

    def perturbed_isolated(*args, **kwargs):
        nonlocal call_count
        field = original(*args, **kwargs)
        call_count += 1
        if call_count != 2:
            return field

        components = field.components.copy()
        center = kwargs["centers"][0]
        axes = tuple(
            (np.arange(size, dtype=float) - (size - 1) / 2.0) * step
            for size, step in zip(components.shape[:3], field.spacing)
        )
        index = tuple(int(np.argmin(np.abs(axis - value))) for axis, value in zip(axes, center))
        first_pair = components[index][[0, 1]]
        second_pair = components[index][[2, 3]]
        a, b = (0, 1) if np.linalg.norm(first_pair) >= np.linalg.norm(second_pair) else (2, 3)
        cosine, sine = np.cos(1.0e-10), np.sin(1.0e-10)
        x, y = components[index][a], components[index][b]
        components[index][a] = cosine * x - sine * y
        components[index][b] = sine * x + cosine * y
        return type(field)(
            components=components,
            spacing=field.spacing,
            boundary=field.boundary,
            length_unit=field.length_unit,
        )

    monkeypatch.setattr(runner, "multi_hedgehog", perturbed_isolated)
    with pytest.raises(ValueError, match="disagree beyond tolerance"):
        runner.run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())
    assert call_count == 2


def test_constrained_pair_rejects_nonfinite_anchor_mismatch(monkeypatch):
    from types import SimpleNamespace

    from field_theory.su2 import constrained_interaction as runner

    original = runner.multi_hedgehog
    call_count = 0

    def nonfinite_isolated(*args, **kwargs):
        nonlocal call_count
        field = original(*args, **kwargs)
        call_count += 1
        if call_count != 2:
            return field

        components = field.components.copy()
        components[5, 8, 8, 0] = np.nan
        return SimpleNamespace(components=components)

    monkeypatch.setattr(runner, "multi_hedgehog", nonfinite_isolated)
    with pytest.raises(ValueError, match="anchor mismatch must be finite"):
        runner.run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())
    assert call_count == 2
