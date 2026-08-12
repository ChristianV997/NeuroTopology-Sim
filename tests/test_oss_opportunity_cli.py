"""Subprocess CLI tests for `python -m oss_opportunities.export_oss_opportunities`.
Synthetic fixtures only -- no network access, no live Trendshift scan."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT_ROOT = "outputs/oss_opportunities_cli_test"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "oss_opportunities.export_oss_opportunities", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / _OUT_ROOT, ignore_errors=True)


def _write_manual_seed(tmp_path: Path) -> Path:
    payload = {
        "snapshot_date": "2026-08-12",
        "repositories": [
            {
                "repo_full_name": "microsoft/markitdown", "description": "Convert documents to markdown for LLMs",
                "topics": ["document-conversion", "markdown"], "primary_language": "Python",
                "stars": 12000, "star_gain": 150, "license_spdx": "MIT", "license_name": "MIT License",
                "latest_activity_status": "active",
            },
            "docker/docker",
        ],
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_from_manual_seed_works(tmp_path):
    seed_path = _write_manual_seed(tmp_path)
    result = _run_cli("from-manual-seed", "--seed", str(seed_path), "--out", _OUT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["candidates_seen"] == 2
    assert (_REPO_ROOT / _OUT_ROOT / "OpenSourceLeverageBatch.json").exists()


def test_from_trendshift_fixture_works(tmp_path):
    payload = {
        "timeframe": "daily", "snapshot_date": "2026-08-12",
        "repositories": [
            {
                "repo_full_name": "3b1b/manim", "rank": 1, "description": "Animation engine",
                "topics": ["animation", "diagram"], "primary_language": "Python", "stars": 60000,
                "license_spdx": "MIT", "license_name": "MIT License", "latest_activity_status": "active",
            }
        ],
    }
    fixture_path = tmp_path / "trendshift.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli("from-trendshift-fixture", "--fixture", str(fixture_path), "--out", _OUT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload_out = json.loads(result.stdout)
    assert payload_out["candidates_seen"] == 1


def test_from_starmap_fixture_works(tmp_path):
    payload = {
        "category": "frontend", "snapshot_date": "2026-08-12",
        "repositories": [
            {
                "repo_full_name": "TanStack/router", "stack_layer": "frontend",
                "description": "Type-safe router for React", "topics": ["frontend", "react"],
                "primary_language": "TypeScript", "stars": 9000,
                "license_spdx": "MIT", "license_name": "MIT License", "latest_activity_status": "active",
            }
        ],
    }
    fixture_path = tmp_path / "starmap.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli("from-starmap-fixture", "--fixture", str(fixture_path), "--out", _OUT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload_out = json.loads(result.stdout)
    assert payload_out["candidates_seen"] == 1


def test_live_trendshift_scan_fails_without_explicit_flag():
    result = _run_cli("live-trendshift-scan", "--timeframe", "daily", "--out", _OUT_ROOT)
    assert result.returncode != 0
    assert "allow-live-network" in (result.stdout + result.stderr)


def test_plan_and_render_chain(tmp_path):
    seed_path = _write_manual_seed(tmp_path)
    _run_cli("from-manual-seed", "--seed", str(seed_path), "--out", _OUT_ROOT)
    batch_path = f"{_OUT_ROOT}/OpenSourceLeverageBatch.json"

    plan_result = _run_cli("plan", "--batch", batch_path, "--out", _OUT_ROOT, "--max-selected", "10")
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    assert (_REPO_ROOT / _OUT_ROOT / "OpenSourceIntegrationPlan.json").exists()

    render_result = _run_cli(
        "render", "--batch", batch_path, "--plan", f"{_OUT_ROOT}/OpenSourceIntegrationPlan.json",
        "--out", f"{_OUT_ROOT}/summary",
    )
    assert render_result.returncode == 0, render_result.stdout + render_result.stderr
    assert (_REPO_ROOT / _OUT_ROOT / "summary" / "summary.md").exists()
    assert (_REPO_ROOT / _OUT_ROOT / "summary" / "summary.html").exists()


def test_invalid_seed_path_fails_clearly():
    result = _run_cli("from-manual-seed", "--seed", "does/not/exist.json", "--out", _OUT_ROOT)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr


def test_unsafe_output_root_rejected(tmp_path):
    seed_path = _write_manual_seed(tmp_path)
    result = _run_cli("from-manual-seed", "--seed", str(seed_path), "--out", "/etc/evil")
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr


def test_invalid_trendshift_timeframe_in_fixture_fails_clearly(tmp_path):
    payload = {"timeframe": "hourly", "snapshot_date": "2026-08-12", "repositories": []}
    fixture_path = tmp_path / "bad_timeframe.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli("from-trendshift-fixture", "--fixture", str(fixture_path), "--out", _OUT_ROOT)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr
