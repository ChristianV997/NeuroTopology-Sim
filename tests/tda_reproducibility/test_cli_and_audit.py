"""Integration tests for master audit orchestrator and CLI entrypoint."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.tda_reproducibility.audit import run_tda_reproducibility_audit
from tools.tda_reproducibility.fixtures import make_circle_fixture, make_triangle_fixture
from tools.tda_reproducibility.reporters import (
    format_markdown_report,
    format_obsidian_mirror,
    format_terminal_summary,
)


def test_audit_runs_cleanly_on_standard_fixtures():
    fixtures = [make_triangle_fixture(), make_circle_fixture(n_points=6)]
    report = run_tda_reproducibility_audit(fixtures=fixtures)
    assert report.schema_version == "1.0.0"
    assert report.all_invariants_passed is True
    assert report.spatial_charge_isolation_confirmed is True
    assert len(report.fixture_results) == 2
    assert report.provenance_hash != ""

    # Test strict JSON serialization (must not throw on allow_nan=False)
    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["schema_version"] == "1.0.0"
    assert parsed["all_invariants_passed"] is True
    assert parsed["spatial_charge_isolation_confirmed"] is True


def test_reporters_output_valid_strings():
    fixtures = [make_triangle_fixture()]
    report = run_tda_reproducibility_audit(fixtures=fixtures)

    term = format_terminal_summary(report)
    assert "TDA BACKEND REPRODUCIBILITY & EQUIVALENCE AUDIT" in term
    assert "ripser" in term

    md = format_markdown_report(report)
    assert "# TDA Backend Reproducibility and Equivalence Audit Report" in md
    assert "Provenance Hash" in md

    obs = format_obsidian_mirror(report)
    assert "tags:" in obs
    assert "[[ripser]]" in obs


def test_cli_execution_summary():
    repo_root = Path(__file__).resolve().parent.parent.parent
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "audit_tda_reproducibility.py"),
        "--fixtures",
        "triangle_equilateral_3",
        "--format",
        "summary",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "TDA BACKEND REPRODUCIBILITY" in res.stdout


def test_cli_execution_json():
    repo_root = Path(__file__).resolve().parent.parent.parent
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "audit_tda_reproducibility.py"),
        "--fixtures",
        "triangle_equilateral_3",
        "--format",
        "json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["schema_version"] == "1.0.0"
    assert "all_invariants_passed" in data
