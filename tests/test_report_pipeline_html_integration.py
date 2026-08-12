"""Tests for `--include-html` integration into
`workflows.report_pipeline.run_report_pipeline` and
`workflows.export_report_pack`. Real already-committed contract artifacts
and existing demo fixtures only -- no downloads.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures import report_pipeline_demo as demo
from workflows.report_pipeline import ReportPipelineSpecV1, run_report_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def test_include_html_works_with_existing_evidence_bundle_mode(tmp_path):
    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    out = "outputs/report_packs/html-int-existing-bundle"
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root=out, evidence_bundle_path=str(bundle_path),
        include_report=True, include_html=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "render_html_report_pack" in manifest.steps_completed
    html_meta = manifest.metadata.get("html_report_pack")
    assert html_meta is not None
    assert (_REPO_ROOT / html_meta["index_html_path"]).exists()


def test_include_html_works_with_builtin_ds005620_mode():
    out = "outputs/report_packs/html-int-builtin"
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=out, source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True, include_html=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "render_html_report_pack" in manifest.steps_completed
    assert "render_html_report_pack" not in manifest.steps_skipped
    html_meta = manifest.metadata["html_report_pack"]
    index_path = _REPO_ROOT / html_meta["index_html_path"]
    assert index_path.exists()
    assert index_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_include_html_works_with_mne_bids_derived_features_mode(tmp_path):
    features_path, mapping_path = demo.write_mne_bids_derived_features_demo(tmp_path)
    out = "outputs/report_packs/html-int-mne-derived"
    spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_derived_features", dataset_id="demo_eeg_derived_ds", modality="EEG",
        output_root=out, feature_table_path=str(features_path), mapping_path=str(mapping_path),
        registry_path=str(_SEED_REGISTRY), include_evidence_bundle=True, include_report=True, include_html=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "render_html_report_pack" in manifest.steps_completed


def test_default_without_include_html_is_unchanged():
    out = "outputs/report_packs/html-int-default"
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=out, source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    assert "render_html_report_pack" not in manifest.steps_completed
    assert "html_report_pack" not in manifest.metadata
    assert not (_REPO_ROOT / out / "html").exists()


def test_failed_pipeline_does_not_render_html():
    out = "outputs/report_packs/html-int-failed"
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="x", modality="EEG",
        output_root=out, evidence_bundle_path="does/not/exist/EvidenceBundle.json",
        include_html=True, limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "failed"
    assert not (_REPO_ROOT / out / "html").exists()
    assert "html_report_pack" not in manifest.metadata


def test_cli_export_report_pack_include_html_end_to_end(tmp_path):
    from workflows.report_pipeline import ReportPipelineSpecV1 as Spec

    spec = Spec.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/html-int-cli", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / "pipeline_spec.json"
    spec.write_json(spec_path)

    result = subprocess.run(
        [sys.executable, "-m", "workflows.export_report_pack", "--spec", str(spec_path), "--include-html"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "html_report_pack" in payload
    assert (_REPO_ROOT / payload["html_report_pack"]["index_html_path"]).exists()


def test_cli_export_report_pack_without_include_html_writes_no_html(tmp_path):
    from workflows.report_pipeline import ReportPipelineSpecV1 as Spec

    spec = Spec.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/html-int-cli-nohtml", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / "pipeline_spec.json"
    spec.write_json(spec_path)

    result = subprocess.run(
        [sys.executable, "-m", "workflows.export_report_pack", "--spec", str(spec_path)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "html_report_pack" not in payload
    assert not (_REPO_ROOT / "outputs" / "report_packs" / "html-int-cli-nohtml" / "html").exists()


def test_html_out_override_via_spec(tmp_path):
    features_path, mapping_path = demo.write_fmri_derived_features_demo(tmp_path)
    out = "outputs/report_packs/html-int-custom-out"
    spec = ReportPipelineSpecV1.make(
        input_mode="fmri_derived_features", dataset_id="demo_fmri_derived_ds", modality="fMRI",
        output_root=out, feature_table_path=str(features_path), mapping_path=str(mapping_path),
        registry_path=str(_SEED_REGISTRY), include_evidence_bundle=True, include_report=True,
        include_html=True, html_out=f"{out}/custom-html-location",
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    html_meta = manifest.metadata["html_report_pack"]
    assert "custom-html-location" in html_meta["index_html_path"]


def test_html_output_guardrail_clean():
    out = "outputs/report_packs/html-int-guardrail"
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=out, source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True, include_html=True,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    index_path = _REPO_ROOT / manifest.metadata["html_report_pack"]["index_html_path"]
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", str(index_path)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
