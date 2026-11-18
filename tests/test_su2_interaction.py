"""Synthetic tests for static two-hedgehog product-ansatz excess energies."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from field_theory.su2 import constrained_interaction as runner
from field_theory.su2 import interaction as interaction_module
from field_theory.su2.field import SU2GridField
from field_theory.su2.generators import multi_hedgehog, vacuum
from field_theory.su2.interaction import evaluate_two_hedgehog_interaction
from field_theory.su2.nearest_neighbor import (
    _cell_volume,
    _energy_coefficients,
    _gradient_coefficients,
    _stable_norm,
    _scaled_product_quotient,
    _scaled_quartic_gradient_contributions,
    _forward_differences,
    compute_nearest_neighbor_diagnostics,
    nearest_neighbor_energy_gradient,
    nearest_neighbor_energy_gradient_finite_difference,
)
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

    def fail_if_relaxed(*args, **kwargs):
        pytest.fail("relaxation must not run after failed anchor preflight")

    monkeypatch.setattr(
        runner, "relax_skyrme_field_nearest_neighbor", fail_if_relaxed
    )
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
    assert call_count == 3


def test_constrained_pair_rejects_nonfinite_anchor_mismatch(monkeypatch):
    from types import SimpleNamespace

    from field_theory.su2 import constrained_interaction as runner

    def fail_if_relaxed(*args, **kwargs):
        pytest.fail("relaxation must not run after failed anchor preflight")

    monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", fail_if_relaxed)
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
    assert call_count == 3


@pytest.mark.parametrize(
    "termination",
    ["iteration_limit", "line_search_stalled"],
)
def test_constrained_pair_withholds_comparison_for_nonconverged_termination(
    monkeypatch, termination
):
    from types import SimpleNamespace

    from field_theory.su2 import constrained_interaction as runner

    def nonconverged_stub(field, *, f_pi, e, **kwargs):
        diagnostic = runner.compute_nearest_neighbor_diagnostics(
            field, f_pi=f_pi, e=e
        )
        return SimpleNamespace(
            field=field,
            energy_history=(diagnostic.energy_total,),
            topological_charge_history=(diagnostic.topological_charge,),
            iterations=0,
            termination=termination,
            stationarity_status="not_established",
            curvature_diagnostics=None,
        )

    monkeypatch.setattr(
        runner, "relax_skyrme_field_nearest_neighbor", nonconverged_stub
    )
    result = runner.run_constrained_two_hedgehog_relaxation(**_constrained_run_kwargs())

    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    assert (
        result["comparison"]["available_only_if_all_three_converged_and_constraints_pass"]
        is False
    )
    assert all(
        run["status"] == "NOT_CONVERGED" for run in result["runs"].values()
    )


# Numerical boundary and failure-contract regressions for constrained runs.


def _kwargs():
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


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("f_pi", 1.0e308),
        ("f_pi", 1.0e-308),
        ("e", 1.0e-308),
        ("e", 1.0e308),
    ],
)
def test_rejects_unrepresentable_derived_energy_coefficients(monkeypatch, name, value):
    kwargs = _kwargs()
    kwargs[name] = value

    def fail_if_building(*args, **kwargs):
        pytest.fail("unrepresentable couplings must be rejected before field construction")

    monkeypatch.setattr(runner, "multi_hedgehog", fail_if_building)
    with pytest.raises(ValueError, match="unrepresentable binary64 energy coefficient"):
        runner.run_constrained_two_hedgehog_relaxation(**kwargs)


def test_stable_coefficients_accept_extreme_but_representable_couplings():
    sigma_coefficient, skyrme_coefficient = _energy_coefficients(
        f_pi=2.0e154, e=1.0e160
    )
    assert np.isfinite(sigma_coefficient)
    assert sigma_coefficient > 0.0
    assert np.isfinite(skyrme_coefficient)
    assert 0.0 < skyrme_coefficient < np.finfo(np.float64).tiny

    diagnostic = compute_nearest_neighbor_diagnostics(
        vacuum((3, 3, 3)), f_pi=2.0e154, e=1.0e160
    )
    assert diagnostic.energy_total == 0.0
    assert np.isfinite(diagnostic.energy_total)



def test_cell_volume_uses_scaled_product_when_an_intermediate_would_underflow():
    assert _cell_volume((1.0e-200, 1.0e-200, 1.0e300)) == pytest.approx(1.0e-100)


def test_scaled_product_quotient_preserves_representable_extremes_and_rejects_loss():
    huge = _scaled_product_quotient(
        np.array([1.0e210]),
        numerator_factors=(1.0e-10,),
        denominator_factors=(1.0e-100,),
        name="test scaling",
    )
    assert huge[0] == pytest.approx(1.0e300, rel=1.0e-14)

    subnormal = _scaled_product_quotient(
        np.array([5.0e-2]),
        numerator_factors=(1.0e-323, 1.0e-309),
        denominator_factors=(1.0e-322,),
        name="subnormal test scaling",
    )
    assert 0.0 < subnormal[0] < np.finfo(np.float64).tiny
    assert subnormal[0] == pytest.approx(5.0e-312, rel=0.2)

    with pytest.raises(FloatingPointError, match="underflowed entirely to zero"):
        _scaled_product_quotient(
            np.array([1.0e-320]),
            numerator_factors=(1.0e-100,),
            name="unrepresentable test scaling",
            fail_if_all_zero=True,
        )


def test_sigma_energy_and_gradient_preserve_tiny_links_with_large_finite_coupling():
    theta = np.linspace(0.0, 1.0e-200, 5)[:, None, None]
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(theta)
    components[..., 1] = np.sin(theta)
    field = SU2GridField(components, boundary="periodic")

    diagnostic = compute_nearest_neighbor_diagnostics(field, f_pi=2.5e154, e=1.0)
    gradient = nearest_neighbor_energy_gradient(field, f_pi=2.5e154, e=1.0)

    assert diagnostic.energy_sigma == pytest.approx(2.44140625e-91, rel=1.0e-12)
    assert diagnostic.energy_sigma > 0.0
    assert np.all(np.isfinite(gradient))
    assert float(np.max(np.abs(gradient))) > 0.0


def test_fixed_vacuum_forward_differences_mask_excluded_wrap_before_scaling():
    values = np.zeros((3, 2, 2, 4), dtype=np.float64)
    values[..., 0] = 1.0
    values[1, ..., 1] = 2.5e-9
    values[2, ..., 1] = 5.0e-9
    spacing = (
        0.75 * 5.0e-9 / np.finfo(np.float64).max,
        1.0e158,
        1.0e158,
    )

    fixed = _forward_differences(values, spacing, boundary="fixed_vacuum")

    assert np.all(np.isfinite(fixed[0]))
    assert np.all(fixed[0][-1] == 0.0)
    assert np.max(np.abs(fixed[0][:-1])) < np.finfo(np.float64).max
    with pytest.raises(FloatingPointError, match="forward difference overflowed"):
        _forward_differences(values, spacing, boundary="periodic")


def test_fixed_vacuum_gradient_ignores_excluded_wrap_quartic_overflow():
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = 1.0
    components[0, :, :, 1] = 1.0e-9
    components[-1, 2, 2, 2] = 1.0e-9
    field = SU2GridField(
        components,
        spacing=(1.0e-209, 1.0e-209, 1.0e308),
        boundary="fixed_vacuum",
    )

    gradient = nearest_neighbor_energy_gradient(field)

    assert np.all(np.isfinite(gradient))
    assert float(np.max(np.abs(gradient))) > 0.0


def test_fixed_vacuum_quartic_energy_masks_excluded_wrap_links_before_products():
    components = np.zeros((6, 6, 6, 4), dtype=np.float64)
    components[..., 0] = 1.0

    angle = 0.2
    components[2, 2, 2] = (np.cos(angle), np.sin(angle), 0.0, 0.0)
    components[3, 2, 2] = (np.cos(angle), 0.0, np.sin(angle), 0.0)
    components[2, 3, 2] = (np.cos(angle), 0.0, 0.0, np.sin(angle))

    # Each perturbation is within the accepted fixed-vacuum tolerance. At the
    # excluded x-wrap anchor, the x and y link components form a nonzero minor
    # of order 1e-400, which must not be evaluated.
    epsilon = 1.0e-200
    components[0, 1, 2, 1] = epsilon
    components[-1, 2, 2, 2] = epsilon
    field = SU2GridField(components, boundary="fixed_vacuum")

    diagnostic = compute_nearest_neighbor_diagnostics(field, f_pi=1.0, e=1.0)

    assert np.isfinite(diagnostic.energy_sigma)
    assert np.isfinite(diagnostic.energy_skyrme)
    assert diagnostic.energy_skyrme > 0.0


def test_scaled_quartic_gradient_fallback_matches_analytic_polynomial():
    rng = np.random.default_rng(42)
    a = rng.normal(scale=0.2, size=(2, 3, 4))
    b = rng.normal(scale=0.15, size=(2, 3, 4))
    transverse = np.array([[0.5, 1.0, 0.5], [1.0, 0.5, 1.0]])
    cell_volume = 0.7
    coefficient = 0.8
    spacing_a = 1.2
    spacing_b = 0.9

    actual_a, actual_b = _scaled_quartic_gradient_contributions(
        a,
        b,
        cell_volume=cell_volume,
        transverse=transverse,
        coefficient=coefficient,
        spacing_a=spacing_a,
        spacing_b=spacing_b,
    )
    dot = np.sum(a * b, axis=-1, keepdims=True)
    norm_a_squared = np.sum(a * a, axis=-1, keepdims=True)
    norm_b_squared = np.sum(b * b, axis=-1, keepdims=True)
    expected_a = (
        cell_volume
        * transverse[..., None]
        * coefficient
        / spacing_a
        * (norm_b_squared * a - dot * b)
    )
    expected_b = (
        cell_volume
        * transverse[..., None]
        * coefficient
        / spacing_b
        * (norm_a_squared * b - dot * a)
    )

    np.testing.assert_allclose(actual_a, expected_a, rtol=1.0e-14, atol=1.0e-16)
    np.testing.assert_allclose(actual_b, expected_b, rtol=1.0e-14, atol=1.0e-16)


def test_quartic_gradient_uses_scaled_fallback_for_tiny_link_products():
    alpha = np.linspace(0.0, 0.4, 5)[:, None, None]
    beta = np.linspace(0.0, 0.6, 5)[None, :, None]
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(alpha) * np.cos(beta)
    components[..., 1] = np.sin(alpha)
    components[..., 2] = np.cos(alpha) * np.sin(beta)
    field = SU2GridField(
        components,
        spacing=(1.0e200, 1.0e200, 1.0e-100),
        boundary="periodic",
    )

    gradient = nearest_neighbor_energy_gradient(
        field, f_pi=1.0e-5, e=1.0e-154
    )

    assert np.all(np.isfinite(gradient))
    assert float(np.max(np.abs(gradient))) > 0.0


def test_gradient_avoids_overflow_before_small_coefficient_and_spacing_scale():
    theta = np.arange(5, dtype=np.float64)[:, None, None] * 1.0e-10
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(theta)
    components[..., 1] = np.sin(theta)
    field = SU2GridField(
        components,
        spacing=(1.0e-100, 1.0e110, 1.0e110),
        boundary="periodic",
    )

    gradient = nearest_neighbor_energy_gradient(field, f_pi=2.0e-5, e=1.0)

    assert np.all(np.isfinite(gradient))
    assert float(np.max(np.abs(gradient))) > 1.0e299


def test_interaction_preflights_unrepresentable_cell_volume_before_fields(monkeypatch):
    def fail_if_building(*args, **kwargs):
        pytest.fail("invalid cell volume must fail before field construction")

    monkeypatch.setattr(interaction_module, "multi_hedgehog", fail_if_building)
    with pytest.raises(ValueError, match="finite positive binary64 cell volume"):
        evaluate_two_hedgehog_interaction(
            shape=(5, 5, 5),
            spacing=(1.0e-200, 1.0e-200, 1.0e-100),
            radius=0.5,
            separation_vector=(0.5, 0.0, 0.0),
        )


@pytest.mark.parametrize(
    "spacing",
    [(1.0e-200, 1.0e-200, 1.0e-100), (1.0e200, 1.0e200, 1.0)],
)
def test_cell_volume_underflow_or_overflow_is_rejected(spacing):
    with pytest.raises(ValueError, match="finite positive binary64 cell volume"):
        _cell_volume(spacing)


def test_stable_norm_preserves_small_and_large_gradient_scales():
    tiny = np.array([1.0e-200, -1.0e-200])
    huge = np.array([1.0e200, -1.0e200])

    assert _stable_norm(tiny) == pytest.approx(np.sqrt(2.0) * 1.0e-200)
    assert _stable_norm(huge) == pytest.approx(np.sqrt(2.0) * 1.0e200)
    smallest = np.nextafter(0.0, 1.0)
    assert _stable_norm(np.array([smallest, 0.0])) == smallest
    per_row = _stable_norm(np.array([tiny, huge]), axis=1)
    np.testing.assert_allclose(
        per_row,
        np.array([np.sqrt(2.0) * 1.0e-200, np.sqrt(2.0) * 1.0e200]),
    )


@pytest.mark.parametrize(
    "spacing",
    [(1.0e-200, 1.0e-200, 1.0e-100), (1.0e200, 1.0e200, 1.0)],
)
def test_constrained_runner_preflights_cell_volume_before_fields(monkeypatch, spacing):
    kwargs = _kwargs()
    kwargs["spacing"] = spacing

    def fail_if_building(*args, **kwargs):
        pytest.fail("unrepresentable cell volume must fail before field construction")

    monkeypatch.setattr(runner, "multi_hedgehog", fail_if_building)
    with pytest.raises(ValueError, match="finite positive binary64 cell volume"):
        run_constrained_two_hedgehog_relaxation(**kwargs)


def test_gradient_coefficients_support_extremes_and_fail_closed():
    sigma_gradient, skyrme_gradient = _gradient_coefficients(
        f_pi=2.0e154, e=1.0e160
    )
    assert sigma_gradient == pytest.approx(1.0e308, rel=1.0e-14)
    assert 0.0 < skyrme_gradient < np.finfo(np.float64).tiny

    with pytest.raises(ValueError, match="unrepresentable binary64 gradient coefficient"):
        _gradient_coefficients(f_pi=3.0e154, e=1.0)


def test_gradient_uses_scaled_coefficients_for_representable_extremes():
    theta = np.linspace(-0.01, 0.01, 5)[:, None, None]
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(theta)
    components[..., 1] = np.sin(theta)
    field = SU2GridField(components, boundary="periodic")

    gradient = nearest_neighbor_energy_gradient(
        field, f_pi=2.0e154, e=1.0e160
    )
    assert np.all(np.isfinite(gradient))
    assert np.max(np.abs(gradient)) > 0.0


def test_gradient_applies_subnormal_coefficients_after_cell_volume_scaling():
    alpha = np.linspace(-0.4, 0.4, 5)[:, None, None]
    beta = np.linspace(-0.4, 0.4, 5)[None, :, None]
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(alpha)
    components[..., 1] = np.sin(alpha) * np.cos(beta)
    components[..., 2] = np.sin(alpha) * np.sin(beta)
    field = SU2GridField(
        components,
        spacing=(1.0e-100, 1.0, 1.0),
        boundary="periodic",
    )

    couplings = {"f_pi": 1.0e-160, "e": 1.0e160}
    gradient = nearest_neighbor_energy_gradient(field, **couplings)
    reference = nearest_neighbor_energy_gradient_finite_difference(
        field, **couplings
    )

    assert np.all(np.isfinite(gradient))
    gradient_scale = float(np.max(np.abs(gradient)))
    reference_scale = float(np.max(np.abs(reference)))
    assert gradient_scale > 0.0
    assert reference_scale > 0.0
    relative_error = float(np.max(np.abs(gradient - reference))) / reference_scale
    assert relative_error < 5.0e-3


def test_gradient_applies_subnormal_coefficients_after_spacing_transpose():
    alpha = np.linspace(-2.0e-4, 2.0e-4, 5)[:, None, None]
    beta = np.linspace(-0.4, 0.4, 5)[None, :, None]
    components = np.zeros((5, 5, 5, 4), dtype=np.float64)
    components[..., 0] = np.cos(alpha)
    components[..., 1] = np.sin(alpha) * np.cos(beta)
    components[..., 2] = np.sin(alpha) * np.sin(beta)
    field = SU2GridField(
        components,
        spacing=(1.0e-100, 1.0, 1.0),
        boundary="periodic",
    )

    couplings = {"f_pi": 1.0e-160, "e": 1.0e160}
    gradient = nearest_neighbor_energy_gradient(field, **couplings)
    reference = nearest_neighbor_energy_gradient_finite_difference(
        field, finite_difference_step=1.0e-7, **couplings
    )

    assert np.all(np.isfinite(gradient))
    gradient_scale = float(np.max(np.abs(gradient)))
    reference_scale = float(np.max(np.abs(reference)))
    assert gradient_scale > 0.0
    assert reference_scale > 0.0
    relative_error = float(np.max(np.abs(gradient - reference))) / reference_scale
    assert relative_error < 5.0e-3


def test_constrained_pair_preflights_unrepresentable_gradient_coefficient(monkeypatch):
    kwargs = _kwargs()
    kwargs["f_pi"] = 3.0e154

    def fail_if_building(*args, **kwargs):
        pytest.fail("unrepresentable gradient coefficients must fail before field construction")

    monkeypatch.setattr(runner, "multi_hedgehog", fail_if_building)
    with pytest.raises(ValueError, match="unrepresentable binary64 gradient coefficient"):
        runner.run_constrained_two_hedgehog_relaxation(**kwargs)


def test_initial_diagnostic_numerical_failure_is_structured(monkeypatch):
    def fail(*args, **kwargs):
        raise FloatingPointError("injected initial failure")

    monkeypatch.setattr(runner, "compute_nearest_neighbor_diagnostics", fail)
    result = runner.run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["comparison"]["initial_pair_minus_isolated_energy"] is None
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    assert all(run["status"] == "NUMERICAL_FAILURE" for run in result["runs"].values())
    assert all(
        run["termination"] == "initial_diagnostics_failure"
        for run in result["runs"].values()
    )
    serialized = runner.serialize_constrained_result(result)
    assert json.loads(serialized)["runs"]["isolated_a"]["initial_energy"] is None


def test_optimizer_zero_division_is_structured(monkeypatch):
    def fail(*args, **kwargs):
        raise ZeroDivisionError("injected optimizer failure")

    monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", fail)
    result = runner.run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    assert all(run["status"] == "NUMERICAL_FAILURE" for run in result["runs"].values())
    assert all(run["termination"] == "optimization_failure" for run in result["runs"].values())
    runner.serialize_constrained_result(result)


def test_final_diagnostic_numerical_failure_is_structured_and_withholds_comparison(monkeypatch):
    original_diagnostics = runner.compute_nearest_neighbor_diagnostics
    calls = 0

    def diagnostics_with_final_failure(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FloatingPointError("injected final diagnostic failure")
        return original_diagnostics(*args, **kwargs)

    def converged_stub(field, **kwargs):
        return SimpleNamespace(
            field=field,
            energy_history=(1.0, 0.5),
            topological_charge_history=(0.0, 0.0),
            iterations=1,
            termination="gradient_tolerance",
            stationarity_status="first_order_stationary",
            curvature_diagnostics=None,
        )

    monkeypatch.setattr(
        runner,
        "compute_nearest_neighbor_diagnostics",
        diagnostics_with_final_failure,
    )
    monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", converged_stub)
    result = runner.run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert calls == 6
    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["runs"]["isolated_a"]["status"] == "NUMERICAL_FAILURE"
    assert result["runs"]["isolated_a"]["termination"] == "final_diagnostics_failure"
    assert result["runs"]["isolated_a"]["failure_class"] == "FloatingPointError"
    assert result["runs"]["isolated_a"]["final_energy"] is None
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    runner.serialize_constrained_result(result)


def test_low_level_diagnostics_rejects_unrepresentable_energy_coefficients():
    field = vacuum((3, 3, 3))
    for kwargs in ({"f_pi": 1.0e308}, {"e": 1.0e-308}, {"e": 1.0e308}):
        with pytest.raises(ValueError, match="unrepresentable binary64 energy coefficient"):
            compute_nearest_neighbor_diagnostics(field, **kwargs)


@pytest.mark.parametrize("stage", ["initial", "optimization", "final"])
@pytest.mark.parametrize("error_type", [TypeError, ValueError])
def test_programming_errors_propagate_at_each_stage(monkeypatch, stage, error_type):
    def programming_bug(*args, **kwargs):
        raise error_type("injected programming error")

    if stage == "initial":
        monkeypatch.setattr(runner, "compute_nearest_neighbor_diagnostics", programming_bug)
    elif stage == "optimization":
        monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", programming_bug)
    else:
        original_diagnostics = runner.compute_nearest_neighbor_diagnostics
        calls = 0

        def final_programming_bug(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                programming_bug(*args, **kwargs)
            return original_diagnostics(*args, **kwargs)

        def converged_stub(field, **kwargs):
            return SimpleNamespace(
                field=field,
                energy_history=(1.0, 0.5),
                topological_charge_history=(0.0, 0.0),
                iterations=1,
                termination="gradient_tolerance",
                stationarity_status="first_order_stationary",
                curvature_diagnostics=None,
            )

        monkeypatch.setattr(
            runner, "compute_nearest_neighbor_diagnostics", final_programming_bug
        )
        monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", converged_stub)

    with pytest.raises(error_type, match="injected programming error"):
        runner.run_constrained_two_hedgehog_relaxation(**_kwargs())


def test_overflowing_finite_energy_subtraction_withholds_comparison(monkeypatch):
    energies = [1.7e308, 1.7e308, 1.7e308, 1.7e308, 0.0, 0.0]
    current_energy = 0.0

    def finite_diagnostics(*args, **kwargs):
        nonlocal current_energy
        current_energy = energies.pop(0)
        return SimpleNamespace(energy_total=current_energy, topological_charge=0.0)

    def converged_stub(field, **kwargs):
        return SimpleNamespace(
            field=field,
            energy_history=(current_energy,),
            topological_charge_history=(0.0,),
            iterations=1,
            termination="gradient_tolerance",
            stationarity_status="first_order_stationary",
            curvature_diagnostics=None,
        )

    monkeypatch.setattr(
        runner, "compute_nearest_neighbor_diagnostics", finite_diagnostics
    )
    monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", converged_stub)
    result = runner.run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert all(np.isfinite(run["final_energy"]) for run in result["runs"].values())
    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["comparison"]["initial_pair_minus_isolated_energy"] is None
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    assert (
        result["comparison"]["available_only_if_all_three_converged_and_constraints_pass"]
        is False
    )
    runner.serialize_constrained_result(result)


@pytest.mark.parametrize(
    ("stage", "error_type"),
    [
        ("initial", np.linalg.LinAlgError),
        ("initial", OverflowError),
        ("optimization", np.linalg.LinAlgError),
        ("optimization", OverflowError),
        ("final", np.linalg.LinAlgError),
        ("final", OverflowError),
    ],
)
def test_numeric_exception_classes_are_structured_at_each_stage(
    monkeypatch, stage, error_type
):
    error_stage = {
        "initial": "initial_diagnostics_failure",
        "optimization": "optimization_failure",
        "final": "final_diagnostics_failure",
    }[stage]
    injected = error_type("injected numeric failure")

    if stage == "initial":
        def fail_initial(*args, **kwargs):
            raise injected

        monkeypatch.setattr(runner, "compute_nearest_neighbor_diagnostics", fail_initial)
    elif stage == "optimization":
        def fail_optimization(*args, **kwargs):
            raise injected

        monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", fail_optimization)
    else:
        original_diagnostics = runner.compute_nearest_neighbor_diagnostics
        calls = 0

        def fail_final(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise injected
            return original_diagnostics(*args, **kwargs)

        def converged_stub(field, **kwargs):
            return SimpleNamespace(
                field=field,
                energy_history=(1.0,),
                topological_charge_history=(0.0,),
                iterations=1,
                termination="gradient_tolerance",
                stationarity_status="first_order_stationary",
                curvature_diagnostics=None,
                raw_gradient_norm=2.0,
                continuum_l2_residual=3.0,
                active_l2_measure=int(np.count_nonzero(runner._active_mask(field, kwargs["fixed_mask"])))
                * float(np.prod(field.spacing)),
                active_l2_rms_residual=3.0 / np.sqrt(
                    int(np.count_nonzero(runner._active_mask(field, kwargs["fixed_mask"])))
                    * float(np.prod(field.spacing))
                ),
                active_site_count=int(np.count_nonzero(runner._active_mask(field, kwargs["fixed_mask"]))),
            )

        monkeypatch.setattr(runner, "compute_nearest_neighbor_diagnostics", fail_final)
        monkeypatch.setattr(runner, "relax_skyrme_field_nearest_neighbor", converged_stub)

    result = runner.run_constrained_two_hedgehog_relaxation(**_kwargs())
    failures = [run for run in result["runs"].values() if run["status"] == "NUMERICAL_FAILURE"]

    assert result["status"] == "COMPARISON_WITHHELD"
    assert failures
    assert all(run["failure_class"] == error_type.__name__ for run in failures)
    assert all(run["termination"] == error_stage for run in failures)
    assert all(run["final_energy"] is None for run in failures)
    for run in failures:
        diagnostics = run["gradient_diagnostics"]
        assert diagnostics["active_site_count"] > 0
        assert diagnostics["active_l2_measure"] == pytest.approx(
            diagnostics["active_site_count"] * diagnostics["cell_volume"]
        )
        if stage == "final":
            assert diagnostics["raw_euclidean_norm"] == pytest.approx(2.0)
            assert diagnostics["continuum_l2_residual"] == pytest.approx(3.0)
            assert diagnostics["active_l2_rms_residual"] == pytest.approx(
                3.0 / np.sqrt(diagnostics["active_l2_measure"])
            )
        else:
            assert diagnostics["raw_euclidean_norm"] is None
            assert diagnostics["continuum_l2_residual"] is None
            assert diagnostics["active_l2_rms_residual"] is None
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    runner.serialize_constrained_result(result)

def test_constrained_runner_records_mesh_metric_definitions_and_solver_residuals():
    kwargs = _constrained_run_kwargs()
    kwargs.update(
        stationarity_metric="continuum_l2",
        descent_metric="continuum_l2",
    )
    result = run_constrained_two_hedgehog_relaxation(**kwargs)
    assert result["schema_version"] == "su2.constrained_pair_relaxation.result.v2"
    assert result["input"]["schema_version"] == "su2.constrained_pair_relaxation.input.v2"
    assert result["input"]["stationarity_metric"] == "continuum_l2"
    assert result["input"]["descent_metric"] == "continuum_l2"
    assert result["input"]["gradient_tolerance_definition"] == (
        "raw_derivative_euclidean_l2_norm_div_sqrt_cell_volume"
    )
    assert result["input"]["descent_definition"] == (
        "discrete_l2_riesz_gradient_derivative_over_cell_volume"
    )
    assert result["input"]["descent_interpretation"] == (
        "cell_volume_rescales_trial_step_without_changing_direction_on_uniform_grids"
    )
    assert result["input"]["active_l2_measure_definition"] == (
        "active_site_count_times_cell_volume_lumped_quadrature_measure"
    )
    assert result["input"]["active_l2_rms_residual_definition"] == (
        "continuum_l2_residual_div_sqrt_active_l2_measure"
    )
    for run in result["runs"].values():
        diagnostics = run["gradient_diagnostics"]
        assert diagnostics["stationarity_metric"] == "continuum_l2"
        assert diagnostics["descent_metric"] == "continuum_l2"
        assert diagnostics["cell_volume"] == pytest.approx(0.25**3)
        assert diagnostics["active_site_count"] > 0
        assert diagnostics["raw_euclidean_norm"] >= 0.0
        assert diagnostics["continuum_l2_residual"] == pytest.approx(
            diagnostics["raw_euclidean_norm"] / np.sqrt(diagnostics["cell_volume"])
        )
        assert diagnostics["active_l2_measure"] == pytest.approx(
            diagnostics["active_site_count"] * diagnostics["cell_volume"]
        )
        assert diagnostics["active_l2_rms_residual"] == pytest.approx(
            diagnostics["continuum_l2_residual"] / np.sqrt(diagnostics["active_l2_measure"])
        )
    assert serialize_constrained_result(result)


def test_active_l2_measure_overflow_is_structured_before_relaxation(monkeypatch):
    maximum = float(np.finfo(np.float64).max)
    monkeypatch.setattr(runner, "_cell_volume", lambda _spacing: maximum)

    def fail_if_relaxing(*args, **kwargs):
        pytest.fail("active-volume overflow must stop before optimization")

    monkeypatch.setattr(
        runner, "relax_skyrme_field_nearest_neighbor", fail_if_relaxing
    )
    result = run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert result["status"] == "COMPARISON_WITHHELD"
    assert result["comparison"]["initial_pair_minus_isolated_energy"] is None
    assert result["comparison"]["final_pair_minus_isolated_energy"] is None
    for run in result["runs"].values():
        assert run["status"] == "NUMERICAL_FAILURE"
        assert run["failure_class"] == "FloatingPointError"
        assert run["termination"] == "preflight_gradient_measure_failure"
        assert run["final_energy"] is None
        diagnostics = run["gradient_diagnostics"]
        assert diagnostics["active_site_count"] > 1
        assert diagnostics["cell_volume"] == maximum
        assert diagnostics["active_l2_measure"] is None
    assert serialize_constrained_result(result)

def test_geometry_overflow_is_reported_as_numerical_preflight_error():
    kwargs = _kwargs()
    kwargs["shape"] = (5, 5, 5)
    kwargs["spacing"] = (1.0e308, 1.0e-308, 0.1)

    with pytest.raises(runner.NumericalPreflightError, match="during geometry") as exc_info:
        run_constrained_two_hedgehog_relaxation(**kwargs)

    assert exc_info.value.stage == "geometry"
    assert exc_info.value.failure_class == "FloatingPointError"
    assert isinstance(exc_info.value.__cause__, FloatingPointError)


def test_field_construction_numeric_failure_is_stage_specific(monkeypatch):
    def fail(*args, **kwargs):
        raise FloatingPointError("injected field-construction overflow")

    monkeypatch.setattr(runner, "multi_hedgehog", fail)
    with pytest.raises(
        runner.NumericalPreflightError, match="during field construction"
    ) as exc_info:
        run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert exc_info.value.stage == "field construction"
    assert exc_info.value.failure_class == "FloatingPointError"
    assert isinstance(exc_info.value.__cause__, FloatingPointError)


def test_anchor_preflight_numeric_failure_is_stage_specific(monkeypatch):
    def fail(*args, **kwargs):
        raise np.linalg.LinAlgError("injected anchor-fit failure")

    monkeypatch.setattr(runner, "_fit_anchor_rotation", fail)
    with pytest.raises(
        runner.NumericalPreflightError, match="during anchor preflight"
    ) as exc_info:
        run_constrained_two_hedgehog_relaxation(**_kwargs())

    assert exc_info.value.stage == "anchor preflight"
    assert exc_info.value.failure_class == "LinAlgError"
    assert isinstance(exc_info.value.__cause__, np.linalg.LinAlgError)
