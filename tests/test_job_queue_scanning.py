"""Tests for `job_runner.queue.scan_job_queue`/`select_next_jobs`. Real
already-committed contract artifacts only -- no downloads, no
execution (scanning never runs a job)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from job_runner.queue import scan_job_queue, select_next_jobs
from job_runner.store import JOB_FILENAME, JobStore
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
        output_root=f"outputs/report_packs/scan-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["scan test"], provenance="scan test",
    )
    return spec.to_dict()


def test_scan_empty_queue():
    state = scan_job_queue("outputs/jobs")
    assert state.total_jobs == 0
    assert state.queued_job_ids == []


def test_scan_finds_created_and_queued_jobs():
    store = JobStore("outputs/jobs")
    job_a = store.create_job(spec_dict=_demo_spec_dict("a"), provenance="test")
    job_b = store.create_job(spec_dict=_demo_spec_dict("b"), provenance="test")

    state = scan_job_queue("outputs/jobs")
    assert set(state.queued_job_ids) == {job_a.job_id, job_b.job_id}
    assert state.total_jobs == 2


def test_scan_excludes_running_completed_failed_cancelled_blocked():
    store = JobStore("outputs/jobs")
    running = store.create_job(spec_dict=_demo_spec_dict("running"), provenance="test")
    store.update_job_status(running.job_id, "running", started_at="2026-01-01T00:00:00+00:00")
    completed = store.create_job(spec_dict=_demo_spec_dict("completed"), provenance="test")
    store.update_job_status(completed.job_id, "completed", completed_at="2026-01-01T00:00:00+00:00")
    failed = store.create_job(spec_dict=_demo_spec_dict("failed"), provenance="test")
    store.update_job_status(failed.job_id, "failed", error_summary="boom")
    cancelled = store.create_job(spec_dict=_demo_spec_dict("cancelled"), provenance="test")
    store.update_job_status(cancelled.job_id, "cancelled")
    blocked = store.create_job(spec_dict=_demo_spec_dict("blocked"), provenance="test")
    store.update_job_status(blocked.job_id, "blocked")
    pending = store.create_job(spec_dict=_demo_spec_dict("pending"), provenance="test")

    state = scan_job_queue("outputs/jobs")
    assert state.queued_job_ids == [pending.job_id]
    assert state.running_job_ids == [running.job_id]
    assert state.completed_job_ids == [completed.job_id]
    assert state.failed_job_ids == [failed.job_id]
    assert state.cancelled_job_ids == [cancelled.job_id]
    assert state.blocked_job_ids == [blocked.job_id]
    assert state.total_jobs == 6


def test_scan_status_filter():
    store = JobStore("outputs/jobs")
    job_a = store.create_job(spec_dict=_demo_spec_dict("a"), provenance="test")
    job_b = store.create_job(spec_dict=_demo_spec_dict("b"), provenance="test")
    store.update_job_status(job_b.job_id, "failed", error_summary="boom")

    state = scan_job_queue("outputs/jobs", status_filter="created")
    assert state.queued_job_ids == [job_a.job_id]
    assert state.failed_job_ids == []


def test_scan_invalid_job_file_does_not_crash_and_is_recorded_as_warning():
    store = JobStore("outputs/jobs")
    good = store.create_job(spec_dict=_demo_spec_dict("good"), provenance="test")

    corrupt_dir = _REPO_ROOT / "outputs" / "jobs" / "corrupt-job-id"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / JOB_FILENAME).write_text("{not valid json", encoding="utf-8")

    state = scan_job_queue("outputs/jobs")
    assert state.queued_job_ids == [good.job_id]
    assert state.total_jobs == 1
    assert state.metadata.get("scan_warnings")
    assert any("corrupt-job-id" in w for w in state.metadata["scan_warnings"])


def test_select_next_jobs_finds_created_and_queued():
    store = JobStore("outputs/jobs")
    job_a = store.create_job(spec_dict=_demo_spec_dict("a"), provenance="test")
    selected = select_next_jobs("outputs/jobs", max_jobs=5)
    assert [j.job_id for j in selected] == [job_a.job_id]


def test_select_next_jobs_excludes_terminal_and_running_statuses():
    store = JobStore("outputs/jobs")
    pending = store.create_job(spec_dict=_demo_spec_dict("pending"), provenance="test")
    running = store.create_job(spec_dict=_demo_spec_dict("running"), provenance="test")
    store.update_job_status(running.job_id, "running", started_at="2026-01-01T00:00:00+00:00")
    blocked = store.create_job(spec_dict=_demo_spec_dict("blocked"), provenance="test")
    store.update_job_status(blocked.job_id, "blocked")
    cancelled = store.create_job(spec_dict=_demo_spec_dict("cancelled"), provenance="test")
    store.update_job_status(cancelled.job_id, "cancelled")

    selected = select_next_jobs("outputs/jobs", max_jobs=10)
    assert [j.job_id for j in selected] == [pending.job_id]


def test_select_next_jobs_deterministic_ordering_by_priority_then_created_at_then_id():
    store = JobStore("outputs/jobs")
    low_priority = store.create_job(spec_dict=_demo_spec_dict("low"), provenance="test", priority=0)
    high_priority = store.create_job(spec_dict=_demo_spec_dict("high"), provenance="test", priority=5)

    selected = select_next_jobs("outputs/jobs", max_jobs=10)
    assert [j.job_id for j in selected] == [high_priority.job_id, low_priority.job_id]


def test_select_next_jobs_respects_max_jobs():
    store = JobStore("outputs/jobs")
    for name in ("a", "b", "c"):
        store.create_job(spec_dict=_demo_spec_dict(name), provenance="test")
    selected = select_next_jobs("outputs/jobs", max_jobs=2)
    assert len(selected) == 2


def test_select_next_jobs_empty_queue():
    assert select_next_jobs("outputs/jobs", max_jobs=5) == []
