"""Subprocess CLI tests for `python -m job_runner.export_worker`. Real
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
        [sys.executable, "-m", "job_runner.export_worker", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _run_job_cli(*args: str) -> subprocess.CompletedProcess:
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
        output_root=f"outputs/report_packs/worker-cli-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["worker cli test"], provenance="worker cli test fixture",
    )
    spec_path = tmp_path / f"{name}_spec.json"
    spec.write_json(spec_path)
    return spec_path


def test_scan_works(tmp_path):
    spec_path = _write_spec(tmp_path, "scan")
    _run_job_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs")

    result = _run_cli("scan", "--jobs-root", "outputs/jobs")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["total_jobs"] == 1
    assert payload["queued"] == 1


def test_run_once_works(tmp_path):
    spec_path = _write_spec(tmp_path, "run-once")
    _run_job_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs")

    result = _run_cli("run-once", "--jobs-root", "outputs/jobs", "--max-jobs", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["jobs_completed"]) == 1


def test_loop_bounded_works(tmp_path):
    spec_a = _write_spec(tmp_path, "loop-a")
    spec_b = _write_spec(tmp_path, "loop-b")
    _run_job_cli("create", "--spec", str(spec_a), "--out", "outputs/jobs")
    _run_job_cli("create", "--spec", str(spec_b), "--out", "outputs/jobs")

    result = _run_cli(
        "loop", "--jobs-root", "outputs/jobs", "--max-loops", "3", "--max-jobs-per-loop", "1",
        "--poll-interval-seconds", "0",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["loops"] == 3
    assert payload["jobs_completed"] == 2


def test_create_batch_works(tmp_path):
    spec_a = _write_spec(tmp_path, "batch-a")
    spec_b = _write_spec(tmp_path, "batch-b")

    result = _run_cli(
        "create-batch", "--spec", str(spec_a), "--spec", str(spec_b), "--jobs-root", "outputs/jobs",
        "--batch-name", "cli_test_batch",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["batch_status"] == "created"
    assert len(payload["job_ids"]) == 2


def test_run_batch_works(tmp_path):
    spec_a = _write_spec(tmp_path, "run-batch-a")
    created = json.loads(
        _run_cli("create-batch", "--spec", str(spec_a), "--jobs-root", "outputs/jobs", "--batch-name", "x").stdout
    )
    batch_id = created["batch_id"]

    result = _run_cli("run-batch", "--batch", f"outputs/jobs/batches/{batch_id}/BatchRunManifest.json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["batch_status"] == "completed"
    assert payload["completed_count"] == 1


def test_invalid_jobs_root_fails_clearly():
    result = _run_cli("scan", "--jobs-root", "/tmp/not-allowed")
    assert result.returncode != 0
    assert "FAILED" in result.stdout


def test_dry_run_works(tmp_path):
    spec_path = _write_spec(tmp_path, "dry")
    _run_job_cli("create", "--spec", str(spec_path), "--out", "outputs/jobs")

    result = _run_cli("run-once", "--jobs-root", "outputs/jobs", "--max-jobs", "1", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["jobs_completed"] == []
    assert len(payload["jobs_selected"]) == 1


def test_loop_requires_max_loops():
    result = _run_cli("loop", "--jobs-root", "outputs/jobs")
    assert result.returncode != 0
