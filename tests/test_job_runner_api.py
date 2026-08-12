"""Tests for `job_runner.api`. `fastapi` is declared (unpinned) in root
`requirements.txt`, so whether it is actually importable is an environment
fact, not a repository constant: this repository's local sandbox does not
have it installed, but a CI job that runs `pip install -r requirements.txt`
does. These tests must be portable across both -- see PR #203's Required
Checks failure (`test_api_unavailable_in_this_environment_is_reported_honestly`
hardcoded `API_AVAILABLE is False`, which is only true where `fastapi`
happens to be absent) and `docs/ci_failure_audit.md` for the incident this
fixed.

The unavailable branch is exercised deterministically via monkeypatching
regardless of what is actually installed; the available branch runs only
when `fastapi` is actually importable (skipped honestly otherwise). Every
other test calls the plain functions directly -- the same functions the
FastAPI routes call when the dependency is present -- so coverage of the
actual job-running behavior does not depend on `fastapi` either way."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

import job_runner.api as api
from job_runner.store import JobStore
from workflows.report_pipeline import ReportPipelineSpecV1

_FASTAPI_ACTUALLY_INSTALLED = importlib.util.find_spec("fastapi") is not None

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


def test_api_available_reflects_actual_fastapi_import_state():
    # API_AVAILABLE is an environment fact, not a repository constant --
    # this compares it against an independent probe (importlib.util.find_spec)
    # rather than hardcoding a value, so the assertion is true in every
    # environment (fastapi absent, as in this sandbox, or present, as in CI).
    assert api.API_AVAILABLE is _FASTAPI_ACTUALLY_INSTALLED


def test_get_app_returns_none_when_fastapi_unavailable(monkeypatch):
    # Deterministic regardless of what is actually installed: simulates the
    # unavailable branch by monkeypatching the module's own flag/class, the
    # same pair `get_app()` reads at call time.
    monkeypatch.setattr(api, "API_AVAILABLE", False)
    monkeypatch.setattr(api, "FastAPI", None)
    assert api.get_app() is None


def test_module_level_app_is_none_when_fastapi_unavailable():
    if api.API_AVAILABLE:
        pytest.skip("fastapi is installed in this environment; api.app is expected non-None here")
    assert api.app is None
    assert api.get_app() is None


@pytest.mark.skipif(not _FASTAPI_ACTUALLY_INSTALLED, reason="fastapi is not installed in this environment")
def test_get_app_returns_fastapi_app_when_available():
    app = api.get_app()
    assert app is not None
    assert api.app is not None
    # The available branch must not imply production-readiness -- the app's
    # own title states local-dev-only/no-auth, matching job_runner.api's and
    # docs/job_runner.md's documented scope.
    assert "local dev only" in app.title.lower()
    assert "no auth" in app.title.lower()


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
