"""Subprocess CLI tests for `python -m benchmark_packs.export_benchmark_pack`.
Real already-committed contract artifacts only -- no network access."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchmark_packs.export_benchmark_pack", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def test_create_spec_works():
    result = _run_cli(
        "create-spec", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-create-spec/spec.json",
        "--output-root", "outputs/benchmark_packs/cli-test-create-spec",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["benchmark_pack_spec_id"]
    assert (_REPO_ROOT / "outputs/benchmark_packs/cli-test-create-spec/spec.json").exists()


def test_create_spec_does_not_create_jobs():
    _run_cli(
        "create-spec", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-no-jobs/spec.json",
        "--output-root", "outputs/benchmark_packs/cli-test-no-jobs",
    )
    assert not (_REPO_ROOT / "outputs/jobs").exists()


def test_build_works():
    _run_cli(
        "create-spec", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-build/spec.json",
        "--output-root", "outputs/benchmark_packs/cli-test-build",
    )
    result = _run_cli("build", "--spec", "outputs/benchmark_packs/cli-test-build/spec.json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["benchmark_pack_id"]
    assert payload["execution_summary"]["status"] == "not_run"


def test_build_default_works():
    result = _run_cli(
        "build-default", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-build-default",
        "--run-immediately",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["execution_summary"]["status"] == "completed"
    assert len(payload["report_pack_ids"]) == 4


def test_build_default_with_include_html_renders_index():
    result = _run_cli(
        "build-default", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-build-default-html",
        "--run-immediately", "--include-html",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["generated_index_path"] is not None
    assert (_REPO_ROOT / payload["generated_index_path"]).exists()


def test_render_index_works():
    build_result = _run_cli(
        "build-default", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-render-index",
        "--run-immediately", "--include-html",
    )
    built = json.loads(build_result.stdout)

    result = _run_cli(
        "render-index", "--pack", "outputs/benchmark_packs/cli-test-render-index/BenchmarkPack.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["index_html_path"] == built["generated_index_path"]


def test_invalid_output_root_fails_clearly():
    result = _run_cli("build-default", "--kind", "demo_pack", "--out", "/tmp/not-allowed")
    assert result.returncode != 0
    assert "FAILED" in result.stdout


def test_invalid_pack_kind_fails_clearly():
    result = _run_cli("create-spec", "--kind", "not_a_real_kind", "--out", "/tmp/x.json")
    assert result.returncode != 0


def test_missing_report_outputs_do_not_crash_render_index():
    _run_cli(
        "build-default", "--kind", "demo_pack", "--out", "outputs/benchmark_packs/cli-test-no-html",
    )
    result = _run_cli(
        "render-index", "--pack", "outputs/benchmark_packs/cli-test-no-html/BenchmarkPack.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
