"""End-to-end tests for `job_runner.worker.run_worker_once`/
`run_worker_loop`. Real already-committed contract artifacts only -- no
downloads, no seed-registry mutation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from job_runner.store import JobStore
from job_runner.worker import run_worker_loop, run_worker_once
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
        output_root=f"outputs/report_packs/worker-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["worker test"], provenance="worker test",
    )
    return spec.to_dict()


def test_run_worker_once_executes_one_queued_demo_job():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("happy"), provenance="test")

    manifest = run_worker_once("outputs/jobs", max_jobs=1)

    assert manifest.jobs_selected == [job.job_id]
    assert manifest.jobs_completed == [job.job_id]
    assert manifest.jobs_failed == []
    assert manifest.result_paths
    reloaded = store.load_job(job.job_id)
    assert reloaded.job_status == "completed"


def test_max_jobs_respected():
    store = JobStore("outputs/jobs")
    for name in ("a", "b", "c"):
        store.create_job(spec_dict=_demo_spec_dict(name), provenance="test")

    manifest = run_worker_once("outputs/jobs", max_jobs=2)
    assert len(manifest.jobs_selected) == 2
    assert len(manifest.jobs_completed) == 2

    remaining = run_worker_once("outputs/jobs", max_jobs=5)
    assert len(remaining.jobs_selected) == 1


def test_dry_run_executes_none():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("dry"), provenance="test")

    manifest = run_worker_once("outputs/jobs", max_jobs=1, dry_run=True)

    assert manifest.jobs_selected == [job.job_id]
    assert manifest.jobs_completed == []
    assert manifest.result_paths == []
    reloaded = store.load_job(job.job_id)
    assert reloaded.job_status == "created"


def test_failed_job_records_error_and_continues():
    store = JobStore("outputs/jobs")
    bad_spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/worker-test-failed",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json", include_report=True,
        limitations=["worker test"], provenance="worker test",
    )
    failing_job = store.create_job(spec_dict=bad_spec.to_dict(), provenance="test")
    good_job = store.create_job(spec_dict=_demo_spec_dict("good"), provenance="test")

    manifest = run_worker_once("outputs/jobs", max_jobs=5)

    assert failing_job.job_id in manifest.jobs_failed
    assert good_job.job_id in manifest.jobs_completed
    assert len(manifest.jobs_selected) == 2


def test_lock_conflict_skips_and_records_conflict():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_demo_spec_dict("locked"), provenance="test")
    store.acquire_job_lock(job.job_id)
    try:
        manifest = run_worker_once("outputs/jobs", max_jobs=1)
        assert manifest.lock_conflicts == [job.job_id]
        assert manifest.jobs_completed == []
        assert manifest.jobs_failed == []
    finally:
        store.release_job_lock(job.job_id)


def test_worker_loop_is_bounded_and_drains_queue():
    store = JobStore("outputs/jobs")
    job_a = store.create_job(spec_dict=_demo_spec_dict("a"), provenance="test")
    job_b = store.create_job(spec_dict=_demo_spec_dict("b"), provenance="test")

    manifests = run_worker_loop("outputs/jobs", max_jobs_per_loop=1, max_loops=3, poll_interval_seconds=0)

    assert len(manifests) == 3
    all_completed = [jid for m in manifests for jid in m.jobs_completed]
    assert set(all_completed) == {job_a.job_id, job_b.job_id}
    assert manifests[2].jobs_selected == []


def test_worker_loop_requires_bounded_max_loops():
    with pytest.raises(ValueError):
        run_worker_loop("outputs/jobs", max_loops=0)
    with pytest.raises(ValueError):
        run_worker_loop("outputs/jobs", max_loops=100_000)


def test_no_outputs_generated_beyond_result_for_failed_job():
    store = JobStore("outputs/jobs")
    bad_spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/worker-test-failed-outputs",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json", include_report=True,
        limitations=["worker test"], provenance="worker test",
    )
    job = store.create_job(spec_dict=bad_spec.to_dict(), provenance="test")

    run_worker_once("outputs/jobs", max_jobs=1)

    assert not (_REPO_ROOT / "outputs" / "report_packs" / "worker-test-failed-outputs" / "ReportPack.json").exists()
    result = store.load_result(job.job_id)
    assert result is not None
    assert result.job_status == "failed"
    assert result.report_pack_id is None


def test_job_worker_never_touches_seed_registries():
    """Source-guard: job_runner.worker/job_runner.batch must orchestrate,
    never mutate a registry themselves -- every registry write stays
    inside workflows.report_pipeline/adapters, called unmodified."""
    for module_name in ("queue.py", "worker.py", "batch.py", "batch_manifest.py"):
        src = (_REPO_ROOT / "job_runner" / module_name).read_text(encoding="utf-8")
        assert "registry.save(" not in src
        assert "SeedRegistry(" not in src
