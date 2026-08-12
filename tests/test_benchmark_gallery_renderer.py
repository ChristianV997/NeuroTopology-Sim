"""Tests for `benchmark_packs.gallery_renderer`: renders `index.html`,
required sections, escaping, no external assets, deterministic output,
links only existing artifacts, guardrail-safe."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark_packs.gallery import BenchmarkGalleryV1
from benchmark_packs.gallery_renderer import render_benchmark_gallery_index, render_gallery_index_html
from benchmark_packs.validation import BenchmarkPackStoreError, scan_text_for_banned_phrases

_REPO_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_SECTIONS = [
    "Verification summary", "Pack table", "Dataset / modality coverage", "Links to benchmark-pack indexes",
    "Links to HTML report packs", "Failed / warning packs", "Limitations", "Blocked interpretations",
    "Reproducibility / rebuild notes", "Generated artifact manifest", "Future work",
]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_gallery_renderer_test", ignore_errors=True)


def _demo_gallery(**overrides) -> BenchmarkGalleryV1:
    kwargs = dict(
        gallery_name="Demo Gallery", benchmark_pack_paths=["outputs/benchmark_packs/x/BenchmarkPack.json"],
        verification_paths=["outputs/gallery/verifications/p1.json"], verified_pack_ids=["p1"], failed_pack_ids=[],
        pack_summaries=[{
            "benchmark_pack_id": "p1", "pack_name": "Demo Pack", "pack_kind": "demo_pack",
            "pack_purpose": "demo", "dataset_ids": ["ds005620"], "modalities": ["EEG"],
            "input_modes": ["builtin_ds005620_cohort_summary"], "report_pack_count": 1, "html_pack_count": 1,
            "verification_status": "passed", "limitations_count": 2,
            "generated_index_path": "outputs/benchmark_packs/x/index.html",
            "source_pack_path": "outputs/benchmark_packs/x/BenchmarkPack.json",
        }],
        dataset_ids=["ds005620"], modalities=["EEG"], input_modes=["builtin_ds005620_cohort_summary"],
        html_index_paths=["outputs/benchmark_packs/x/reports/y/html/index.html"],
        report_pack_paths=["outputs/benchmark_packs/x/reports/y/ReportPack.json"],
        limitations=["demo gallery test"],
    )
    kwargs.update(overrides)
    return BenchmarkGalleryV1.make(**kwargs)


def test_render_includes_all_required_sections():
    gallery = _demo_gallery()
    html_text, sections = render_gallery_index_html(gallery)
    for section in _REQUIRED_SECTIONS:
        assert section in sections
        assert section in html_text


def test_render_escapes_unsafe_text():
    gallery = _demo_gallery(gallery_name="<script>alert(1)</script>")
    html_text, _ = render_gallery_index_html(gallery)
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text


def test_render_no_external_assets():
    gallery = _demo_gallery()
    html_text, _ = render_gallery_index_html(gallery)
    assert "<script" not in html_text
    assert "cdn." not in html_text.lower()
    assert "http://" not in html_text and "https://" not in html_text


def test_render_is_deterministic():
    gallery = _demo_gallery()
    first, _ = render_gallery_index_html(gallery)
    second, _ = render_gallery_index_html(gallery)
    assert first == second


def test_render_links_only_existing_artifacts():
    gallery = _demo_gallery()
    html_text, _ = render_gallery_index_html(gallery)
    for path in gallery.html_index_paths:
        assert path in html_text
    for summary in gallery.pack_summaries:
        assert summary["generated_index_path"] in html_text
    assert "does/not/exist" not in html_text


def test_render_deterministic_pack_ordering_by_name_then_id():
    gallery = _demo_gallery(pack_summaries=[
        {"benchmark_pack_id": "z2", "pack_name": "Zeta", "pack_kind": "demo_pack", "pack_purpose": "", "dataset_ids": [], "modalities": [], "input_modes": [], "report_pack_count": 0, "html_pack_count": 0, "verification_status": "passed", "limitations_count": 1, "generated_index_path": None, "source_pack_path": "z.json"},
        {"benchmark_pack_id": "a1", "pack_name": "Alpha", "pack_kind": "demo_pack", "pack_purpose": "", "dataset_ids": [], "modalities": [], "input_modes": [], "report_pack_count": 0, "html_pack_count": 0, "verification_status": "passed", "limitations_count": 1, "generated_index_path": None, "source_pack_path": "a.json"},
    ])
    html_text, _ = render_gallery_index_html(gallery)
    assert html_text.index("Alpha") < html_text.index("Zeta")


def test_render_benchmark_gallery_index_writes_file_and_returns_index():
    gallery = _demo_gallery()
    index = render_benchmark_gallery_index(gallery, "outputs/benchmark_gallery_renderer_test")
    assert index.gallery_id == gallery.gallery_id
    assert index.index_html_path is not None
    assert (_REPO_ROOT / index.index_html_path).exists()
    assert index.validate() == []


def test_render_guardrail_scan_passes_for_clean_gallery():
    gallery = _demo_gallery()
    index = render_benchmark_gallery_index(gallery, "outputs/benchmark_gallery_renderer_test")
    html_text = (_REPO_ROOT / index.index_html_path).read_text(encoding="utf-8")
    assert scan_text_for_banned_phrases(html_text) == []


def test_render_refuses_to_write_banned_phrase():
    gallery = _demo_gallery(gallery_name="this run confirms diagnosis beyond doubt")
    with pytest.raises(BenchmarkPackStoreError):
        render_benchmark_gallery_index(gallery, "outputs/benchmark_gallery_renderer_test")
    assert not (_REPO_ROOT / "outputs/benchmark_gallery_renderer_test/index.html").exists()
