import hashlib
import json

import pytest

from field_theory.su2 import constrained_interaction_sweep as sweep
from field_theory.su2.constrained_interaction import (
    NumericalPreflightError,
    run_constrained_two_hedgehog_relaxation,
)
from field_theory.su2.constrained_interaction_visualization import (
    build_constrained_sensitivity_plot_data,
    render_constrained_sensitivity_png,
    serialize_constrained_sensitivity_plot_data,
)


REVISION = "9e950316e031ae60d05e21626231c47bd785ac1f"


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _reseal_sweep(result, *, reseal_nested=False):
    for case in result["cases"]:
        nested = case.get("single_run_result")
        if reseal_nested and isinstance(nested, dict):
            nested["input_sha256"] = _digest(nested["input"])
            nested_payload = {
                key: value for key, value in nested.items() if key != "result_sha256"
            }
            nested["result_sha256"] = _digest(nested_payload)
        case["case_sha256"] = sweep._case_digest(case)
    result["sweep_id"] = sweep._sha256(
        {
            "schema_version": sweep.SWEEP_SCHEMA_VERSION,
            "spec": result["spec"],
            "case_sha256": [case["case_sha256"] for case in result["cases"]],
        }
    )
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _digest(payload)
    return result


def _runner_input(kwargs):
    rotation = list(kwargs["relative_isorotation"])
    return {
        "schema_version": "su2.constrained_pair_relaxation.input.v2",
        "code_revision": kwargs["code_revision"],
        "data_mode": "synthetic_only",
        "randomness": "none_deterministic",
        "shape": list(kwargs["shape"]),
        "spacing": list(kwargs["spacing"]),
        "radius": kwargs["radius"],
        "anchor_radius": kwargs["anchor_radius"],
        "separation_vector": list(kwargs["separation_vector"]),
        "relative_isorotation_input": rotation,
        "relative_isorotation_used": rotation,
        "f_pi": kwargs["f_pi"],
        "e": kwargs["e"],
        "solver": "nearest_neighbor_forward_link_v2",
        "stationarity_metric": kwargs["stationarity_metric"],
        "descent_metric": kwargs["descent_metric"],
        "max_iterations_per_run": kwargs["max_iterations"],
        "initial_step": kwargs["initial_step"],
        "gradient_tolerance": kwargs["gradient_tolerance"],
        "max_backtracks_per_iteration": kwargs["max_backtracks"],
        "orientation_tolerance_rad": kwargs["orientation_tolerance_rad"],
        "orientation_residual_tolerance": kwargs["orientation_residual_tolerance"],
        "charge_drift_tolerance": kwargs["charge_drift_tolerance"],
    }


def _single_result(excess, *, available=True, input_record=None):
    payload = {
        "schema_version": "su2.constrained_pair_relaxation.result.v2",
        "status": "COMPARISON_AVAILABLE" if available else "COMPARISON_WITHHELD",
        "input": (
            {"schema_version": "su2.constrained_pair_relaxation.input.v2"}
            if input_record is None
            else input_record
        ),
        "input_sha256": None,
        "comparison": {
            "initial_pair_minus_isolated_energy": None,
            "final_pair_minus_isolated_energy": excess if available else None,
            "available_only_if_all_three_converged_and_constraints_pass": available,
        },
    }
    payload["input_sha256"] = _digest(payload["input"])
    payload["result_sha256"] = _digest(payload)
    return payload


def _small_spec(**changes):
    arguments = dict(
        radius=1.5,
        separation_vector=(4.0, 0.0, 0.0),
        relative_isorotation=(1.0, 0.0, 0.0, 0.0),
        grid_levels=(
            sweep.ConstrainedSensitivityGridLevel(
                "coarse", (13, 13, 13), (0.75, 0.75, 0.75)
            ),
            sweep.ConstrainedSensitivityGridLevel(
                "fine", (19, 19, 19), (0.5, 0.5, 0.5)
            ),
        ),
        anchor_radii=(0.75, 1.0),
        code_revision=REVISION,
        max_iterations=1,
        max_backtracks=1,
    )
    arguments.update(changes)
    return sweep.ConstrainedInteractionSensitivitySpec(**arguments)


def test_recommended_six_point_matrix_is_fixed_box_and_under_aggregate_budget():
    spec = sweep.recommended_constrained_sensitivity_spec(REVISION)

    assert spec.point_count == 6
    assert [level.box_extent for level in spec.grid_levels] == [
        (14.0, 14.0, 14.0),
        (14.0, 14.0, 14.0),
        (14.0, 14.0, 14.0),
    ]
    assert spec.planned_estimated_node_visits == 97_968_150
    assert spec.planned_estimated_node_visits < sweep.MAX_SWEEP_ESTIMATED_NODE_VISITS
    assert max(spec._estimated_visits(level) for level in spec.grid_levels) == 32_266_647
    assert all(level.node_count <= 32_768 for level in spec.grid_levels)
    assert spec.stationarity_metric == "continuum_l2"
    assert spec.descent_metric == "continuum_l2"


def test_grid_levels_must_preserve_the_physical_box():
    with pytest.raises(ValueError, match="same box extent"):
        _small_spec(
            grid_levels=(
                sweep.ConstrainedSensitivityGridLevel(
                    "coarse", (13, 13, 13), (0.75, 0.75, 0.75)
                ),
                sweep.ConstrainedSensitivityGridLevel(
                    "wrong-box", (19, 19, 19), (0.6, 0.5, 0.5)
                ),
            )
        )


def test_invalid_metric_container_is_rejected_as_input_error():
    with pytest.raises(ValueError, match="stationarity_metric must be"):
        _small_spec(stationarity_metric=[])


def test_aggregate_budget_is_rejected_before_any_solver_call(monkeypatch):
    def fail_if_called(**kwargs):
        pytest.fail("sweep work must be preflighted before solving")

    monkeypatch.setattr(
        sweep, "run_constrained_two_hedgehog_relaxation", fail_if_called
    )
    with pytest.raises(ValueError, match="aggregate estimated node-visit budget"):
        sweep.recommended_constrained_sensitivity_spec(REVISION).__class__(
            **{
                **sweep.recommended_constrained_sensitivity_spec(REVISION).__dict__,
                "max_iterations": 41,
            }
        )


def test_mocked_sweep_is_deterministic_and_records_anchor_spread(monkeypatch):
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        delta = 0.1 if kwargs["anchor_radius"] == 0.75 else 0.2
        return _single_result(delta, input_record=_runner_input(kwargs))

    monkeypatch.setattr(sweep, "run_constrained_two_hedgehog_relaxation", fake_runner)
    spec = _small_spec()
    first = sweep.run_constrained_interaction_sensitivity_sweep(spec)
    first_json = first.to_json()
    second = sweep.run_constrained_interaction_sensitivity_sweep(spec)

    assert first_json == second.to_json()
    assert len(calls) == 8
    assert all(call["stationarity_metric"] == "continuum_l2" for call in calls)
    assert all(call["descent_metric"] == "continuum_l2" for call in calls)

    data = first.to_dict()
    assert data["case_count"] == 4
    assert data["comparison_available_count"] == 4
    assert data["status"] == "ALL_CASES_EVALUATED"
    assert data["scientific_pass"] is False
    assert data["spec"]["not_a_binding_energy"] is True
    assert data["anchor_sensitivity_by_grid"][0]["anchor_spread"] == pytest.approx(0.1)
    assert data["anchor_sensitivity_by_grid"][0]["sign_stability"] == "all_positive"
    assert json.loads(first_json)["result_sha256"] == data["result_sha256"]


def test_numerical_preflight_failure_is_a_row_and_other_cases_continue(monkeypatch):
    calls = []

    def fail_one_then_succeed(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise NumericalPreflightError(
                "field construction", FloatingPointError("injected overflow")
            )
        return _single_result(0.0, input_record=_runner_input(kwargs))

    monkeypatch.setattr(
        sweep, "run_constrained_two_hedgehog_relaxation", fail_one_then_succeed
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()

    assert len(calls) == 4
    assert result["case_count"] == 4
    assert result["numerical_preflight_failure_count"] == 1
    assert result["comparison_available_count"] == 3
    assert result["cases"][0]["status"] == "NUMERICAL_PREFLIGHT_FAILURE"
    assert result["cases"][0]["single_run_result"] is None
    assert result["cases"][0]["failure"]["stage"] == "field construction"
    assert result["cases"][0]["final_pair_minus_isolated_energy"] is None
    assert result["comparison_status"] == "SOME_WITHHELD_OR_FAILED"


def test_known_anchor_identifiability_rejection_is_labeled_and_later_cases_run(monkeypatch):
    calls = []

    def reject_first_case(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ValueError(
                "anchor pion vectors do not span two non-collinear directions"
            )
        return _single_result(0.0, input_record=_runner_input(kwargs))

    monkeypatch.setattr(sweep, "run_constrained_two_hedgehog_relaxation", reject_first_case)
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()

    assert len(calls) == 4
    assert result["case_preflight_rejection_count"] == 1
    assert result["cases"][0]["status"] == "CASE_PREFLIGHT_REJECTED"
    assert result["cases"][0]["failure"]["category"] == "case_input_preflight_rejection"
    assert result["cases"][0]["failure"]["stage"] == "anchor_identifiability"
    assert result["cases"][0]["single_run_result"] is None
    assert result["comparison_available_count"] == 3


def test_unexpected_value_error_is_not_reclassified_as_numerical_failure(monkeypatch):
    error = ValueError("programming/contract error")

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(sweep, "run_constrained_two_hedgehog_relaxation", fail)
    with pytest.raises(ValueError) as raised:
        sweep.run_constrained_interaction_sensitivity_sweep(_small_spec())
    assert raised.value is error


def test_sweep_checksum_rejects_case_mutation(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["cases"][0]["final_pair_minus_isolated_energy"] = 999.0
    with pytest.raises(ValueError, match="case checksum mismatch"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("scientific_pass", True, "cannot assert a scientific pass"),
        ("status", "SCIENTIFICALLY_VALIDATED", "status is inconsistent"),
        ("evidence_class", "empirical", "evidence class must remain synthetic"),
    ],
)
def test_sweep_serializer_rejects_resealed_claim_escalation(
    monkeypatch, field, value, message
):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result[field] = value
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match=message):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_requires_synthetic_spec_even_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["spec"]["data_mode"] = "empirical"
    result["sweep_id"] = sweep._sha256(
        {
            "schema_version": sweep.SWEEP_SCHEMA_VERSION,
            "spec": result["spec"],
            "case_sha256": [case["case_sha256"] for case in result["cases"]],
        }
    )
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match="spec must remain synthetic"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_revalidates_spec_axes_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["spec"]["anchor_radii"] = [0.75, 0.75]
    _reseal_sweep(result)

    with pytest.raises(ValueError, match="spec does not satisfy its input schema"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_recomputes_anchor_summary_from_case_rows(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["anchor_sensitivity_by_grid"][0]["anchor_spread"] = 1_000.0
    _reseal_sweep(result)

    with pytest.raises(ValueError, match="anchor summary disagrees with case rows"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_rejects_resealed_top_level_nested_disagreement(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    case = result["cases"][0]
    case["comparison_available"] = False
    case["final_pair_minus_isolated_energy"] = None
    case["case_sha256"] = sweep._case_digest(case)
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match="availability disagrees"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_rejects_omitted_case_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["cases"].pop()
    result["case_count"] -= 1
    result["comparison_available_count"] -= 1
    result["comparison_status"] = "SOME_WITHHELD_OR_FAILED"
    _reseal_sweep(result)

    with pytest.raises(ValueError, match="do not exhaust the declared grid-anchor plan"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_binds_row_to_plan_and_nested_runner_input(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    case = result["cases"][0]
    case["case_input"]["anchor_radius"] = 99.0
    _reseal_sweep(result)

    with pytest.raises(ValueError, match="does not match the declared grid-anchor plan"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_rejects_nested_input_mismatch_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["cases"][0]["single_run_result"]["input"]["anchor_radius"] = 77.0
    _reseal_sweep(result, reseal_nested=True)

    with pytest.raises(ValueError, match="single-run input does not match"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_rejects_unknown_nested_status_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    result["cases"][0]["single_run_result"]["status"] = "MAGICALLY_CONVERGED"
    _reseal_sweep(result, reseal_nested=True)

    with pytest.raises(ValueError, match="outside the declared comparison status set"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_sweep_serializer_rejects_malformed_failure_metadata(monkeypatch):
    def fail(**kwargs):
        raise NumericalPreflightError("field construction", FloatingPointError("bad"))

    monkeypatch.setattr(sweep, "run_constrained_two_hedgehog_relaxation", fail)
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec()).to_dict()
    case = result["cases"][0]
    case["failure"] = ["not", "an", "object"]
    case["case_sha256"] = sweep._case_digest(case)
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match="record is inconsistent"):
        sweep.serialize_constrained_interaction_sensitivity_result(result)


def test_one_case_sweep_matches_the_direct_constrained_runner():
    level = sweep.ConstrainedSensitivityGridLevel(
        "small", (13, 13, 13), (0.75, 0.75, 0.75)
    )
    spec = sweep.ConstrainedInteractionSensitivitySpec(
        radius=1.5,
        separation_vector=(4.0, 0.0, 0.0),
        relative_isorotation=(1.0, 0.0, 0.0, 0.0),
        grid_levels=(level,),
        anchor_radii=(1.1,),
        code_revision=REVISION,
        max_iterations=1,
        max_backtracks=1,
    )
    direct = run_constrained_two_hedgehog_relaxation(
        shape=level.shape,
        spacing=level.spacing,
        radius=spec.radius,
        separation_vector=spec.separation_vector,
        relative_isorotation=spec.relative_isorotation,
        anchor_radius=spec.anchor_radii[0],
        code_revision=spec.code_revision,
        f_pi=spec.f_pi,
        e=spec.e,
        max_iterations=spec.max_iterations,
        initial_step=spec.initial_step,
        gradient_tolerance=spec.gradient_tolerance,
        max_backtracks=spec.max_backtracks,
        orientation_tolerance_rad=spec.orientation_tolerance_rad,
        orientation_residual_tolerance=spec.orientation_residual_tolerance,
        charge_drift_tolerance=spec.charge_drift_tolerance,
        stationarity_metric=spec.stationarity_metric,
        descent_metric=spec.descent_metric,
    )

    result = sweep.run_constrained_interaction_sensitivity_sweep(spec).to_dict()
    assert result["cases"][0]["single_run_result"] == direct
    assert result["case_count"] == 1


def test_one_anchor_sweep_does_not_claim_zero_sensitivity(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(-0.25, input_record=_runner_input(kwargs)),
    )
    spec = _small_spec(
        grid_levels=(
            sweep.ConstrainedSensitivityGridLevel(
                "coarse", (13, 13, 13), (0.75, 0.75, 0.75)
            ),
        ),
        anchor_radii=(0.75,),
    )
    summary = sweep.run_constrained_interaction_sensitivity_sweep(spec).to_dict()[
        "anchor_sensitivity_by_grid"
    ][0]

    assert summary["all_anchor_comparisons_available"] is True
    assert summary["anchor_spread_assessed"] is False
    assert summary["anchor_spread"] is None
    assert summary["sign_stability"] == "not_assessed_single_anchor"


def test_plot_data_keeps_withheld_values_null_and_preserves_scientific_scope(monkeypatch):
    calls = []

    def one_available_one_withheld(**kwargs):
        calls.append(kwargs)
        if kwargs["anchor_radius"] == 0.75:
            return _single_result(-0.2, input_record=_runner_input(kwargs))
        return _single_result(
            None, available=False, input_record=_runner_input(kwargs)
        )

    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        one_available_one_withheld,
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec())
    data = build_constrained_sensitivity_plot_data(result)

    assert len(calls) == 4
    assert data["schema_version"] == "su2.constrained_interaction_sensitivity_plot_data.v1"
    assert data["not_a_binding_energy"] is True
    assert data["not_a_force"] is True
    assert data["not_a_continuum_extrapolation"] is True
    assert data["unavailable_points_are_not_zero"] is True
    assert any(point["excess"] is None for point in data["status_points"])
    assert all(
        point["excess"] is not None
        for point in data["status_points"]
        if point["comparison_available"]
    )
    assert json.loads(serialize_constrained_sensitivity_plot_data(data))[
        "plot_data_sha256"
    ] == data["plot_data_sha256"]


def test_plot_data_serializer_rejects_resealed_claim_escalation(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(
            0.125, input_record=_runner_input(kwargs)
        ),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec())
    data = build_constrained_sensitivity_plot_data(result)
    data["scientific_pass"] = True
    payload = {key: value for key, value in data.items() if key != "plot_data_sha256"}
    data["plot_data_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match="cannot assert a scientific pass"):
        serialize_constrained_sensitivity_plot_data(data)


def test_plot_data_serializer_rejects_unknown_status_after_resealing(monkeypatch):
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(
            0.125, input_record=_runner_input(kwargs)
        ),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec())
    data = build_constrained_sensitivity_plot_data(result)
    data["status_points"][0]["status"] = "MAGICALLY_CONVERGED"
    data["status_points"][0]["comparison_available"] = False
    data["status_points"][0]["excess"] = None
    payload = {key: value for key, value in data.items() if key != "plot_data_sha256"}
    data["plot_data_sha256"] = _digest(payload)

    with pytest.raises(ValueError, match="unavailable plot point has an unknown status"):
        serialize_constrained_sensitivity_plot_data(data)


def test_plot_renderer_is_headless_and_marks_unavailable_cases(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.setattr(
        sweep,
        "run_constrained_two_hedgehog_relaxation",
        lambda **kwargs: _single_result(0.125, input_record=_runner_input(kwargs)),
    )
    result = sweep.run_constrained_interaction_sensitivity_sweep(_small_spec())
    output = tmp_path / "constrained-sensitivity.png"

    rendered = render_constrained_sensitivity_png(result, output, dpi=80)

    assert rendered == output
    assert output.is_file()
    assert output.stat().st_size > 1000
