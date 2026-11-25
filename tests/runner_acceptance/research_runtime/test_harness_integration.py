"""Tests for acceptance harness integration, report generation, and CLI runner."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.runner_acceptance.research_runtime.contracts import (
    AcceptanceReport,
    PlatformStatus,
    ScenarioOutcome,
    dumps_finite_json,
)
from tools.runner_acceptance.research_runtime.harness import (
    generate_markdown_report,
    run_acceptance_suite,
)


def test_run_acceptance_suite(tmp_path: Path) -> None:
    """Verifies that the full acceptance harness runs and returns a valid report."""
    report = run_acceptance_suite(base_dir=tmp_path)
    assert isinstance(report, AcceptanceReport)
    assert report.total_cases >= 14
    assert report.failed_cases == 0
    assert report.supported_cases > 0

    md = generate_markdown_report(report)
    assert "# Research Runtime Cross-Platform Acceptance Report" in md
    assert "Scenario Execution Matrix" in md

    dumped = dumps_finite_json(report.to_dict())
    loaded = json.loads(dumped)
    assert loaded["schema_version"] == "NeuroTopologySim.ResearchRuntimeAcceptanceReport.v1"
    assert loaded["total_cases"] == report.total_cases


def test_cli_runner(tmp_path: Path) -> None:
    """Verifies scripts/run_research_runtime_acceptance.py via subprocess."""
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    cmd = [
        sys.executable,
        "scripts/run_research_runtime_acceptance.py",
        "--output",
        str(out_json),
        "--markdown-output",
        str(out_md),
        "--json",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"CLI runner failed: {res.stderr}"

    assert out_json.exists()
    assert out_md.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["failed_cases"] == 0
    assert data["supported_cases"] > 0
