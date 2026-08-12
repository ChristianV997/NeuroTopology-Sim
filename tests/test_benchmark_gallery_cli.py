"""Subprocess CLI tests for `python -m benchmark_packs.export_gallery`.
Real already-committed contract artifacts only -- no network access."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_gallery_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchmark_packs.export_gallery", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _run_pack_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchmark_packs.export_benchmark_pack", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_gallery_cli_test", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _build_demo_pack(name: str) -> str:
    out = f"outputs/benchmark_packs/gallery-cli-{name}"
    result = _run_pack_cli("build-default", "--kind", "demo_pack", "--out", out, "--run-immediately")
    assert result.returncode == 0, result.stdout + result.stderr
    return f"{out}/BenchmarkPack.json"


def test_verify_works():
    pack_path = _build_demo_pack("verify")
    result = _run_gallery_cli("verify", "--pack", pack_path)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verification_status"] == "passed"


def test_build_gallery_works():
    pack_path = _build_demo_pack("build-gallery")
    result = _run_gallery_cli(
        "build-gallery", "--pack", pack_path, "--out", "outputs/benchmark_gallery_cli_test",
        "--gallery-name", "CLI Test Gallery",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verified_pack_ids"]
    assert payload["generated_gallery_index_path"] is not None
    assert (_REPO_ROOT / payload["generated_gallery_index_path"]).exists()


def test_scan_and_build_works():
    _build_demo_pack("scan-a")
    _build_demo_pack("scan-b")
    result = _run_gallery_cli(
        "scan-and-build", "--root", "outputs/benchmark_packs", "--out", "outputs/benchmark_gallery_cli_test",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["verified_pack_ids"]) == 2


def test_render_index_works():
    pack_path = _build_demo_pack("render-index")
    build_result = _run_gallery_cli(
        "build-gallery", "--pack", pack_path, "--out", "outputs/benchmark_gallery_cli_test",
    )
    built = json.loads(build_result.stdout)

    result = _run_gallery_cli(
        "render-index", "--gallery", "outputs/benchmark_gallery_cli_test/BenchmarkGallery.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["index_html_path"] == built["generated_gallery_index_path"]


def test_invalid_pack_path_fails_clearly():
    result = _run_gallery_cli("verify", "--pack", "outputs/benchmark_packs/does-not-exist/BenchmarkPack.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["verification_status"] == "failed"


def test_non_strict_mode_works():
    pack_path = _build_demo_pack("non-strict")
    result = _run_gallery_cli("verify", "--pack", pack_path, "--non-strict")
    assert result.returncode == 0, result.stdout + result.stderr


def test_scan_and_build_fails_clearly_when_no_packs_found():
    result = _run_gallery_cli("scan-and-build", "--root", "outputs/benchmark_packs", "--out", "outputs/benchmark_gallery_cli_test")
    assert result.returncode != 0
    assert "FAILED" in result.stdout
