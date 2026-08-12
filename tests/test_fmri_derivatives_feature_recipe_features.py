"""Unit + extraction tests for `adapters.fmri_derivatives_feature_recipe`'s
feature-computation core. Synthetic fixtures only -- no raw BOLD, no
downloads.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from adapters.fmri_derivatives_feature_recipe import (
    FmriFeatureRecipeError,
    _build_graph,
    compute_correlation_matrix,
    compute_graph_metrics,
    compute_mean_connectivity,
    extract_from_connectivity_matrix,
    extract_from_graph_summary,
    extract_from_timeseries_table,
    write_recipe_outputs,
)
from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _spec(dataset_id: str = "demo_fmri", **overrides) -> FmriFeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id=dataset_id, feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity", "qc.valid_timepoints"],
        max_subjects=5, max_runs=5, max_timepoints_per_state=100, max_total_timepoints=10000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={
            "connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation.",
            "qc.valid_timepoints": "Number of valid timepoints used per state.",
        },
        confound_policy={"description": "No confounds regression applied to this synthetic fixture."},
        input_kind="timeseries_table",
        limitations=["unit test fixture"], provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FmriFeatureRecipeSpecV1.make(**kwargs)


def _coupled_timeseries(n_parcels=6, n_timepoints=50, coupling=0.0, seed=0):
    rng = np.random.RandomState(seed)
    base = rng.randn(n_parcels, n_timepoints)
    if coupling:
        shared = rng.randn(1, n_timepoints)
        base = base * (1 - coupling) + shared * coupling
    return base


def _write_timeseries_table(tmp_path: Path, dataset_id: str, *, n_subjects: int = 1) -> Path:
    subjects = {}
    for i in range(1, n_subjects + 1):
        subjects[f"sub-{i:02d}"] = {
            "session": None,
            "timeseries": {
                "placebo_label": _coupled_timeseries(coupling=0.0, seed=i).tolist(),
                "drug_label": _coupled_timeseries(coupling=0.85, seed=i + 100).tolist(),
            },
        }
    data = {"dataset_id": dataset_id, "atlas_or_parcellation": "Schaefer100", "subjects": subjects}
    path = tmp_path / f"{dataset_id}_timeseries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── compute_correlation_matrix / compute_mean_connectivity ────────────────


def test_compute_correlation_matrix_returns_none_for_constant_signal():
    arr = np.ones((4, 20))
    assert compute_correlation_matrix(arr) is None


def test_compute_correlation_matrix_returns_none_for_all_nan_row():
    arr = _coupled_timeseries(n_parcels=4, coupling=0.2)
    arr[1, :] = np.nan
    assert compute_correlation_matrix(arr) is None


def test_compute_correlation_matrix_returns_valid_matrix_for_real_signal():
    arr = _coupled_timeseries(n_parcels=4, coupling=0.3)
    matrix = compute_correlation_matrix(arr)
    assert matrix is not None
    assert matrix.shape == (4, 4)
    assert np.allclose(np.diag(matrix), 1.0)


def test_compute_mean_connectivity_excludes_diagonal():
    matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    # diagonal is all 1.0 -- if it leaked in, mean_connectivity would be > 0
    assert compute_mean_connectivity(matrix) == 0.0


def test_compute_mean_connectivity_none_matrix_is_nan():
    value = compute_mean_connectivity(None)
    assert value != value  # NaN


def test_timeseries_table_mean_connectivity_discriminates_coupling():
    low = compute_mean_connectivity(compute_correlation_matrix(_coupled_timeseries(coupling=0.0, seed=1)))
    high = compute_mean_connectivity(compute_correlation_matrix(_coupled_timeseries(coupling=0.9, seed=1)))
    assert high > low


# ── compute_graph_metrics / _build_graph ───────────────────────────────────


def test_build_graph_absolute_threshold():
    matrix = np.array([[1.0, 0.9, 0.1], [0.9, 1.0, 0.05], [0.1, 0.05, 1.0]])
    graph = _build_graph(matrix, {"threshold": 0.5, "threshold_method": "absolute_threshold"})
    assert graph.has_edge(0, 1)
    assert not graph.has_edge(0, 2)


def test_build_graph_unsupported_threshold_method_raises():
    matrix = np.eye(4)
    with pytest.raises(FmriFeatureRecipeError):
        _build_graph(matrix, {"threshold": 0.5, "threshold_method": "not_a_real_method"})


def test_compute_graph_metrics_global_efficiency_and_degree():
    arr = _coupled_timeseries(n_parcels=8, coupling=0.6)
    matrix = compute_correlation_matrix(arr)
    metrics = compute_graph_metrics(
        matrix, requested_features=["connectivity.global_efficiency", "connectivity.degree"],
        graph_policy={"threshold": 0.3, "threshold_method": "absolute_threshold"},
    )
    assert metrics["connectivity.global_efficiency"] == metrics["connectivity.global_efficiency"]  # not NaN
    assert metrics["connectivity.degree"] >= 0.0


def test_compute_graph_metrics_small_worldness_skips_disconnected_graph():
    matrix = np.eye(6)  # no off-diagonal correlation at all -- disconnected once thresholded
    metrics = compute_graph_metrics(
        matrix, requested_features=["connectivity.small_worldness"],
        graph_policy={"threshold": 0.99, "threshold_method": "absolute_threshold"},
    )
    value = metrics["connectivity.small_worldness"]
    assert value != value  # NaN
    assert "connectivity.small_worldness" in metrics["_skip_reasons"]


def test_compute_graph_metrics_none_matrix_marks_all_skipped():
    metrics = compute_graph_metrics(
        None, requested_features=["connectivity.global_efficiency"],
        graph_policy={"threshold": 0.3, "threshold_method": "absolute_threshold"},
    )
    assert metrics["connectivity.global_efficiency"] != metrics["connectivity.global_efficiency"]
    assert "connectivity.global_efficiency" in metrics["_skip_reasons"]


def test_compute_graph_metrics_no_graph_requiring_feature_is_a_noop():
    metrics = compute_graph_metrics(None, requested_features=["connectivity.mean_connectivity"], graph_policy={})
    assert metrics == {"_skip_reasons": {}}


# ── extraction: timeseries_table ────────────────────────────────────────


def test_extract_from_timeseries_table_happy_path(tmp_path):
    table_path = _write_timeseries_table(tmp_path, "ds_a", n_subjects=2)
    spec = _spec("ds_a")
    result = extract_from_timeseries_table(spec, table_path)
    assert len(result.subjects_used) == 2
    assert len(result.rows) == 4  # 2 subjects x 2 requested features
    assert result.states_observed == ["drug", "placebo"]


def test_constant_signal_skipped_safely_not_fabricated(tmp_path):
    data = {
        "dataset_id": "ds_const", "atlas_or_parcellation": "Schaefer100",
        "subjects": {
            "sub-01": {
                "session": None,
                "timeseries": {"placebo_label": np.ones((4, 30)).tolist(), "drug_label": _coupled_timeseries(n_parcels=4, coupling=0.5).tolist()},
            },
        },
    }
    path = tmp_path / "const_timeseries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    spec = _spec("ds_const", requested_features=["connectivity.mean_connectivity"],
                  feature_definitions={"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."})
    result = extract_from_timeseries_table(spec, path)
    assert result.rows == []
    reasons = {s["reason"] for s in result.skipped_inputs}
    assert any("correlation is undefined" in r for r in reasons)
    assert any("NaN" in r for r in reasons)


def test_respects_max_subjects(tmp_path):
    table_path = _write_timeseries_table(tmp_path, "ds_bound", n_subjects=4)
    spec = _spec("ds_bound", max_subjects=2)
    result = extract_from_timeseries_table(spec, table_path)
    assert len(result.subjects_used) + len(result.skipped_subjects) <= 4
    assert len(result.subjects_used) <= 2


def test_respects_max_total_timepoints(tmp_path):
    table_path = _write_timeseries_table(tmp_path, "ds_tp", n_subjects=2)
    spec = _spec("ds_tp", max_total_timepoints=50)  # 2 subjects x 100 timepoints (50+50) would exceed this
    result = extract_from_timeseries_table(spec, table_path)
    assert len(result.subjects_used) < 2


# ── extraction: connectivity_matrix ─────────────────────────────────────


def test_connectivity_matrix_mode_computes_graph_metrics(tmp_path):
    matrix = compute_correlation_matrix(_coupled_timeseries(n_parcels=6, coupling=0.7))
    matrix2 = compute_correlation_matrix(_coupled_timeseries(n_parcels=6, coupling=0.2, seed=7))
    data = {
        "dataset_id": "ds_matrix", "atlas_or_parcellation": "Schaefer100",
        "subjects": {"sub-01": {"session": None, "matrices": {"placebo_label": matrix2.tolist(), "drug_label": matrix.tolist()}}},
    }
    path = tmp_path / "connectivity_matrix.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    spec = _spec(
        "ds_matrix", input_kind="connectivity_matrix",
        requested_features=["connectivity.mean_connectivity", "connectivity.global_efficiency"],
        feature_definitions={
            "connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation.",
            "connectivity.global_efficiency": "Global efficiency of the thresholded connectivity graph.",
        },
        graph_policy={"threshold": 0.2, "threshold_method": "absolute_threshold"},
    )
    result = extract_from_connectivity_matrix(spec, path)
    assert len(result.rows) == 2
    assert result.subjects_used == ["sub-01"]


# ── extraction: graph_summary ────────────────────────────────────────────


def test_graph_summary_mode_writes_features_and_mapping(tmp_path):
    summary = {
        "format": "graph_summary", "dataset_id": "ds_graphsummary", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"note": "already-computed graph metrics from an external pipeline"},
        "confound_policy": "24-param + aCompCor",
        "feature_definitions": {"connectivity.global_efficiency": "Global efficiency of the connectivity graph."},
        "subjects": [
            {"subject_id": "sub-01", "metrics": {"connectivity.global_efficiency": {"source_value": 0.31, "target_value": 0.42}}},
        ],
    }
    summary_path = tmp_path / "graph_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    spec = _spec(
        "ds_graphsummary", input_kind="graph_summary",
        requested_features=["connectivity.global_efficiency"],
        feature_definitions={"connectivity.global_efficiency": "Global efficiency of the connectivity graph."},
    )
    result = extract_from_graph_summary(spec, summary_path)
    assert len(result.rows) == 1
    assert result.rows[0]["source_value"] == 0.31
    assert result.rows[0]["target_value"] == 0.42

    features_path, mapping_path, manifest, summary_out_path = write_recipe_outputs(
        spec, result, "outputs/feature_recipes/features-test-graph-summary",
    )
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        assert mapping["confound_policy"] == "No confounds regression applied to this synthetic fixture."
        assert manifest.features_written == 1
    finally:
        import shutil

        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_graph_summary_mode_filters_to_requested_features_only(tmp_path):
    summary = {
        "format": "graph_summary", "dataset_id": "ds_graphsummary2", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"note": "already-computed"},
        "confound_policy": "24-param",
        "feature_definitions": {
            "connectivity.global_efficiency": "Global efficiency.",
            "connectivity.modularity": "Modularity.",
        },
        "subjects": [
            {"subject_id": "sub-01", "metrics": {
                "connectivity.global_efficiency": {"source_value": 0.1, "target_value": 0.2},
                "connectivity.modularity": {"source_value": 0.5, "target_value": 0.6},
            }},
        ],
    }
    summary_path = tmp_path / "graph_summary2.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    spec = _spec(
        "ds_graphsummary2", input_kind="graph_summary",
        requested_features=["connectivity.global_efficiency"],
        feature_definitions={"connectivity.global_efficiency": "Global efficiency."},
    )
    result = extract_from_graph_summary(spec, summary_path)
    assert len(result.rows) == 1
    assert result.rows[0]["feature_name"] == "connectivity.global_efficiency"
