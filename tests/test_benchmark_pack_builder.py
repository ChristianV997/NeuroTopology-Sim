"""End-to-end tests for `benchmark_packs.builder.build_benchmark_pack`.
Real already-committed contract artifacts only -- no downloads, no
seed-registry mutation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark_packs.builder import build_benchmark_pack, make_builtin_demo_pack_spec
from benchmark_packs.pack_spec import BenchmarkPackSpecV1
from job_runner.store import JobStore
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _good_pipeline_spec_dict(name: str) -> dict:
    return ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/benchmark_packs/builder-test-{name}/reports/good",
        source_paths=[str(_DS005620_SOURCE)], registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["builder test"], provenance="builder test",
    ).to_dict()


def _failing_pipeline_spec_dict(name: str) -> dict:
    return ReportPipelineSpecV1.make(
        input_mode="existing_evidence_bundle", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/benchmark_packs/builder-test-{name}/reports/bad",
        evidence_bundle_path="does/not/exist/EvidenceBundle.json", include_report=True,
        limitations=["builder test"], provenance="builder test",
    ).to_dict()


def test_build_without_run_creates_jobs_and_planned_summary():
    spec = BenchmarkPackSpecV1.make(
        pack_name="no-run test", output_root="outputs/benchmark_packs/builder-test-norun",
        pipeline_specs=[_good_pipeline_spec_dict("norun")], run_immediately=False,
        limitations=["builder test"], provenance="builder test",
    )
    pack = build_benchmark_pack(spec)

    assert pack.execution_summary["total_jobs"] == 1
    assert pack.execution_summary["status"] == "not_run"
    assert pack.report_pack_ids == []
    assert len(pack.job_ids) == 1

    store = JobStore(spec.jobs_root)
    assert store.load_job(pack.job_ids[0]).job_status == "created"


def test_build_with_run_immediately_executes_through_batch_worker_path():
    spec = BenchmarkPackSpecV1.make(
        pack_name="happy path", output_root="outputs/benchmark_packs/builder-test-happy",
        pipeline_specs=[_good_pipeline_spec_dict("happy")], run_immediately=True,
        limitations=["builder test"], provenance="builder test",
    )
    pack = build_benchmark_pack(spec)

    assert pack.execution_summary["status"] == "completed"
    assert pack.execution_summary["completed"] == 1
    assert pack.report_pack_ids == ["0030c8dcc44866c8"]
    assert pack.generated_report_pack_paths
    assert (_REPO_ROOT / pack.generated_report_pack_paths[0]).exists()


def test_build_with_include_html_produces_html_pack_ids():
    spec = BenchmarkPackSpecV1.make(
        pack_name="html test", output_root="outputs/benchmark_packs/builder-test-html",
        pipeline_specs=[_good_pipeline_spec_dict("html")], requested_outputs=["report_pack", "html_report_pack"],
        include_html=True, run_immediately=True,
        limitations=["builder test"], provenance="builder test",
    )
    pack = build_benchmark_pack(spec)

    assert pack.html_pack_ids
    assert pack.generated_index_path is not None
    assert (_REPO_ROOT / pack.generated_index_path).exists()


def test_build_partial_failure_recorded_without_fake_outputs():
    spec = BenchmarkPackSpecV1.make(
        pack_name="partial fail", output_root="outputs/benchmark_packs/builder-test-partial",
        pipeline_specs=[_failing_pipeline_spec_dict("partial"), _good_pipeline_spec_dict("partial")],
        run_immediately=True, limitations=["builder test"], provenance="builder test",
    )
    pack = build_benchmark_pack(spec)

    assert pack.execution_summary["status"] == "completed_with_failures"
    assert pack.execution_summary["completed"] == 1
    assert pack.execution_summary["failed"] == 1
    assert len(pack.report_pack_ids) == 1
    assert len(pack.generated_report_pack_paths) == 1


def test_build_does_not_mutate_input_spec_object():
    spec = BenchmarkPackSpecV1.make(
        pack_name="no mutate", output_root="outputs/benchmark_packs/builder-test-no-mutate",
        pipeline_specs=[_good_pipeline_spec_dict("no-mutate")], run_immediately=True,
        limitations=["builder test"], provenance="builder test",
    )
    before = spec.to_dict()
    build_benchmark_pack(spec)
    after = spec.to_dict()
    assert before == after


def test_build_writes_benchmark_pack_json():
    spec = BenchmarkPackSpecV1.make(
        pack_name="write test", output_root="outputs/benchmark_packs/builder-test-write",
        pipeline_specs=[_good_pipeline_spec_dict("write")], run_immediately=True,
        limitations=["builder test"], provenance="builder test",
    )
    build_benchmark_pack(spec)
    assert (_REPO_ROOT / "outputs/benchmark_packs/builder-test-write/BenchmarkPack.json").exists()


def test_builtin_demo_pack_end_to_end():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/builder-test-e2e", run_immediately=True)
    pack = build_benchmark_pack(spec)

    assert pack.execution_summary["status"] == "completed"
    assert pack.execution_summary["total_jobs"] == 4
    assert len(pack.report_pack_ids) == 4
    assert set(pack.dataset_ids) == {"ds005620", "ds000245"}
    assert set(pack.modalities) == {"EEG", "fMRI"}


def test_benchmark_pack_builder_never_touches_seed_registries():
    """Source-guard: benchmark_packs must orchestrate, never mutate a
    registry itself -- every registry write stays inside
    workflows.report_pipeline/adapters, called unmodified."""
    for module_name in ("builder.py", "pack_spec.py", "pack_manifest.py", "renderer.py"):
        src = (_REPO_ROOT / "benchmark_packs" / module_name).read_text(encoding="utf-8")
        assert "registry.save(" not in src
        assert "SeedRegistry(" not in src
