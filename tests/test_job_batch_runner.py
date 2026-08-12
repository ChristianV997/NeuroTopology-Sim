"""End-to-end tests for `job_runner.batch.create_batch_from_specs`/
`run_batch`. Real already-committed contract artifacts only -- no
downloads, no seed-registry mutation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from job_runner.batch import batch_manifest_path, create_batch_from_specs, run_batch
from job_runner.store import JobStore
from job_runner.validation import JobStoreError
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _write_demo_spec(tmp_path: Path, name: str) -> Path:
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/batch-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["batch test"], provenance="batch test",
    )
    path = tmp_path / f"{name}_spec.json"
    spec.write_json(path)
    return path


def _write_failing_spec(tmp_path: Path, name: str) -> Path:
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/batch-test-{name}",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json", include_report=True,
        limitations=["batch test"], provenance="batch test",
    )
    path = tmp_path / f"{name}_spec.json"
    spec.write_json(path)
    return path


def test_create_batch_from_specs_creates_jobs_without_running(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    spec_b = _write_demo_spec(tmp_path, "b")

    manifest = create_batch_from_specs([str(spec_a), str(spec_b)], "outputs/jobs", batch_name="demo")

    assert manifest.batch_status == "created"
    assert len(manifest.job_ids) == 2
    store = JobStore("outputs/jobs")
    for job_id in manifest.job_ids:
        job = store.load_job(job_id)
        assert job.job_status == "created"
        assert job.attempts == 0


def test_create_batch_writes_manifest_file(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    manifest = create_batch_from_specs([str(spec_a)], "outputs/jobs", batch_name="demo")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)
    assert path.exists()


def test_create_batch_does_not_mutate_input_specs(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    before = spec_a.read_text(encoding="utf-8")
    create_batch_from_specs([str(spec_a)], "outputs/jobs", batch_name="demo")
    after = spec_a.read_text(encoding="utf-8")
    assert before == after


def test_create_batch_fails_closed_on_missing_spec(tmp_path):
    with pytest.raises(JobStoreError):
        create_batch_from_specs([str(tmp_path / "does_not_exist.json")], "outputs/jobs")


def test_run_batch_executes_only_batch_jobs(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    spec_b = _write_demo_spec(tmp_path, "b")
    manifest = create_batch_from_specs([str(spec_a), str(spec_b)], "outputs/jobs", batch_name="demo")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)

    result = run_batch(path)

    assert result.batch_status == "completed"
    assert result.completed_count == 2
    assert result.failed_count == 0
    assert len(result.job_result_paths) == 2


def test_run_batch_mixed_success_failure_gives_completed_with_failures(tmp_path):
    spec_good = _write_demo_spec(tmp_path, "good")
    spec_bad = _write_failing_spec(tmp_path, "bad")
    manifest = create_batch_from_specs([str(spec_good), str(spec_bad)], "outputs/jobs", batch_name="mixed")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)

    result = run_batch(path)

    assert result.batch_status == "completed_with_failures"
    assert result.completed_count == 1
    assert result.failed_count == 1


def test_run_batch_dry_run_executes_none(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    manifest = create_batch_from_specs([str(spec_a)], "outputs/jobs", batch_name="demo")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)

    result = run_batch(path, dry_run=True)

    assert result.completed_count == 0
    assert result.job_result_paths == []
    store = JobStore("outputs/jobs")
    for job_id in manifest.job_ids:
        assert store.load_job(job_id).job_status == "created"


def test_run_batch_all_failed_gives_failed_status(tmp_path):
    spec_bad = _write_failing_spec(tmp_path, "bad")
    manifest = create_batch_from_specs([str(spec_bad)], "outputs/jobs", batch_name="all_fail")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)

    result = run_batch(path)

    assert result.batch_status == "failed"
    assert result.failed_count == 1


def test_run_batch_respects_max_jobs(tmp_path):
    spec_a = _write_demo_spec(tmp_path, "a")
    spec_b = _write_demo_spec(tmp_path, "b")
    manifest = create_batch_from_specs([str(spec_a), str(spec_b)], "outputs/jobs", batch_name="capped")
    path = batch_manifest_path("outputs/jobs", manifest.batch_id)

    result = run_batch(path, max_jobs=1)

    assert result.completed_count == 1
    store = JobStore("outputs/jobs")
    statuses = [store.load_job(jid).job_status for jid in manifest.job_ids]
    assert statuses.count("completed") == 1
    assert statuses.count("created") == 1
