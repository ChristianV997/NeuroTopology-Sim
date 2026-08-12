"""Tests for `job_runner.api`. This repository's environments do not
currently have `fastapi` installed (confirmed: `pip show fastapi` finds
nothing in both the root and `.venv/` environments), so
`job_runner.api.API_AVAILABLE` is expected to be `False` here and
`job_runner.api.app` is expected to be `None` -- these tests assert that
graceful-degradation behavior explicitly, per the module's own contract,
and otherwise call the plain functions directly (the same functions the
FastAPI routes would call if the dependency were present)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import job_runner.api as api
from job_runner.store import JobStore
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _demo_spec_dict(name: str) -> dict:
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/api-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["api test"], provenance="api test",
    )
    return spec.to_dict()


def test_api_unavailable_in_this_environment_is_reported_honestly():
    # This is the environment-truth assertion the mission's Phase F
    # fallback explicitly asks for: fail gracefully, don't pretend.
    assert api.API_AVAILABLE is False
    assert api.app is None
    assert api.get_app() is None


def test_health_works_regardless_of_fastapi_availability():
    result = api.health()
    assert result["ok"] is True
    assert result["fastapi_available"] is api.API_AVAILABLE


def test_create_job_via_plain_function():
    payload = {"spec_dict": _demo_spec_dict("create"), "job_name": "api test job"}
    created = api.create_job(payload, jobs_root="outputs/jobs")
    assert created["job_status"] == "created"
    assert created["attempts"] == 0
    store = JobStore("outputs/jobs")
    assert store.load_job(created["job_id"]).job_status == "created"


def test_get_job_returns_job_and_result_when_present():
    payload = {"spec_dict": _demo_spec_dict("get")}
    created = api.create_job(payload, jobs_root="outputs/jobs")
    job_id = created["job_id"]

    before_run = api.get_job(job_id, jobs_root="outputs/jobs")
    assert "result" not in before_run

    api.run_job(job_id, jobs_root="outputs/jobs")
    after_run = api.get_job(job_id, jobs_root="outputs/jobs")
    assert after_run["job_status"] == "completed"
    assert after_run["result"]["report_pack_id"] is not None


def test_run_job_via_plain_function():
    payload = {"spec_dict": _demo_spec_dict("run")}
    created = api.create_job(payload, jobs_root="outputs/jobs")
    result = api.run_job(created["job_id"], jobs_root="outputs/jobs")
    assert result["job_status"] == "completed"
    assert result["report_pack_id"] is not None


def test_list_jobs_via_plain_function():
    payload = {"spec_dict": _demo_spec_dict("list")}
    created = api.create_job(payload, jobs_root="outputs/jobs")

    all_jobs = api.list_jobs(jobs_root="outputs/jobs")
    assert any(j["job_id"] == created["job_id"] for j in all_jobs)

    created_only = api.list_jobs(status="created", jobs_root="outputs/jobs")
    assert any(j["job_id"] == created["job_id"] for j in created_only)


def test_invalid_spec_returns_clear_error():
    from job_runner.validation import JobStoreError

    with pytest.raises(JobStoreError):
        api.create_job({"spec_dict": {"bad": "spec"}}, jobs_root="outputs/jobs")


def test_get_job_missing_raises_clear_error():
    from job_runner.validation import JobStoreError

    with pytest.raises(JobStoreError):
        api.get_job("does_not_exist", jobs_root="outputs/jobs")


def test_smoke_test_cli_entrypoint_exits_zero():
    assert api.main(["--smoke-test"]) == 0
