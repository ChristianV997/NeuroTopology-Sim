"""Subprocess CLI tests for `python -m job_runner.export_job`. Real
already-committed contract artifacts only -- no network access."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from job_runner.store import JobStore
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "job_runner.export_job", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _write_spec(tmp_path: Path, name: str) -> Path:
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/cli-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["cli test"], provenance="cli test fixture",
    )
    spec_path = tmp_path / f"{name}_spec.json"
    spec.write_json(spec_path)
    return spec_path


def test_create_does_not_execute(tmp_path):
    spec_path = _write_spec(tmp_path, "create")
    result = _run_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_status"] == "created"
    assert payload["attempts"] == 0
    job_id = payload["job_id"]
    assert not (_REPO_ROOT / f"outputs/report_packs/cli-test-create/ReportPack.json").exists()

    store = JobStore("outputs/jobs")
    assert store.load_job(job_id).job_status == "created"


def test_run_executes_a_created_job(tmp_path):
    spec_path = _write_spec(tmp_path, "run")
    created = json.loads(_run_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs").stdout)
    job_id = created["job_id"]

    result = _run_cli("run", "--job", f"outputs/jobs/{job_id}/PipelineJob.json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_status"] == "completed"
    assert payload["report_pack_id"] is not None


def test_run_spec_creates_and_runs_in_one_step(tmp_path):
    spec_path = _write_spec(tmp_path, "runspec")
    result = _run_cli("run-spec", "--spec", str(spec_path), "--out", "outputs/jobs")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_status"] == "completed"
    assert payload["report_pack_id"] is not None


def test_status_reports_job_and_result(tmp_path):
    spec_path = _write_spec(tmp_path, "status")
    created = json.loads(_run_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs").stdout)
    job_id = created["job_id"]
    _run_cli("run", "--job", f"outputs/jobs/{job_id}/PipelineJob.json")

    result = _run_cli("status", "--job", job_id)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["job_status"] == "completed"
    assert payload["result"]["report_pack_id"] is not None


def test_list_shows_jobs_by_status(tmp_path):
    spec_path = _write_spec(tmp_path, "list")
    created = json.loads(_run_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs").stdout)
    job_id = created["job_id"]

    listed = json.loads(_run_cli("list", "--jobs-root", "outputs/jobs").stdout)
    assert any(j["job_id"] == job_id for j in listed)

    listed_created = json.loads(_run_cli("list", "--jobs-root", "outputs/jobs", "--status", "created").stdout)
    assert any(j["job_id"] == job_id for j in listed_created)
    listed_completed = json.loads(_run_cli("list", "--jobs-root", "outputs/jobs", "--status", "completed").stdout)
    assert not any(j["job_id"] == job_id for j in listed_completed)


def test_invalid_spec_fails_clearly(tmp_path):
    bad_spec = tmp_path / "bad_spec.json"
    bad_spec.write_text(json.dumps({"bad": "spec"}), encoding="utf-8")
    result = _run_cli("create", "--spec", str(bad_spec), "--out", "outputs/jobs")
    assert result.returncode != 0
    assert "FAILED" in result.stdout


def test_missing_job_fails_clearly():
    result = _run_cli("status", "--job", "does_not_exist_job_id")
    assert result.returncode != 0
    assert "FAILED" in result.stdout


def test_lock_conflict_fails_clearly(tmp_path):
    spec_path = _write_spec(tmp_path, "lock")
    created = json.loads(_run_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs").stdout)
    job_id = created["job_id"]

    store = JobStore("outputs/jobs")
    store.acquire_job_lock(job_id)
    try:
        result = _run_cli("run", "--job", f"outputs/jobs/{job_id}/PipelineJob.json")
        assert result.returncode != 0
        assert "locked" in result.stdout
    finally:
        store.release_job_lock(job_id)


def test_unsupported_requested_output_rejected_by_argparse(tmp_path):
    spec_path = _write_spec(tmp_path, "unsupported")
    result = _run_cli(
        "create", "--spec", str(spec_path), "--out", "outputs/jobs", "--requested-output", "pdf_export",
    )
    assert result.returncode != 0
