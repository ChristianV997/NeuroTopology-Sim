"""Subprocess CLI tests for `python -m workflows.export_report_pack`.
Synthetic fixtures + real already-committed contract artifacts only --
no network access, no raw dataset download.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures import report_pipeline_demo as demo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "workflows.export_report_pack", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup_report_packs():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _write_builtin_spec(tmp_path: Path, name: str, **overrides) -> Path:
    from workflows.report_pipeline import ReportPipelineSpecV1

    kwargs = dict(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/cli-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY),
        limitations=["cli test"], provenance="cli test fixture",
    )
    kwargs.update(overrides)
    spec = ReportPipelineSpecV1.make(**kwargs)
    path = tmp_path / f"{name}_pipeline_spec.json"
    spec.write_json(path)
    return path


def test_cli_happy_path_works(tmp_path):
    spec_path = _write_builtin_spec(tmp_path, "happy")
    result = _run_cli("--spec", str(spec_path), "--include-report")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert "build_evidence_bundle" in payload["steps_completed"]
    out = _REPO_ROOT / "outputs" / "report_packs" / "cli-test-happy"
    assert (out / "ReportPack.json").exists()
    assert (out / "PipelineSpec.json").exists()
    assert (out / "PipelineRunManifest.json").exists()


def test_cli_dry_run_writes_no_scientific_output(tmp_path):
    spec_path = _write_builtin_spec(tmp_path, "dryrun")
    result = _run_cli("--spec", str(spec_path), "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    out = _REPO_ROOT / "outputs" / "report_packs" / "cli-test-dryrun"
    assert not (out / "adapter_export").exists()
    assert not (out / "ReportPack.json").exists()


def test_cli_out_override_works(tmp_path):
    spec_path = _write_builtin_spec(tmp_path, "outoverride")
    result = _run_cli("--spec", str(spec_path), "--out", "outputs/report_packs/cli-test-outoverride-actual")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["output_root"] == "outputs/report_packs/cli-test-outoverride-actual"
    assert (_REPO_ROOT / "outputs" / "report_packs" / "cli-test-outoverride-actual").exists()
    assert not (_REPO_ROOT / "outputs" / "report_packs" / "cli-test-outoverride").exists()


def test_cli_missing_spec_file_fails():
    result = _run_cli("--spec", "does/not/exist_pipeline_spec.json")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_output_root_fails(tmp_path):
    spec_path = _write_builtin_spec(tmp_path, "badroot", output_root="outputs/report_packs/valid-for-now")
    result = _run_cli("--spec", str(spec_path), "--out", "/etc/evil")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_unsupported_input_mode_fails(tmp_path):
    from workflows.report_pipeline import ReportPipelineSpecV1

    spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_bids_raw_recipe", dataset_id="x", modality="EEG",
        output_root="outputs/report_packs/cli-test-unsupported",
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / "unsupported_spec.json"
    spec.write_json(spec_path)
    result = _run_cli("--spec", str(spec_path))
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_input_fails_clearly(tmp_path):
    from workflows.report_pipeline import ReportPipelineSpecV1

    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="x", modality="EEG",
        output_root="outputs/report_packs/cli-test-missing-input",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json",
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / "missing_input_spec.json"
    spec.write_json(spec_path)
    result = _run_cli("--spec", str(spec_path))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["errors"]


def test_cli_prints_concise_summary(tmp_path):
    spec_path = _write_builtin_spec(tmp_path, "summary")
    result = _run_cli("--spec", str(spec_path))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    for key in ("run_id", "pipeline_id", "input_mode", "dataset_id", "status", "steps_completed", "output_root"):
        assert key in payload


def test_cli_existing_evidence_bundle_end_to_end(tmp_path):
    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    from workflows.report_pipeline import ReportPipelineSpecV1

    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/cli-test-existing-bundle",
        evidence_bundle_path=str(bundle_path),
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / "existing_bundle_spec.json"
    spec.write_json(spec_path)
    result = _run_cli("--spec", str(spec_path), "--include-report")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["evidence_report_paths"]


def test_cli_never_downloads_raw_data():
    source = (_REPO_ROOT / "workflows" / "export_report_pack.py").read_text(encoding="utf-8")
    source += (_REPO_ROOT / "workflows" / "report_pipeline.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "boto3", "s3.download", "nilearn.datasets.fetch"):
        assert banned not in source
