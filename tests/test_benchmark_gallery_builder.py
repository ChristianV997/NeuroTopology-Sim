"""End-to-end tests for `benchmark_packs.gallery.build_benchmark_gallery`.
Real already-committed contract artifacts only -- no downloads, no
seed-registry mutation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark_packs.builder import build_benchmark_pack, make_builtin_demo_pack_spec
from benchmark_packs.gallery import build_benchmark_gallery, discover_benchmark_pack_paths
from benchmark_packs.pack_spec import BenchmarkPackSpecV1
from benchmark_packs.validation import BenchmarkPackStoreError
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_gallery_test", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _good_spec_dict(name: str) -> dict:
    return ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/benchmark_packs/gallery-builder-test-{name}/reports/good",
        source_paths=[str(_DS005620_SOURCE)], registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    ).to_dict()


def test_builds_gallery_from_one_valid_pack():
    spec = BenchmarkPackSpecV1.make(
        pack_name="single", output_root="outputs/benchmark_packs/gallery-builder-test-single",
        pipeline_specs=[_good_spec_dict("single")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    pack = build_benchmark_pack(spec)

    gallery = build_benchmark_gallery(
        ["outputs/benchmark_packs/gallery-builder-test-single/BenchmarkPack.json"],
        "outputs/benchmark_gallery_test",
    )
    assert gallery.verified_pack_ids == [pack.benchmark_pack_id]
    assert gallery.failed_pack_ids == []
    assert gallery.generated_gallery_index_path is not None
    assert (_REPO_ROOT / gallery.generated_gallery_index_path).exists()


def test_builds_gallery_from_multiple_valid_packs():
    spec_a = BenchmarkPackSpecV1.make(
        pack_name="a", output_root="outputs/benchmark_packs/gallery-builder-test-multi-a",
        pipeline_specs=[_good_spec_dict("multi-a")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    spec_b = BenchmarkPackSpecV1.make(
        pack_name="b", output_root="outputs/benchmark_packs/gallery-builder-test-multi-b",
        pipeline_specs=[_good_spec_dict("multi-b")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    build_benchmark_pack(spec_a)
    build_benchmark_pack(spec_b)

    gallery = build_benchmark_gallery(
        [
            "outputs/benchmark_packs/gallery-builder-test-multi-a/BenchmarkPack.json",
            "outputs/benchmark_packs/gallery-builder-test-multi-b/BenchmarkPack.json",
        ],
        "outputs/benchmark_gallery_test",
    )
    assert len(gallery.verified_pack_ids) == 2
    assert gallery.dataset_ids == ["ds005620"]


def test_failed_pack_recorded_separately():
    spec = BenchmarkPackSpecV1.make(
        pack_name="bad", output_root="outputs/benchmark_packs/gallery-builder-test-bad",
        pipeline_specs=[_good_spec_dict("bad")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    pack = build_benchmark_pack(spec)
    Path(pack.generated_report_pack_paths[0]).unlink()

    gallery = build_benchmark_gallery(
        ["outputs/benchmark_packs/gallery-builder-test-bad/BenchmarkPack.json"], "outputs/benchmark_gallery_test",
    )
    assert gallery.verified_pack_ids == []
    assert gallery.failed_pack_ids == [pack.benchmark_pack_id]


def test_strict_mode_excludes_failed_packs_from_verified_list():
    spec_good = BenchmarkPackSpecV1.make(
        pack_name="good", output_root="outputs/benchmark_packs/gallery-builder-test-strict-good",
        pipeline_specs=[_good_spec_dict("strict-good")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    spec_bad = BenchmarkPackSpecV1.make(
        pack_name="bad", output_root="outputs/benchmark_packs/gallery-builder-test-strict-bad",
        pipeline_specs=[_good_spec_dict("strict-bad")], run_immediately=True,
        limitations=["gallery builder test"], provenance="gallery builder test",
    )
    good_pack = build_benchmark_pack(spec_good)
    bad_pack = build_benchmark_pack(spec_bad)
    Path(bad_pack.generated_report_pack_paths[0]).unlink()

    gallery = build_benchmark_gallery(
        [
            "outputs/benchmark_packs/gallery-builder-test-strict-good/BenchmarkPack.json",
            "outputs/benchmark_packs/gallery-builder-test-strict-bad/BenchmarkPack.json",
        ],
        "outputs/benchmark_gallery_test", strict=True,
    )
    assert gallery.verified_pack_ids == [good_pack.benchmark_pack_id]
    assert gallery.failed_pack_ids == [bad_pack.benchmark_pack_id]


def test_output_root_safety_enforced():
    with pytest.raises(BenchmarkPackStoreError):
        build_benchmark_gallery(["a/BenchmarkPack.json"], "/tmp/not-allowed")


def test_gallery_does_not_copy_raw_data():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/gallery-builder-test-nocopy", run_immediately=True)
    build_benchmark_pack(spec)
    gallery = build_benchmark_gallery(
        discover_benchmark_pack_paths("outputs/benchmark_packs/gallery-builder-test-nocopy"),
        "outputs/benchmark_gallery_test",
    )
    gallery_text = gallery.to_json()
    assert "data/raw" not in gallery_text
    for report_pack_path in gallery.report_pack_paths:
        assert "data/raw" not in report_pack_path
