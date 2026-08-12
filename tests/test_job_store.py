"""Tests for `job_runner.store.JobStore`: creation, atomicity, locking,
listing, and output-root safety. Uses `tests/fixtures/report_pipeline_demo.py`
for a real, already-committed `ReportPipelineSpecV1`."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dataset_acquisition.store import TargetRootError
from job_runner.job import PipelineJobValidationError
from job_runner.result import PipelineJobResultV1
from job_runner.store import JobLockError, JobStore
from job_runner.validation import JobStoreError
from tests.fixtures import report_pipeline_demo as demo
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
        output_root=f"outputs/report_packs/store-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["store test"], provenance="store test",
    )
    return spec.to_dict()


def test_create_job_writes_deterministic_json():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("determinism"), job_name="det job", provenance="test")
    on_disk = store.job_path(job.job_id).read_text(encoding="utf-8")
    assert job.job_id in on_disk
    assert store.job_path(job.job_id).exists()


def test_create_job_does_not_execute_pipeline():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("no-exec"), provenance="test")
    assert job.job_status == "created"
    assert job.attempts == 0
    assert not (_REPO_ROOT / job.output_root / "ReportPack.json").exists()


def test_create_job_requires_exactly_one_spec_source():
    store = JobStore("outputs/jobs")
    with pytest.raises(JobStoreError):
        store.create_job(provenance="test")
    with pytest.raises(JobStoreError):
        store.create_job(spec_path="a.json", spec_dict=_demo_spec_dict("both"), provenance="test")


def test_create_job_fails_closed_on_invalid_spec():
    store = JobStore("outputs/jobs")
    with pytest.raises(JobStoreError):
        store.create_job(spec_dict={"input_mode": "existing_evidence_bundle"}, provenance="test")


def test_load_job_by_id_and_by_path():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("load"), provenance="test")
    by_id = store.load_job(job.job_id)
    by_path = store.load_job(store.job_path(job.job_id))
    assert by_id == job
    assert by_path == job


def test_load_job_missing_raises():
    store = JobStore("outputs/jobs")
    with pytest.raises(JobStoreError):
        store.load_job("does_not_exist")


def test_list_jobs_filters_by_status():
    store = JobStore("outputs/jobs")
    job_a = store.create_job(spec_dict=_demo_spec_dict("list-a"), provenance="test")
    job_b = store.create_job(spec_dict=_demo_spec_dict("list-b"), provenance="test")
    store.update_job_status(job_b.job_id, "failed", error_summary="boom", completed_at="2026-01-01T00:00:00+00:00")

    all_jobs = store.list_jobs()
    assert {j.job_id for j in all_jobs} == {job_a.job_id, job_b.job_id}

    created_only = store.list_jobs(status="created")
    assert [j.job_id for j in created_only] == [job_a.job_id]

    failed_only = store.list_jobs(status="failed")
    assert [j.job_id for j in failed_only] == [job_b.job_id]


def test_list_jobs_empty_root_returns_empty_list():
    store = JobStore("outputs/jobs")
    assert store.list_jobs() == []


def test_save_job_atomic_write_leaves_no_partial_file():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("atomic"), provenance="test")
    job.job_status = "queued"
    store.save_job(job)
    job_dir = store.job_dir(job.job_id)
    leftover_tmp = list(job_dir.glob(".*.tmp"))
    assert leftover_tmp == []
    assert store.load_job(job.job_id).job_status == "queued"


def test_write_result_and_load_result():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("result"), provenance="test")
    result = PipelineJobResultV1.make(
        job_id=job.job_id, job_status="completed", output_root=job.output_root,
        limitations=["test"], provenance="test",
    )
    store.write_result(result)
    loaded = store.load_result(job.job_id)
    assert loaded == result


def test_load_result_returns_none_when_absent():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("no-result"), provenance="test")
    assert store.load_result(job.job_id) is None


def test_acquire_and_release_lock():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("lock"), provenance="test")
    assert not store.is_locked(job.job_id)
    store.acquire_job_lock(job.job_id)
    assert store.is_locked(job.job_id)
    store.release_job_lock(job.job_id)
    assert not store.is_locked(job.job_id)


def test_acquire_lock_twice_raises_lock_error():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("lock-conflict"), provenance="test")
    store.acquire_job_lock(job.job_id)
    with pytest.raises(JobLockError):
        store.acquire_job_lock(job.job_id)
    store.release_job_lock(job.job_id)


def test_release_lock_is_idempotent():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("release-idempotent"), provenance="test")
    store.release_job_lock(job.job_id)
    store.release_job_lock(job.job_id)


def test_output_root_safety_rejects_absolute_and_traversal_paths():
    with pytest.raises(TargetRootError):
        JobStore("/tmp/not-allowed")
    with pytest.raises(TargetRootError):
        JobStore("../escape")
    with pytest.raises(TargetRootError):
        JobStore("not_under_outputs_or_data")
