"""Downstream integration (--run-fmri-derivatives-adapter equivalent,
library-level) + guardrail checks for
`adapters.fmri_derivatives_feature_recipe`. Synthetic fixtures only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from adapters.fmri_derivatives_feature_recipe import run_feature_recipe, write_recipe_outputs
from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_timeseries_table(tmp_path: Path, dataset_id: str) -> Path:
    rng = np.random.RandomState(0)

    def ts(coupling):
        base = rng.randn(6, 50)
        if coupling:
            shared = rng.randn(1, 50)
            base = base * (1 - coupling) + shared * coupling
        return base.tolist()

    data = {
        "dataset_id": dataset_id, "atlas_or_parcellation": "Schaefer100",
        "subjects": {
            "sub-01": {"session": None, "timeseries": {"placebo_label": ts(0.0), "drug_label": ts(0.85)}},
            "sub-02": {"session": None, "timeseries": {"placebo_label": ts(0.0), "drug_label": ts(0.85)}},
        },
    }
    path = tmp_path / f"{dataset_id}_timeseries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _spec(dataset_id: str) -> FmriFeatureRecipeSpecV1:
    return FmriFeatureRecipeSpecV1.make(
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
        limitations=["integration test fixture"], provenance="integration test fixture",
    )


def test_run_fmri_derivatives_adapter_produces_valid_transition_records(tmp_path):
    from adapters.fmri_derivatives import export_fmri_derivative_transitions

    dataset_id = "fmri_feature_recipe_integration_ds_1"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-1")
    try:
        adapter_result = export_fmri_derivative_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
        )
        assert adapter_result["n_written"] == 2
        for record in adapter_result["records"]:
            assert record.validate() == []
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_include_phase_space_writes_valid_coordinates(tmp_path):
    from adapters.fmri_derivatives import export_fmri_derivative_transitions

    dataset_id = "fmri_feature_recipe_integration_ds_2"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-2")
    try:
        adapter_result = export_fmri_derivative_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            include_phase_space=True, updated_registry_out=out / "reg.json",
        )
        assert adapter_result["phase_space"] is not None
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_include_evidence_bundle_and_report_work(tmp_path):
    from adapters.fmri_derivatives import export_fmri_derivative_transitions

    dataset_id = "fmri_feature_recipe_integration_ds_3"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-3")
    try:
        adapter_result = export_fmri_derivative_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
        )
        bundle = adapter_result["evidence_bundle"]
        assert bundle is not None
        assert bundle.validate() == []
        assert adapter_result["report"] is not None
        assert (out / "EvidenceReport.md").exists()
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_claim_scope_not_promoted(tmp_path):
    from adapters.fmri_derivatives import export_fmri_derivative_transitions

    dataset_id = "fmri_feature_recipe_integration_ds_4"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-4")
    try:
        adapter_result = export_fmri_derivative_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            include_evidence_bundle=True, updated_registry_out=out / "reg.json",
        )
        bundle = adapter_result["evidence_bundle"]
        assert bundle.claim_scope_ceiling == "exploratory_metric"
        assert bundle.generated_claim_scope == "exploratory_metric"
        assert bundle.null_control_summary["status"] == "not_provided"
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


# ── guardrails ─────────────────────────────────────────────────────────


def test_no_forbidden_overclaim_language_in_recipe_source():
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py",
         "adapters/fmri_derivatives_feature_recipe.py", "adapters/fmri_derivatives_feature_recipe_schema.py",
         "adapters/fmri_derivatives_feature_recipe_validation.py", "adapters/fmri_derivatives_feature_recipe_cli.py"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_transition_report_passes_guardrail_scan(tmp_path):
    from adapters.fmri_derivatives import export_fmri_derivative_transitions

    dataset_id = "fmri_feature_recipe_integration_ds_5"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-5")
    try:
        export_fmri_derivative_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
        )
        scan = subprocess.run(
            [sys.executable, "tools/check_claim_guardrails.py", str(out / "EvidenceReport.md"), str(out / "EvidenceReport.json")],
            capture_output=True, text=True, cwd=str(_REPO_ROOT),
        )
        assert scan.returncode == 0, scan.stdout + scan.stderr
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_recipe_outputs_are_not_described_as_evidence(tmp_path):
    dataset_id = "fmri_feature_recipe_integration_ds_6"
    table_path = _write_timeseries_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, input_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/fmri-integration-test-6")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        text = json.dumps(summary).lower() + json.dumps(manifest.to_dict()).lower()
        for banned in ("is evidence", "clinical", "diagnos", "treatment", "biomarker", "consciousness_detect", "spiritual"):
            assert banned not in text
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_recipe_never_infers_states_from_labels(tmp_path):
    """A raw state label present in the input but absent from
    state_mapping must never silently become a state."""
    data = {
        "dataset_id": "fmri_feature_recipe_integration_ds_7", "atlas_or_parcellation": "Schaefer100",
        "subjects": {"sub-01": {"session": None, "timeseries": {"some_unmapped_label": [[0.0] * 50] * 4}}},
    }
    path = tmp_path / "unmapped_timeseries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    spec = _spec("fmri_feature_recipe_integration_ds_7")
    result = run_feature_recipe(spec, input_path=path)
    assert result.rows == []
    assert result.skipped_subjects
