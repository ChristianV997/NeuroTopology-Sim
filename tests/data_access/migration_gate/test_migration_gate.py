"""Integration tests for DataAccessMigrationGate orchestration, fail-closed behavior, and reporting."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import pytest

from tools.data_access.migration_gate.gate import DataAccessMigrationGate
from tools.data_access.migration_gate.types import MigrationStatus

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_clean_manifest_evaluation_tracks_without_suppression():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "clean_manifest.json",
        current_date="2026-09-11",
        strict=False,
    )

    # Gate passes because all findings are legitimately tracked with owners/references,
    # and there are 0 hidden findings, 0 stale exceptions, 0 unsafe approvals.
    assert report.gate_passed is True

    # Rule 10: Repository-wide compliance MUST BE PROHIBITED because unresolved findings remain!
    assert report.compliance_claim_allowed is False
    assert "PROHIBITED" in report.compliance_statement

    # Before counts: 2 scanner findings (both error)
    assert report.before_counts["total"] == 2
    assert report.before_counts["by_severity"]["error"] == 2

    # After counts
    assert report.after_counts["reviewed_temporary_exception"] == 1
    assert report.after_counts["unmigrated"] == 1
    assert report.after_counts["safely_migrated"] == 1
    assert report.after_counts["not_applicable"] == 1
    assert report.after_counts["unsafe_blocked"] == 0
    assert report.after_counts["unresolved_total"] == 2
    assert report.after_counts["resolved_total"] == 2

    # Checksum is present and 64 hex chars
    assert len(report.checksum) == 64


def test_strict_mode_fails_on_unmigrated_debt():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "clean_manifest.json",
        current_date="2026-09-11",
        strict=True,
    )

    # In strict mode, gate fails because unmigrated findings remain
    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert any("Strict mode enabled" in reason for reason in report.fail_closed_reasons)


def test_progress_manifest_tracks_counts_and_resolutions():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "progress_manifest.json",
        current_date="2026-09-11",
        strict=False,
    )

    assert report.gate_passed is True
    assert report.compliance_claim_allowed is False
    assert report.after_counts["safely_migrated"] == 2
    assert report.after_counts["unmigrated"] == 1
    assert report.after_counts["reviewed_temporary_exception"] == 1
    assert report.after_counts["resolved_total"] == 2


def test_stale_exception_fails_closed():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "stale_exception_manifest.json",
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert len(report.stale_exceptions) > 0
    assert any("stale/expired exception" in reason for reason in report.fail_closed_reasons)
    assert any("Exception expired" in s["reason"] for s in report.stale_exceptions)


def test_hidden_finding_fails_closed():
    # Manifest only covers 1 of the 2 findings
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "hidden_finding_manifest.json",
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert len(report.hidden_findings) == 1
    assert report.hidden_findings[0]["file"] == "scripts/eeg_topology_ds005620.py"
    assert any("hidden/untracked finding" in reason for reason in report.fail_closed_reasons)


def test_unsafe_approval_manifest_fails_closed():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "unsafe_approval_manifest.json",
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert len(report.unsafe_approvals) >= 4  # Prohibited rule x2, wildcard, permanent
    assert any("unsafe exception approval attempt" in reason for reason in report.fail_closed_reasons)


def test_malformed_manifest_fails_closed():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "malformed_manifest.json",
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert report.after_counts["unable_to_assess"] > 0
    assert any("classified as unable to assess" in reason for reason in report.fail_closed_reasons)


def test_missing_scanner_input_fails_closed():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=None,
        manifest_input=FIXTURES / "clean_manifest.json",
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert any("No scanner findings provided" in reason for reason in report.fail_closed_reasons)


def test_missing_manifest_input_fails_closed():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=None,
        current_date="2026-09-11",
    )

    assert report.gate_passed is False
    assert report.compliance_claim_allowed is False
    assert "CRITICAL: Migration manifest could not be loaded" in report.compliance_statement


def test_zero_network_execution(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("Migration gate must not perform any network calls!")

    monkeypatch.setattr(socket, "socket", fail_socket)

    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "clean_manifest.json",
        current_date="2026-09-11",
    )
    assert report.gate_passed is True


def test_finite_json_and_markdown_serialization():
    gate = DataAccessMigrationGate()
    report = gate.evaluate(
        scanner_input=FIXTURES / "scanner_sample_findings.json",
        manifest_input=FIXTURES / "clean_manifest.json",
        current_date="2026-09-11",
    )

    # Finite JSON test: allow_nan=False
    json_str = report.to_json()
    assert "NeuroTopology.DataAccessMigrationGateReport.v1" in json_str
    parsed = json.loads(json_str)
    assert parsed["gate_passed"] is True
    assert parsed["compliance_claim_allowed"] is False

    # Markdown test
    md_str = report.to_markdown()
    assert "# Data-Access Migration Gate Report" in md_str
    assert "PROHIBITED" in md_str
    assert "scripts/fetch_real_datasets.py" in md_str
