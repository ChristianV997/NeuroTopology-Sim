"""Tests for optional static two-hedgehog sweep plotting."""

import builtins
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from field_theory.su2.interaction_sweep import (
    InteractionGridLevel,
    TwoHedgehogSweepSpec,
    run_two_hedgehog_interaction_sweep,
)
from field_theory.su2.interaction_visualization import (
    InteractionSweepVisualizationUnavailable,
    build_interaction_sweep_plot_data,
    plot_two_hedgehog_interaction_sweep,
)


def _rehash_point_payload(point, payload):
    metadata = payload["input_metadata"]
    metadata_bytes = json.dumps(
        metadata,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["input_sha256"] = hashlib.sha256(metadata_bytes).hexdigest()
    result_json = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    result_sha256 = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
    return replace(
        point,
        evaluator_result_json=result_json,
        result_sha256=result_sha256,
    )


@pytest.fixture(scope="module")
def sweep_result():
    spec = TwoHedgehogSweepSpec(
        radius=0.5,
        # Deliberately reverse separation order: plotted x values should be
        # sorted while curve order follows the declared orientation/grid axes.
        separation_values=(1.0, 0.5),
        relative_isorotations=(
            (1.0, 0.0, 0.0, 0.0),
            (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)),
        ),
        grid_levels=(
            InteractionGridLevel("coarse", (5, 5, 5), (1.0, 1.0, 1.0)),
            InteractionGridLevel("fine", (9, 9, 9), (0.5, 0.5, 0.5)),
        ),
        code_revision="synthetic-visualization-test",
    )
    return run_two_hedgehog_interaction_sweep(spec)


def test_plot_data_labels_axes_groups_curves_and_preserves_order(sweep_result):
    data = build_interaction_sweep_plot_data(sweep_result)

    assert data["axes"]["x"] == {
        "symbol": "s",
        "label": "Dimensionless separation, s = d/R",
        "unit": "dimensionless",
    }
    assert data["axes"]["y"] == {
        "symbol": "V_h",
        "label": "Dimensionless lattice excess, V_h = ΔE/E₀",
        "unit": "dimensionless_lattice",
    }
    expected_order = [
        (rotation, level.level_id)
        for rotation in sweep_result.spec.relative_isorotations
        for level in sweep_result.spec.grid_levels
    ]
    assert [
        (tuple(curve["relative_isorotation"]), curve["grid_level"])
        for curve in data["curves"]
    ] == expected_order
    assert all(curve["s_values"] == [1.0, 2.0] for curve in data["curves"])

    by_key_and_s = {
        (
            point.relative_isorotation,
            point.grid_level.level_id,
            point.separation / sweep_result.spec.radius,
        ): point.evaluator_result["excess"]["V_h"]
        for point in sweep_result.points
    }
    for curve in data["curves"]:
        key = (tuple(curve["relative_isorotation"]), curve["grid_level"])
        assert curve["v_h_values"] == pytest.approx(
            [by_key_and_s[(key[0], key[1], s)] for s in curve["s_values"]]
        )
        assert len(curve["point_refs"]) == 2
        assert all(ref["result_sha256"] for ref in curve["point_refs"])

    assert "comparisons" in data["grid_level_note"]
    assert "convergence is not assumed" in data["grid_level_note"]
    assert data["scientific_pass"] is False
    assert data["evidence_class"] == "synthetic_static_model"
    assert "physical potential" not in data["scope_note"].lower()


def test_plot_data_is_deterministic_and_does_not_import_matplotlib(
    sweep_result, monkeypatch
):
    real_import = builtins.__import__

    def reject_matplotlib(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError("synthetic optional dependency absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_matplotlib)
    first = build_interaction_sweep_plot_data(sweep_result)
    second = build_interaction_sweep_plot_data(sweep_result)
    assert first == second


def test_fresh_module_import_succeeds_with_matplotlib_blocked():
    script = r'''
import builtins
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "matplotlib" or name.startswith("matplotlib."):
        raise ModuleNotFoundError("synthetic optional dependency absence")
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
import field_theory.su2.interaction_visualization
'''
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_plot_data_rejects_swapped_separations_with_valid_evaluator_json(sweep_result):
    points = list(sweep_result.points)
    same_curve = [
        (index, point)
        for index, point in enumerate(points)
        if point.relative_isorotation == sweep_result.spec.relative_isorotations[0]
        and point.grid_level == sweep_result.spec.grid_levels[0]
    ]
    (first_index, first), (second_index, second) = same_curve
    points[first_index] = replace(first, separation=second.separation)
    points[second_index] = replace(second, separation=first.separation)
    assert points[first_index].evaluator_result_json == first.evaluator_result_json
    assert points[second_index].evaluator_result_json == second.evaluator_result_json

    tampered = replace(sweep_result, points=tuple(points))
    with pytest.raises(ValueError, match="evaluator input metadata"):
        build_interaction_sweep_plot_data(tampered)


def test_plot_data_rejects_point_vector_orientation_and_grid_mismatches(sweep_result):
    first = sweep_result.points[0]
    second = next(
        point
        for point in sweep_result.points
        if point.relative_isorotation != first.relative_isorotation
        and point.separation == first.separation
        and point.grid_level == first.grid_level
    )
    third = next(
        point
        for point in sweep_result.points
        if point.relative_isorotation == first.relative_isorotation
        and point.separation == first.separation
        and point.grid_level != first.grid_level
    )

    corruptions = [
        replace(first, separation_vector=(9.0, 0.0, 0.0)),
        replace(first, relative_isorotation=second.relative_isorotation),
        replace(first, grid_level=third.grid_level),
    ]
    for corrupted_point in corruptions:
        points = tuple(
            corrupted_point if point.point_id == first.point_id else point
            for point in sweep_result.points
        )
        with pytest.raises(ValueError, match="evaluator input metadata"):
            build_interaction_sweep_plot_data(replace(sweep_result, points=points))


@pytest.mark.parametrize("field", ["radius", "f_pi", "e"])
def test_plot_data_rejects_spec_model_values_that_disagree_with_evaluator_metadata(
    sweep_result, field
):
    original = getattr(sweep_result.spec, field)
    changed_spec = replace(sweep_result.spec, **{field: original * 1.5})
    with pytest.raises(ValueError, match="evaluator input metadata"):
        build_interaction_sweep_plot_data(replace(sweep_result, spec=changed_spec))


@pytest.mark.parametrize(
    ("metadata_key", "replacement"),
    [
        ("ansatz", "other_ansatz"),
        ("energy_method", "other_energy_method"),
        ("vacuum", [0.0, 0.0, 0.0, 1.0]),
        ("composition_order", "U_B * U_A"),
        ("allow_overlaps_in_product_ansatz", False),
    ],
)
def test_plot_data_rejects_unsupported_evaluator_metadata(
    sweep_result, metadata_key, replacement
):
    point = sweep_result.points[0]
    payload = point.evaluator_result
    payload["input_metadata"][metadata_key] = replacement
    tampered = _rehash_point_payload(point, payload)
    points = (tampered, *sweep_result.points[1:])
    with pytest.raises(ValueError, match="unsupported evaluator input metadata"):
        build_interaction_sweep_plot_data(replace(sweep_result, points=points))


def test_plot_data_rejects_unknown_evaluator_result_schema(sweep_result):
    point = sweep_result.points[0]
    payload = point.evaluator_result
    payload["schema_version"] = "su2.two_hedgehog_interaction.result.v999"
    tampered = _rehash_point_payload(point, payload)
    points = (tampered, *sweep_result.points[1:])
    with pytest.raises(ValueError, match="unsupported evaluator result schema"):
        build_interaction_sweep_plot_data(replace(sweep_result, points=points))


@pytest.mark.parametrize(
    ("section", "key", "increment", "message"),
    [
        ("energy_pair", "energy_total", 1.0, "energy breakdown"),
        ("excess", "delta_energy_sigma", 1.0, "delta_energy_sigma"),
        ("excess", "delta_energy_total", 1.0, "delta_energy_total"),
        ("excess", "V_h", 1.0, "V_h"),
    ],
)
def test_plot_data_rejects_inconsistent_rehashed_energy_payload(
    sweep_result, section, key, increment, message
):
    point = sweep_result.points[0]
    payload = point.evaluator_result
    payload[section][key] += increment
    tampered = _rehash_point_payload(point, payload)
    points = (tampered, *sweep_result.points[1:])
    with pytest.raises(ValueError, match=message):
        build_interaction_sweep_plot_data(replace(sweep_result, points=points))


def test_plot_data_rejects_invalid_evaluator_status_with_value_error(sweep_result):
    point = sweep_result.points[0]
    payload = point.evaluator_result
    payload["status"] = "PASS"
    tampered = _rehash_point_payload(point, payload)
    points = (tampered, *sweep_result.points[1:])
    with pytest.raises(ValueError, match="unsupported evaluator evidence status"):
        build_interaction_sweep_plot_data(replace(sweep_result, points=points))


def test_near_identical_orientations_have_distinct_stable_legend_labels():
    base = math.sqrt(0.5)
    spec = TwoHedgehogSweepSpec(
        radius=0.5,
        separation_values=(0.5,),
        relative_isorotations=(
            (base, 0.0, 0.0, base),
            (base + 1.0e-11, 0.0, 0.0, base),
        ),
        grid_levels=(
            InteractionGridLevel("base", (5, 5, 5), (1.0, 1.0, 1.0)),
        ),
    )
    labels = [
        curve["label"]
        for curve in build_interaction_sweep_plot_data(
            run_two_hedgehog_interaction_sweep(spec)
        )["curves"]
    ]
    assert len(labels) == 2
    assert labels[0] != labels[1]
    assert "orientation[00]" in labels[0]
    assert "orientation[01]" in labels[1]


def test_render_reports_clear_import_error_when_matplotlib_is_unavailable(
    sweep_result, monkeypatch, tmp_path
):
    real_import = builtins.__import__

    def reject_matplotlib(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError("synthetic optional dependency absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_matplotlib)
    destination = tmp_path / "nested" / "interaction.png"
    with pytest.raises(
        InteractionSweepVisualizationUnavailable,
        match="optional matplotlib dependency",
    ):
        plot_two_hedgehog_interaction_sweep(sweep_result, destination)
    assert not destination.exists()


def test_render_writes_png_when_matplotlib_is_installed(sweep_result, tmp_path):
    pytest.importorskip("matplotlib")
    destination = tmp_path / "plots" / "interaction.png"
    returned = plot_two_hedgehog_interaction_sweep(sweep_result, destination)
    assert returned == destination
    assert destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
