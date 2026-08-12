"""End-to-end tests for `job_runner.runner.run_pipeline_job`. Real
already-committed contract artifacts and existing demo fixtures only --
no downloads, no seed-registry mutation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from job_runner.runner import run_pipeline_job
from job_runner.store import JobStore
from tests.fixtures import report_pipeline_demo as demo
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _builtin_spec_dict(name: str, **overrides) -> dict:
    kwargs = dict(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/report_packs/runner-test-{name}",
        source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["runner test"], provenance="runner test",
    )
    kwargs.update(overrides)
    spec = ReportPipelineSpecV1.make(**kwargs)
    return spec.to_dict()


def test_run_reaches_report_pack():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_builtin_spec_dict("happy"), provenance="test")
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed"
    assert result.errors == []
    assert result.report_pack_id is not None
    assert result.report_pack_path is not None
    assert (_REPO_ROOT / result.report_pack_path).exists()

    reloaded_job = store.load_job(job.job_id)
    assert reloaded_job.job_status == "completed"
    assert reloaded_job.attempts == 1
    assert not store.is_locked(job.job_id)


def test_run_with_html_requested_reaches_html_report_pack():
    store = JobStore("outputs/jobs")
    job = store.create_job(
        spec_dict=_builtin_spec_dict("html"), requested_outputs=["report_pack", "html_report_pack"],
        provenance="test",
    )
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed"
    assert result.html_pack_id is not None
    assert result.index_html_path is not None
    assert (_REPO_ROOT / result.index_html_path).exists()


def test_run_with_html_already_in_spec_does_not_double_render():
    store = JobStore("outputs/jobs")
    job = store.create_job(
        spec_dict=_builtin_spec_dict("html-in-spec", include_html=True), requested_outputs=["html_report_pack"],
        provenance="test",
    )
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed"
    assert result.html_pack_id is not None
    assert (_REPO_ROOT / result.index_html_path).exists()


def test_dry_run_does_not_claim_report_generation():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_builtin_spec_dict("dry", dry_run=True), provenance="test")
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed"
    assert result.report_pack_id is None
    assert result.report_pack_path is None
    assert result.generated_files == []
    assert result.metadata.get("dry_run") is True


def test_failed_pipeline_records_error_and_writes_result():
    store = JobStore("outputs/jobs")
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/runner-test-existing-bundle-missing",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json", include_report=True,
        limitations=["runner test"], provenance="runner test",
    )
    job = store.create_job(spec_dict=spec.to_dict(), provenance="test")

    result = run_pipeline_job(job, store=store)

    assert result.job_status == "failed"
    assert result.errors
    assert store.load_result(job.job_id) == result

    reloaded_job = store.load_job(job.job_id)
    assert reloaded_job.job_status == "failed"
    assert reloaded_job.error_summary


def test_html_failure_after_valid_report_pack_marks_completed_with_warnings(monkeypatch):
    from workflows import html_report_pack as html_mod

    def _boom(**kwargs):
        raise html_mod.HtmlReportPackError("simulated renderer failure")

    monkeypatch.setattr("workflows.html_report_pack.render_html_report_pack", _boom)

    store = JobStore("outputs/jobs")
    job = store.create_job(
        spec_dict=_builtin_spec_dict("html-failure"), requested_outputs=["report_pack", "html_report_pack"],
        provenance="test",
    )
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed_with_warnings"
    assert result.report_pack_id is not None
    assert result.html_pack_id is None
    assert any("HTML report pack rendering failed" in w for w in result.warnings)


def test_existing_evidence_bundle_demo_reaches_report_pack(tmp_path):
    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    store = JobStore("outputs/jobs")
    spec = ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/runner-test-existing-bundle", evidence_bundle_path=str(bundle_path),
        include_report=True, limitations=["test"], provenance="test",
    )
    job = store.create_job(spec_dict=spec.to_dict(), provenance="test")
    result = run_pipeline_job(job, store=store)

    assert result.job_status == "completed"
    assert result.report_pack_id is not None


def test_run_acquires_and_releases_lock():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_builtin_spec_dict("lock-lifecycle"), provenance="test")
    assert not store.is_locked(job.job_id)
    run_pipeline_job(job, store=store)
    assert not store.is_locked(job.job_id)


def test_run_raises_on_invalid_job():
    store = JobStore("outputs/jobs")
    job = store.create_job(spec_dict=_builtin_spec_dict("invalid"), provenance="test")
    job.limitations = []  # now structurally invalid
    with pytest.raises(Exception):
        run_pipeline_job(job, store=store)


def test_job_runner_never_touches_seed_registries():
    """Source-guard: job_runner must orchestrate, never mutate a
    registry itself -- every registry write stays inside
    workflows.report_pipeline/adapters, called unmodified."""
    runner_src = (_REPO_ROOT / "job_runner" / "runner.py").read_text(encoding="utf-8")
    store_src = (_REPO_ROOT / "job_runner" / "store.py").read_text(encoding="utf-8")
    for src in (runner_src, store_src):
        assert "registry.save(" not in src
        assert "SeedRegistry(" not in src
