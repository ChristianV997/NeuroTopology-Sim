"""Tests for `workflows.html_report_pack.render_html_report_pack` and
`workflows.html_renderer.render_index_html` against a real, small
already-committed contract artifact (`contracts/btc_icft/ds005620/
pitnn_cohort/`) -- no raw data reprocessing, no downloads.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from workflows.html_report_pack import render_html_report_pack
from workflows.html_validation import scan_html_for_banned_phrases
from workflows.report_pipeline import ReportPipelineSpecV1, run_report_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _build_report_pack(name: str, *, include_report: bool = True):
    out = f"outputs/report_packs/html-renderer-test-{name}"
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", output_root=out,
        modality="EEG", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=include_report,
        limitations=["test"], provenance="test",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    return out, manifest


def test_renders_index_html():
    out, manifest = _build_report_pack("basic")
    html_pack = render_html_report_pack(
        report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html",
        pipeline_manifest_path=f"{out}/PipelineRunManifest.json",
    )
    index_path = _REPO_ROOT / html_pack.index_html_path
    assert index_path.exists()
    text = index_path.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")


def test_includes_required_sections():
    out, _ = _build_report_pack("sections")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    expected = {
        "header", "executive_summary", "evidence_chain", "registry_summary", "transition_summary",
        "phase_space_summary", "null_control_summary", "claim_evidence_summary", "validation_summary",
        "limitations", "blocked_interpretations", "reproducibility_commands", "artifact_manifest",
        "artifact_links", "future_work",
    }
    assert expected.issubset(set(html_pack.rendered_sections))


def test_includes_limitations_text():
    import html as _html

    out, _ = _build_report_pack("limitations")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    for item in html_pack.limitations:
        assert _html.escape(item.split(" -- ")[0][:40]) in text


def test_includes_blocked_interpretations_text():
    out, _ = _build_report_pack("blocked")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert "does not support a clinical claim" in text
    assert "does not support a diagnostic claim" in text


def test_includes_reproducibility_commands():
    out, _ = _build_report_pack("repro")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert "python -m workflows.export_report_pack" in text
    assert "python -m workflows.export_html_report_pack" in text


def test_includes_artifact_manifest():
    out, _ = _build_report_pack("manifest")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert "evidence_bundle_paths" in text
    assert "Generated artifact manifest" in text


def test_escapes_unsafe_text(tmp_path):
    out, _ = _build_report_pack("escape")
    # Inject unsafe text into the report pack's own artifact_manifest field
    # (a field this renderer's "Generated artifact manifest" section
    # definitely surfaces) and confirm it survives only in escaped form,
    # never as raw markup.
    import json

    report_pack_path = _REPO_ROOT / out / "ReportPack.json"
    data = json.loads(report_pack_path.read_text(encoding="utf-8"))
    data["artifact_manifest"]["untrusted_note"] = "<script>alert(1)</script>"
    tampered_path = tmp_path / "ReportPack.json"
    tampered_path.write_text(json.dumps(data), encoding="utf-8")

    html_pack = render_html_report_pack(report_pack_path=tampered_path, out_dir=f"{out}/html-escape")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def _strip_volatile_lines(text: str) -> str:
    # Only the "Generated: <timestamp>" meta line and the output-dir name
    # legitimately differ between two back-to-back renders of the same
    # source ReportPack -- every other byte must match.
    lines = [line for line in text.splitlines() if "Generated:" not in line]
    return "\n".join(lines)


def test_deterministic_output_across_repeated_renders():
    out, _ = _build_report_pack("determinism")
    pack1 = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html-a")
    pack2 = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html-b")

    text1 = _strip_volatile_lines((_REPO_ROOT / pack1.index_html_path).read_text(encoding="utf-8")).replace("html-a", "html-X")
    text2 = _strip_volatile_lines((_REPO_ROOT / pack2.index_html_path).read_text(encoding="utf-8")).replace("html-b", "html-X")
    assert text1 == text2


def test_no_external_assets_or_cdns():
    out, _ = _build_report_pack("noexternal")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text
    assert "<script" not in text.lower()


def test_no_raw_html_injection_from_markdown():
    out, _ = _build_report_pack("md-safe")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    # The embedded EvidenceReport.md content contains raw '#'/'|' Markdown
    # syntax -- confirm it is shown as escaped text inside <pre>, not
    # converted into real <h1>/<table> elements.
    assert "<pre># Governed Evidence Report" in text


def test_scan_html_for_banned_phrases_clean_on_real_render():
    out, _ = _build_report_pack("guardrail")
    html_pack = render_html_report_pack(report_pack_path=f"{out}/ReportPack.json", out_dir=f"{out}/html")
    text = (_REPO_ROOT / html_pack.index_html_path).read_text(encoding="utf-8")
    assert scan_html_for_banned_phrases(text) == []


def test_scan_html_for_banned_phrases_detects_injected_phrase():
    assert scan_html_for_banned_phrases("this text confirms diagnosis of something") == ["confirms diagnosis"]
    assert scan_html_for_banned_phrases("a completely clean sentence") == []
