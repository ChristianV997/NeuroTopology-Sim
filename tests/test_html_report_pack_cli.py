"""Subprocess CLI tests for `python -m workflows.export_html_report_pack`.
Real already-committed contract artifacts only -- no network access, no
raw dataset download.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from workflows.report_pipeline import ReportPipelineSpecV1, run_report_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "workflows.export_html_report_pack", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup_report_packs():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _build_report_pack(name: str):
    out = f"outputs/report_packs/html-cli-test-{name}"
    spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", output_root=out,
        modality="EEG", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["cli test"], provenance="cli test fixture",
    )
    manifest = run_report_pipeline(spec)
    assert manifest.execution_status == "completed", manifest.errors
    return out


def test_cli_happy_path_works():
    out = _build_report_pack("happy")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--pipeline-manifest", f"{out}/PipelineRunManifest.json", "--out", f"{out}/html")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["validation_status"] == "valid"
    assert (_REPO_ROOT / out / "html" / "index.html").exists()
    assert (_REPO_ROOT / out / "html" / "HtmlReportPack.json").exists()


def test_cli_missing_report_pack_fails():
    result = _run_cli("--report-pack", "outputs/report_packs/does-not-exist/ReportPack.json", "--out", "outputs/report_packs/html-cli-test-missing/html")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_output_root_fails():
    out = _build_report_pack("badroot")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--out", "/etc/evil")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_copy_artifacts_works():
    out = _build_report_pack("copy")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--out", f"{out}/html", "--copy-artifacts")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["copied_artifact_count"] > 0
    assert (_REPO_ROOT / out / "html" / "artifacts" / "ReportPack.json").exists()


def test_cli_no_copy_artifacts_works():
    out = _build_report_pack("nocopy")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--out", f"{out}/html", "--no-copy-artifacts")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["copied_artifact_count"] == 0
    assert not (_REPO_ROOT / out / "html" / "artifacts").exists()


def test_cli_title_override_works():
    out = _build_report_pack("title")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--out", f"{out}/html", "--title", "My Custom Title")
    assert result.returncode == 0, result.stdout + result.stderr
    index_text = (_REPO_ROOT / out / "html" / "index.html").read_text(encoding="utf-8")
    assert "My Custom Title" in index_text


def test_cli_prints_concise_summary():
    out = _build_report_pack("summary")
    result = _run_cli("--report-pack", f"{out}/ReportPack.json", "--out", f"{out}/html")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    for key in ("html_pack_id", "report_pack_id", "dataset_id", "input_mode", "output_root", "index_html_path", "validation_status"):
        assert key in payload


def test_cli_never_downloads_raw_data():
    source = (_REPO_ROOT / "workflows" / "export_html_report_pack.py").read_text(encoding="utf-8")
    source += (_REPO_ROOT / "workflows" / "html_report_pack.py").read_text(encoding="utf-8")
    source += (_REPO_ROOT / "workflows" / "html_renderer.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "boto3", "s3.download", "nilearn.datasets.fetch"):
        assert banned not in source
