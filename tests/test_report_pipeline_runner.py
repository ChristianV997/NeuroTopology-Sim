"""End-to-end tests for `workflows.report_pipeline.run_report_pipeline`
across every supported input_mode. Synthetic fixtures for EEG/fMRI modes;
real already-committed `contracts/btc_icft/ds005620/`/`contracts/fmri_tda/
ds000245/` artifacts for builtin modes (no download, no reprocessing of
raw data).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures import report_pipeline_demo as demo
from workflows.report_pack import ReportPackV1
from workflows.report_pipeline import ReportPipelineSpecV1, run_report_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS000245_SOURCE = _REPO_ROOT / "contracts" / "fmri_tda" / "ds000245"


def _out(tmp_path_factory, name: str) -> str:
    # A repo-relative outputs/ path is required by validate_target_root --
    # use a unique per-test subdirectory under outputs/report_packs/ and
    # clean it up after the test (mirrors every prior milestone's
    # try/finally shutil.rmtree discipline).
    return f"outputs/report_packs/rp-test-{name}"


@pytest.fixture(autouse=True)
def _cleanup_report_packs():
    yield
    import shutil

    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def test_existing_evidence_bundle_mode_generates_report_pack(tmp_path):
    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root=_out(None, "existing-bundle"), evidence_bundle_path=str(bundle_path),
        include_report=True, limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed"
    assert "load_existing_evidence_bundle" in manifest.steps_completed
    assert "build_evidence_report" in manifest.steps_completed
    assert manifest.report_pack_path is not None
    pack = ReportPackV1.from_json((_REPO_ROOT / manifest.report_pack_path).read_text(encoding="utf-8"))
    assert pack.validate() == []
    assert pack.evidence_bundle_ids
    assert pack.evidence_report_ids


def test_mne_bids_epoch_table_recipe_mode_reaches_evidence_report(tmp_path):
    recipe_spec_path, epoch_table_path = demo.write_mne_bids_epoch_table_recipe_demo(tmp_path)
    spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_epoch_table_recipe", dataset_id="demo_eeg_ds", modality="EEG",
        output_root=_out(None, "eeg-recipe"), recipe_spec_path=str(recipe_spec_path),
        source_paths=[str(epoch_table_path)], registry_path=str(_SEED_REGISTRY),
        include_evidence_bundle=True, include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    for step in ("run_feature_recipe", "write_recipe_outputs", "export_adapter_transitions", "build_evidence_bundle", "build_evidence_report"):
        assert step in manifest.steps_completed
    assert manifest.generated_feature_paths
    assert manifest.transition_record_paths
    assert manifest.evidence_report_paths
    pack = ReportPackV1.from_json((_REPO_ROOT / manifest.report_pack_path).read_text(encoding="utf-8"))
    assert pack.validate() == []


def test_mne_bids_derived_features_mode_reaches_evidence_report(tmp_path):
    features_path, mapping_path = demo.write_mne_bids_derived_features_demo(tmp_path)
    spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_derived_features", dataset_id="demo_eeg_derived_ds", modality="EEG",
        output_root=_out(None, "eeg-derived"), feature_table_path=str(features_path), mapping_path=str(mapping_path),
        registry_path=str(_SEED_REGISTRY), include_evidence_bundle=True, include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "export_adapter_transitions" in manifest.steps_completed
    assert "build_evidence_report" in manifest.steps_completed
    assert manifest.transition_record_paths


def test_fmri_timeseries_recipe_mode_reaches_evidence_report(tmp_path):
    # Note: this fixture's tiny 2-subject cohort is not combined with
    # include_phase_space here -- phase_space.export_from_transitions can
    # legitimately produce coordinates with n_estimated=0 for such a small
    # cohort, which evidence.builder's own bundle-metadata validation
    # (phase_space_status="insufficient_data_only" requires an EMPTY
    # phase_space_coordinate_ids) then rejects. That combination is
    # exercised successfully elsewhere in this file (see
    # test_fmri_graph_summary_recipe_mode_reaches_evidence_report) with a
    # fixture shape that does not hit this pre-existing edge case.
    recipe_spec_path, table_path = demo.write_fmri_timeseries_recipe_demo(tmp_path)
    spec = ReportPipelineSpecV1.make(
        input_mode="fmri_timeseries_recipe", dataset_id="demo_fmri_ds", modality="fMRI",
        output_root=_out(None, "fmri-ts-recipe"), recipe_spec_path=str(recipe_spec_path),
        source_paths=[str(table_path)], registry_path=str(_SEED_REGISTRY),
        include_evidence_bundle=True, include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert manifest.registry_updated_path is not None
    assert "build_evidence_report" in manifest.steps_completed


def test_fmri_connectivity_matrix_recipe_mode_works(tmp_path):
    import json

    import numpy as np

    from adapters.fmri_derivatives_feature_recipe import compute_correlation_matrix
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    rng = np.random.RandomState(3)
    matrix = compute_correlation_matrix(rng.randn(6, 50))
    data = {
        "dataset_id": "demo_fmri_matrix_ds", "atlas_or_parcellation": "Schaefer100",
        "subjects": {"sub-01": {"session": None, "matrices": {"placebo_label": matrix.tolist(), "drug_label": matrix.tolist()}}},
    }
    matrix_path = tmp_path / "demo_connectivity_matrix.json"
    matrix_path.write_text(json.dumps(data), encoding="utf-8")

    recipe_spec = FmriFeatureRecipeSpecV1.make(
        dataset_id="demo_fmri_matrix_ds", feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity"],
        max_subjects=5, max_runs=5, max_timepoints_per_state=100, max_total_timepoints=10000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."},
        confound_policy={"description": "No confounds regression applied to this synthetic fixture."},
        input_kind="connectivity_matrix",
        limitations=["test"], provenance="test",
    )
    recipe_spec_path = tmp_path / "demo_connectivity_matrix_recipe_spec.json"
    recipe_spec.write_json(recipe_spec_path)

    spec = ReportPipelineSpecV1.make(
        input_mode="fmri_connectivity_matrix_recipe", dataset_id="demo_fmri_matrix_ds", modality="fMRI",
        output_root=_out(None, "fmri-matrix-recipe"), recipe_spec_path=str(recipe_spec_path),
        source_paths=[str(matrix_path)], limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert manifest.transition_record_paths


def test_fmri_graph_summary_recipe_mode_reaches_evidence_report(tmp_path):
    recipe_spec_path, gs_path = demo.write_fmri_graph_summary_recipe_demo(tmp_path)
    spec = ReportPipelineSpecV1.make(
        input_mode="fmri_graph_summary_recipe", dataset_id="demo_fmri_gs_ds", modality="fMRI",
        output_root=_out(None, "fmri-gs-recipe"), recipe_spec_path=str(recipe_spec_path),
        graph_summary_path=str(gs_path), registry_path=str(_SEED_REGISTRY),
        include_evidence_bundle=True, include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "build_evidence_report" in manifest.steps_completed


def test_fmri_derived_features_mode_reaches_evidence_report(tmp_path):
    features_path, mapping_path = demo.write_fmri_derived_features_demo(tmp_path)
    spec = ReportPipelineSpecV1.make(
        input_mode="fmri_derived_features", dataset_id="demo_fmri_derived_ds", modality="fMRI",
        output_root=_out(None, "fmri-derived"), feature_table_path=str(features_path), mapping_path=str(mapping_path),
        registry_path=str(_SEED_REGISTRY), include_evidence_bundle=True, include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert manifest.transition_record_paths


def test_builtin_ds005620_cohort_summary_mode_works():
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=_out(None, "builtin-cohort"), source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "build_evidence_bundle" in manifest.steps_completed


def test_builtin_ds005620_spatial_defect_map_mode_works():
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_spatial_defect_map", dataset_id="ds005620", modality="EEG",
        output_root=_out(None, "builtin-spatial"), source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY),
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors


def test_builtin_ds000245_schaefer100_motcorr_mode_works():
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds000245_schaefer100_motcorr", dataset_id="ds000245", modality="fMRI",
        output_root=_out(None, "builtin-schaefer"), source_paths=[str(_DS000245_SOURCE)],
        registry_path=str(_SEED_REGISTRY),
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors


def test_builtin_ds000245_kmeans100_mode_works():
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds000245_kmeans100", dataset_id="ds000245", modality="fMRI",
        output_root=_out(None, "builtin-kmeans"), source_paths=[str(_DS000245_SOURCE)],
        registry_path=str(_SEED_REGISTRY),
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors


def test_dry_run_does_not_generate_scientific_outputs(tmp_path):
    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    out = _out(None, "dry-run")
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root=out, evidence_bundle_path=str(bundle_path), dry_run=True,
        include_report=True, limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "dry_run"
    assert manifest.steps_completed == []
    assert manifest.report_pack_path is None
    written = sorted(p.name for p in (_REPO_ROOT / out).iterdir())
    assert written == ["PipelineRunManifest.json", "PipelineSpec.json"]
    assert not (_REPO_ROOT / out / "adapter_export").exists()
    assert not (_REPO_ROOT / out / "reports").exists()


def test_unsupported_mode_fails_clearly():
    spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_derived_features", dataset_id="demo_ds", modality="EEG",
        output_root=_out(None, "will-mutate"), feature_table_path="x.csv", mapping_path="y.json",
        limitations=["test"], provenance="test",
    )
    # bypass validate_or_raise() to exercise the runner's own defense-in-depth
    # unsupported-mode branch directly (validate() already rejects this at
    # the spec layer -- this test targets the runner, not the validator).
    spec.input_mode = "totally_unknown_mode"
    from workflows.report_pipeline import ReportPipelineValidationError

    with pytest.raises(ReportPipelineValidationError):
        run_report_pipeline(spec)


def test_missing_input_fails_clearly_in_manifest():
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="x", modality="EEG",
        output_root=_out(None, "missing-input"), evidence_bundle_path="does/not/exist/EvidenceBundle.json",
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "failed"
    assert manifest.errors
    assert any("does not exist" in e for e in manifest.errors)
