"""Tests for `benchmark_packs.renderer`: renders `index.html`, includes
required sections, escapes unsafe text, no external assets, deterministic
output, links only existing artifacts, guardrail-safe."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark_packs.pack_manifest import BenchmarkPackV1
from benchmark_packs.renderer import render_benchmark_pack_index, render_index_html
from benchmark_packs.validation import BenchmarkPackStoreError, scan_text_for_banned_phrases

_REPO_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_SECTIONS = [
    "Purpose", "Execution summary", "Datasets / modalities / input modes included",
    "Report packs", "HTML report links", "Coverage summary", "Limitations",
    "Blocked interpretations", "Reproducibility commands", "Generated artifact manifest", "Future work",
]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)


def _demo_pack(**overrides) -> BenchmarkPackV1:
    kwargs = dict(
        source_spec_id="spec1", batch_id="batch1", report_pack_ids=["rp1"], html_pack_ids=["hp1"],
        pack_name="Demo Pack", pack_kind="demo_pack", pack_purpose="demo purpose",
        execution_summary={"total_jobs": 1, "completed": 1, "failed": 0, "status": "completed"},
        coverage_summary={"n_report_packs": 1}, dataset_ids=["ds005620"], modalities=["EEG"],
        input_modes=["builtin_ds005620_cohort_summary"],
        generated_report_pack_paths=["outputs/report_packs/demo/ReportPack.json"],
        generated_html_paths=["outputs/report_packs/demo/html/index.html"],
        reproducibility_commands=["python -m benchmark_packs.export_benchmark_pack build --spec x.json"],
        limitations=["demo test"],
    )
    kwargs.update(overrides)
    return BenchmarkPackV1.make(**kwargs)


def test_render_index_html_includes_all_required_sections():
    pack = _demo_pack()
    html_text, sections = render_index_html(pack)
    for section in _REQUIRED_SECTIONS:
        assert section in sections
        assert section in html_text


def test_render_index_html_escapes_unsafe_text():
    pack = _demo_pack(pack_name="<script>alert(1)</script>", pack_purpose="<img src=x onerror=alert(1)>")
    html_text, _ = render_index_html(pack)
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "<img src=x" not in html_text
    assert "&lt;img src=x" in html_text


def test_render_index_html_has_no_external_assets():
    pack = _demo_pack()
    html_text, _ = render_index_html(pack)
    assert "<script" not in html_text
    assert "cdn." not in html_text.lower()
    assert "http://" not in html_text and "https://" not in html_text


def test_render_index_html_is_deterministic():
    pack = _demo_pack()
    first, _ = render_index_html(pack)
    second, _ = render_index_html(pack)
    assert first == second


def test_render_index_html_links_only_existing_artifacts():
    pack = _demo_pack()
    html_text, _ = render_index_html(pack)
    for path in pack.generated_html_paths:
        assert path in html_text
    assert "does/not/exist" not in html_text


def test_render_index_html_no_links_for_missing_html_packs():
    pack = _demo_pack(html_pack_ids=[], generated_html_paths=[])
    html_text, _ = render_index_html(pack)
    assert "No HTML report packs were generated." in html_text


def test_render_benchmark_pack_index_writes_file_and_returns_index():
    pack = _demo_pack()
    index = render_benchmark_pack_index(pack, "outputs/benchmark_packs/renderer-test")
    assert index.benchmark_pack_id == pack.benchmark_pack_id
    assert index.index_html_path is not None
    assert (_REPO_ROOT / index.index_html_path).exists()
    assert index.validate() == []


def test_render_benchmark_pack_index_guardrail_scan_passes_for_clean_pack():
    pack = _demo_pack()
    index = render_benchmark_pack_index(pack, "outputs/benchmark_packs/renderer-guardrail")
    html_text = (_REPO_ROOT / index.index_html_path).read_text(encoding="utf-8")
    assert scan_text_for_banned_phrases(html_text) == []


def test_render_benchmark_pack_index_refuses_to_write_banned_phrase():
    pack = _demo_pack(pack_purpose="this run confirms diagnosis beyond doubt")
    with pytest.raises(BenchmarkPackStoreError):
        render_benchmark_pack_index(pack, "outputs/benchmark_packs/renderer-banned")
    assert not (_REPO_ROOT / "outputs/benchmark_packs/renderer-banned/index.html").exists()
