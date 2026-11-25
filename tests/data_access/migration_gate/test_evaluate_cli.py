"""Tests for evaluate_data_access_migration.py CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.evaluate_data_access_migration import main

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cli_clean_manifest_passes(tmp_path, capsys):
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    rc = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "clean_manifest.json"),
        "--as-of-date", "2026-09-11",
        "--output-json", str(out_json),
        "--output-markdown", str(out_md),
        "--format", "summary",
    ])

    assert rc == 0
    captured = capsys.readouterr()
    assert "GATE_PASSED" in captured.out
    assert "PROHIBITED" in captured.out

    assert out_json.is_file()
    assert out_md.is_file()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["gate_passed"] is True
    assert data["compliance_claim_allowed"] is False


def test_cli_strict_mode_fails_on_unmigrated(capsys):
    rc = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "clean_manifest.json"),
        "--as-of-date", "2026-09-11",
        "--strict",
    ])

    assert rc == 1
    captured = capsys.readouterr()
    assert "Strict mode enabled" in captured.out


def test_cli_stale_exception_fails(capsys):
    rc = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "stale_exception_manifest.json"),
        "--as-of-date", "2026-09-11",
    ])

    assert rc == 1
    captured = capsys.readouterr()
    assert "GATE_BLOCKED" in captured.out
    assert "stale/expired exception" in captured.out


def test_cli_hidden_finding_fails(capsys):
    rc = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "hidden_finding_manifest.json"),
        "--as-of-date", "2026-09-11",
    ])

    assert rc == 1
    captured = capsys.readouterr()
    assert "hidden/untracked finding" in captured.out


def test_cli_json_and_markdown_format(capsys):
    rc_json = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "clean_manifest.json"),
        "--as-of-date", "2026-09-11",
        "--format", "json",
    ])
    assert rc_json == 0
    captured_json = capsys.readouterr()
    parsed = json.loads(captured_json.out)
    assert parsed["schema_version"] == "NeuroTopology.DataAccessMigrationGateReport.v1"

    rc_md = main([
        "--scanner-report", str(FIXTURES / "scanner_sample_findings.json"),
        "--manifest", str(FIXTURES / "clean_manifest.json"),
        "--as-of-date", "2026-09-11",
        "--format", "markdown",
    ])
    assert rc_md == 0
    captured_md = capsys.readouterr()
    assert "# Data-Access Migration Gate Report" in captured_md.out
