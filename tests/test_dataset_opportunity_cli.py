"""Subprocess CLI tests for `python -m dataset_opportunities.export_opportunities`.
Synthetic fixtures only -- no network access, no eegdash live query."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests._dataset_opportunity_fixtures import make_blocked_candidate, make_good_candidate

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT_ROOT = "outputs/dataset_opportunities_cli_test"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dataset_opportunities.export_opportunities", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / _OUT_ROOT, ignore_errors=True)


def _write_candidates_fixture(tmp_path: Path) -> Path:
    candidates = [make_good_candidate().to_dict(), make_blocked_candidate().to_dict()]
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    return path


def test_from_candidates_works(tmp_path):
    candidates_path = _write_candidates_fixture(tmp_path)
    result = _run_cli("from-candidates", "--candidates", str(candidates_path), "--out", _OUT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["total_candidates_seen"] == 2
    assert payload["total_opportunities_ranked"] == 1
    assert (_REPO_ROOT / _OUT_ROOT / "DatasetOpportunityBatch.json").exists()


def test_plan_and_render_chain(tmp_path):
    candidates_path = _write_candidates_fixture(tmp_path)
    _run_cli("from-candidates", "--candidates", str(candidates_path), "--out", _OUT_ROOT)
    batch_path = f"{_OUT_ROOT}/DatasetOpportunityBatch.json"

    plan_result = _run_cli("plan", "--batch", batch_path, "--out", _OUT_ROOT, "--max-selected", "5")
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    assert (_REPO_ROOT / _OUT_ROOT / "DatasetOpportunityPlan.json").exists()

    render_result = _run_cli(
        "render", "--batch", batch_path, "--plan", f"{_OUT_ROOT}/DatasetOpportunityPlan.json",
        "--out", f"{_OUT_ROOT}/summary.md",
    )
    assert render_result.returncode == 0, render_result.stdout + render_result.stderr
    assert (_REPO_ROOT / _OUT_ROOT / "summary.md").exists()


def test_eegdash_metadata_query_fails_without_explicit_flag():
    result = _run_cli("eegdash-metadata-query", "--out", _OUT_ROOT)
    assert result.returncode != 0
    assert "allow-live-metadata-query" in (result.stdout + result.stderr)


def test_invalid_candidates_path_fails_clearly():
    result = _run_cli("from-candidates", "--candidates", "does/not/exist.json", "--out", _OUT_ROOT)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr


def test_unsafe_output_root_rejected(tmp_path):
    candidates_path = _write_candidates_fixture(tmp_path)
    result = _run_cli("from-candidates", "--candidates", str(candidates_path), "--out", "/etc/evil")
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr


def test_from_eegdash_fixture_works(tmp_path):
    fixture = {
        "source_catalog": "eegdash",
        "datasets": [
            {
                "dataset_id": "ds000321", "name": "Fixture EEGDash Dataset", "source": "openneuro",
                "recording_modality": "EEG", "datatypes": ["eeg"], "license": "CC0",
                "tasks": ["rest"], "sessions": ["ses-1"], "demographics": {"subjects_count": 10},
            }
        ],
    }
    fixture_path = tmp_path / "eegdash_fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    result = _run_cli("from-eegdash-fixture", "--fixture", str(fixture_path), "--out", _OUT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["total_candidates_seen"] == 1
