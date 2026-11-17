"""Contract tests for deterministic, bounded static interaction sweeps."""

import json
import math

import numpy as np
import pytest

from field_theory.su2 import interaction_sweep
from field_theory.su2.interaction_sweep import (
    InteractionGridLevel,
    TwoHedgehogSweepSpec,
    run_two_hedgehog_interaction_sweep,
)


@pytest.fixture
def small_spec():
    return TwoHedgehogSweepSpec(
        radius=0.75,
        separation_values=(0.5, 1.0),
        relative_isorotations=(
            (1.0, 0.0, 0.0, 0.0),
            (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)),
        ),
        grid_levels=(
            InteractionGridLevel("coarse", (7, 7, 7), (1.0, 1.0, 1.0)),
            InteractionGridLevel("fine", (13, 13, 13), (0.5, 0.5, 0.5)),
        ),
        separation_direction=(1.0, 0.0, 0.0),
        f_pi=1.2,
        e=0.8,
        code_revision="synthetic-test-revision",
    )


def test_sweep_records_dimensionless_controls_and_static_only_claim_scope():
    spec = TwoHedgehogSweepSpec(
        radius=0.75,
        separation_values=(1.0,),
        relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
        grid_levels=(InteractionGridLevel("coarse", (7, 7, 7), (1.0, 1.0, 1.0)),),
        f_pi=1.2,
        e=0.8,
        code_revision="revision-under-test",
    )

    result = run_two_hedgehog_interaction_sweep(spec)
    record = result.to_dict()
    point = record["points"][0]
    metadata = point["evaluator_input_metadata"]
    controls = spec.to_dict()["dimensionless_controls"]

    assert record["schema_version"] == "su2.two_hedgehog_interaction_sweep.v1"
    assert record["status"] == "SYNTHETIC_STATIC_PRODUCT_ANSATZ_LANDSCAPE"
    assert record["evidence_class"] == "synthetic_static_model"
    assert record["scientific_pass"] is False
    assert record["claim_scope"] == "product_ansatz_excess_energy_landscape_only"
    assert record["not_a_force"] and record["not_a_relaxed_potential"]
    assert record["not_a_physical_prediction"] and record["not_time_evolution"]
    assert controls["lambda"] == pytest.approx(0.96)
    assert controls["E0"] == pytest.approx(1.5)
    assert controls["rho"] == pytest.approx(0.72)
    assert controls["s_values"] == pytest.approx([1.0 / 0.75])
    assert metadata["code_revision"] == "revision-under-test"
    assert metadata["separation_vector"] == [1.0, 0.0, 0.0]
    assert metadata["f_pi"] == pytest.approx(1.2)
    assert metadata["e"] == pytest.approx(0.8)
    assert metadata["dimensionless_controls"]["E0"] == pytest.approx(1.5)
    assert point["grid_geometry"]["dimensionless_spacing_h"] == pytest.approx(
        [0.96, 0.96, 0.96]
    )
    assert point["dimensionless_excess_E_over_E0"] == pytest.approx(
        point["evaluator_result"]["excess"]["V_h"]
    )
    assert point["stencil_overlap"] is point["evaluator_result"]["support_stencils_overlap"]


def test_cartesian_sweep_order_and_grid_metadata_are_explicit(small_spec):
    result = run_two_hedgehog_interaction_sweep(small_spec)
    records = result.to_dict()["points"]

    assert len(records) == 8
    assert [item["point_id"] for item in records] == [f"point-{i:04d}" for i in range(8)]
    assert [
        (item["separation"], item["relative_isorotation"], item["grid_level"])
        for item in records
    ] == [
        (separation, list(rotation), level)
        for separation in small_spec.separation_values
        for rotation in small_spec.relative_isorotations
        for level in ("coarse", "fine")
    ]
    assert all(item["evaluator_input_sha256"] for item in records)
    assert all(item["result_sha256"] for item in records)
    assert all(item["evaluator_result"]["scientific_pass"] is False for item in records)
    assert [level["box_extent"] for level in small_spec.to_dict()["grid_levels"]] == [
        [6.0, 6.0, 6.0],
        [6.0, 6.0, 6.0],
    ]


def test_repeated_sweeps_have_deterministic_json_ids_and_point_checksums(small_spec):
    first = run_two_hedgehog_interaction_sweep(small_spec)
    second = run_two_hedgehog_interaction_sweep(small_spec)

    assert first.to_json() == second.to_json()
    assert first.sweep_id == second.sweep_id
    assert [point.result_sha256 for point in first.points] == [
        point.result_sha256 for point in second.points
    ]
    decoded = json.loads(first.to_json())
    assert decoded["sweep_id"] == first.sweep_id
    assert all(math.isfinite(point["dimensionless_excess_E_over_E0"]) for point in decoded["points"])
    json.dumps(decoded, allow_nan=False)


def test_exposed_evaluator_payload_cannot_mutate_sweep_or_stale_its_checksums(small_spec):
    result = run_two_hedgehog_interaction_sweep(small_spec)
    original_json = result.to_json()
    point = result.points[0]

    exposed = point.evaluator_result
    exposed["status"] = "PASS"
    exposed["input_metadata"]["separation_distance"] = -999.0

    assert result.to_json() == original_json
    assert point.evaluator_result["status"] == "SYNTHETIC_STATIC_PRODUCT_ANSATZ"
    assert point.result_sha256 == result.points[0].result_sha256


@pytest.mark.parametrize(
    "changes",
    [
        {"radius": 0.0},
        {"radius": True},
        {"separation_values": ()},
        {"separation_values": (-0.1,)},
        {"separation_values": (float("nan"),)},
        {"separation_values": (True,)},
        {"separation_values": (1.0, 1.0)},
        {"separation_direction": (2.0, 0.0, 0.0)},
        {"separation_direction": (True, 0.0, 0.0)},
        {"relative_isorotations": ((2.0, 0.0, 0.0, 0.0),)},
        {"relative_isorotations": ((True, 0.0, 0.0, 0.0),)},
        {
            "relative_isorotations": (
                (1.0, 0.0, 0.0, 0.0),
                (-1.0, 0.0, 0.0, 0.0),
            )
        },
        {"f_pi": float("inf")},
        {"e": 0.0},
    ],
)
def test_spec_rejects_malformed_or_duplicate_axes(changes):
    arguments = dict(
        radius=0.75,
        separation_values=(0.5,),
        relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
        grid_levels=(InteractionGridLevel("base", (7, 7, 7), (1.0, 1.0, 1.0)),),
    )
    arguments.update(changes)
    with pytest.raises(ValueError):
        TwoHedgehogSweepSpec(**arguments)


def test_grid_refinement_requires_identical_box_extents():
    with pytest.raises(ValueError, match="same box extent"):
        TwoHedgehogSweepSpec(
            radius=0.75,
            separation_values=(0.5,),
            relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
            grid_levels=(
                InteractionGridLevel("coarse", (7, 7, 7), (1.0, 1.0, 1.0)),
                InteractionGridLevel("inconsistent", (13, 13, 13), (0.6, 0.5, 0.5)),
            ),
        )


def test_valid_normalized_direction_survives_floating_point_renormalization():
    direction = (
        -0.2264309255994313,
        -0.7060091858498858,
        0.6710291092253498,
    )
    spec = TwoHedgehogSweepSpec(
        radius=0.75,
        separation_values=(0.5,),
        relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
        grid_levels=(InteractionGridLevel("base", (7, 7, 7), (1.0, 1.0, 1.0)),),
        separation_direction=direction,
    )

    result = run_two_hedgehog_interaction_sweep(spec)
    normalized = np.asarray(spec.separation_direction)
    assert np.linalg.norm(normalized) == pytest.approx(1.0, abs=1e-15)
    assert result.to_dict()["points"][0]["separation_vector"] == pytest.approx(
        tuple(0.5 * component for component in spec.separation_direction), abs=1e-15
    )


def test_sweep_budget_is_rechecked_before_any_evaluator_call(monkeypatch):
    spec = TwoHedgehogSweepSpec(
        radius=0.1,
        separation_values=(0.0,),
        relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
        grid_levels=(InteractionGridLevel("large", (40, 40, 40), (0.1, 0.1, 0.1)),),
    )
    # Frozen dataclasses can still be mutated through low-level APIs. The
    # runner repeats preflight so a changed spec cannot trigger partial work.
    object.__setattr__(spec, "separation_values", tuple(float(i) for i in range(80)))
    evaluator_calls = []

    def unexpected_evaluator(**kwargs):
        evaluator_calls.append(kwargs)
        raise AssertionError("budget must be rejected before evaluator execution")

    monkeypatch.setattr(interaction_sweep, "evaluate_two_hedgehog_interaction", unexpected_evaluator)
    with pytest.raises(ValueError, match="node volume limit"):
        run_two_hedgehog_interaction_sweep(spec)
    assert evaluator_calls == []


def test_every_axis_point_must_fit_every_grid_before_evaluation(monkeypatch):
    original_evaluator = interaction_sweep.evaluate_two_hedgehog_interaction
    evaluator_calls = []

    def recording_evaluator(**kwargs):
        evaluator_calls.append(kwargs)
        return original_evaluator(**kwargs)

    monkeypatch.setattr(
        interaction_sweep,
        "evaluate_two_hedgehog_interaction",
        recording_evaluator,
    )
    with pytest.raises(ValueError, match="support"):
        spec = TwoHedgehogSweepSpec(
            radius=0.75,
            separation_values=(0.5, 8.0),
            relative_isorotations=((1.0, 0.0, 0.0, 0.0),),
            grid_levels=(
                InteractionGridLevel("coarse", (7, 7, 7), (1.0, 1.0, 1.0)),
                InteractionGridLevel("fine", (13, 13, 13), (0.5, 0.5, 0.5)),
            ),
        )
        run_two_hedgehog_interaction_sweep(spec)
    assert evaluator_calls == []


def test_sweep_rejects_non_spec_input_before_evaluation(monkeypatch):
    evaluator_calls = []
    monkeypatch.setattr(
        interaction_sweep,
        "evaluate_two_hedgehog_interaction",
        lambda **kwargs: evaluator_calls.append(kwargs),
    )
    with pytest.raises(ValueError, match="TwoHedgehogSweepSpec"):
        run_two_hedgehog_interaction_sweep({})
    assert evaluator_calls == []
