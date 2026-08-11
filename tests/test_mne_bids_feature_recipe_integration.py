"""Downstream integration (--run-mne-bids-adapter equivalent, library-level)
+ guardrail checks for `adapters.mne_bids_feature_recipe`. Synthetic
fixtures only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from adapters.mne_bids_feature_recipe import run_feature_recipe, write_recipe_outputs
from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_epoch_table(tmp_path: Path, dataset_id: str) -> Path:
    rng = np.random.RandomState(0)
    sfreq = 100.0
    n_samples = 200

    def epoch(alpha_boost):
        t = np.arange(n_samples) / sfreq
        sig = rng.randn(n_samples) * 1e-5 + alpha_boost * np.sin(2 * np.pi * 10 * t) * 1e-5
        return [sig.tolist(), sig.tolist()]

    table = {
        "sfreq": sfreq, "channels": ["C3", "C4"],
        "subjects": {
            "sub-01": {"session": None, "epochs": {"rest_marker": [epoch(0.0) for _ in range(5)], "task_marker": [epoch(3.0) for _ in range(5)]}},
            "sub-02": {"session": None, "epochs": {"rest_marker": [epoch(0.0) for _ in range(5)], "task_marker": [epoch(3.0) for _ in range(5)]}},
        },
    }
    path = tmp_path / f"{dataset_id}_epoch_table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def _spec(dataset_id: str) -> FeatureRecipeSpecV1:
    return FeatureRecipeSpecV1.make(
        dataset_id=dataset_id, feature_set_id="mne_bids_spectral_v1",
        source_state="rest", target_state="task",
        requested_features=["spectral.alpha_power", "qc.valid_epoch_count"],
        max_subjects=5, max_runs=5, max_epochs_per_state=10, max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={
            "spectral.alpha_power": "Mean relative alpha-band power over valid epochs.",
            "qc.valid_epoch_count": "Count of valid epochs used per state.",
        },
        input_kind="epoch_table",
        limitations=["integration test fixture"], provenance="integration test fixture",
    )


def test_run_mne_bids_adapter_produces_valid_transition_records(tmp_path):
    from adapters.mne_bids import export_mne_bids_derived_transitions

    dataset_id = "feature_recipe_integration_ds_1"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-1")
    try:
        adapter_result = export_mne_bids_derived_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            updated_registry_out=out / "reg.json",
        )
        assert adapter_result["n_written"] == 2
        for record in adapter_result["records"]:
            assert record.validate() == []
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_include_phase_space_writes_valid_coordinates(tmp_path):
    from adapters.mne_bids import export_mne_bids_derived_transitions

    dataset_id = "feature_recipe_integration_ds_2"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-2")
    try:
        adapter_result = export_mne_bids_derived_transitions(
            features_path, mapping_path, out, registry_path=_SEED_REGISTRY,
            include_phase_space=True, updated_registry_out=out / "reg.json",
        )
        assert adapter_result["phase_space"] is not None
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_include_evidence_bundle_and_report_work(tmp_path):
    from adapters.mne_bids import export_mne_bids_derived_transitions

    dataset_id = "feature_recipe_integration_ds_3"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-3")
    try:
        adapter_result = export_mne_bids_derived_transitions(
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
    from adapters.mne_bids import export_mne_bids_derived_transitions

    dataset_id = "feature_recipe_integration_ds_4"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-4")
    try:
        adapter_result = export_mne_bids_derived_transitions(
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
         "adapters/mne_bids_feature_recipe.py", "adapters/mne_bids_feature_recipe_schema.py",
         "adapters/mne_bids_feature_recipe_validation.py", "adapters/mne_bids_feature_recipe_cli.py"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_transition_report_passes_guardrail_scan(tmp_path):
    from adapters.mne_bids import export_mne_bids_derived_transitions

    dataset_id = "feature_recipe_integration_ds_5"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    out = tmp_path / "out"
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-5")
    try:
        export_mne_bids_derived_transitions(
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
    dataset_id = "feature_recipe_integration_ds_6"
    table_path = _write_epoch_table(tmp_path, dataset_id)
    spec = _spec(dataset_id)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/integration-test-6")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        text = json.dumps(summary).lower() + json.dumps(manifest.to_dict()).lower()
        for banned in ("is evidence", "clinical", "diagnos", "treatment", "biomarker", "consciousness_detect", "spiritual"):
            assert banned not in text
    finally:
        shutil.rmtree(features_path.parent, ignore_errors=True)


def test_recipe_never_infers_states_from_event_names(tmp_path):
    """A raw event label present in the table but absent from
    event_state_mapping must never silently become a state."""
    table = {
        "sfreq": 100.0, "channels": ["C3"],
        "subjects": {"sub-01": {"session": None, "epochs": {
            "some_unmapped_label": [[[0.0] * 200]],
        }}},
    }
    path = tmp_path / "unmapped_epoch_table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    spec = _spec("feature_recipe_integration_ds_7")
    result = run_feature_recipe(spec, epoch_table_path=path)
    assert result.rows == []
    assert result.skipped_subjects
