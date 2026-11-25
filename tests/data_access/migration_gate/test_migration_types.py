"""Tests for data-access migration gate types and serialization."""

from __future__ import annotations

import json
import pytest

from tools.data_access.migration_gate.types import (
    MANIFEST_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    GateClassification,
    GateReport,
    MigrationEntry,
    MigrationManifest,
    MigrationStatus,
    json_safe,
)


def test_migration_status_enum_values():
    expected_states = {
        "unmigrated",
        "safely migrated",
        "reviewed temporary exception",
        "unsafe blocked",
        "not applicable",
        "unable to assess",
    }
    actual_states = {status.value for status in MigrationStatus}
    assert actual_states == expected_states
    assert len(MigrationStatus) == 6


def test_migration_entry_creation_and_dict_serialization():
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #235",
        status=MigrationStatus.UNMIGRATED,
        severity="error",
        notes="Legacy downloader",
    )
    d = entry.to_dict()
    assert d["file"] == "scripts/fetch_real_datasets.py"
    assert d["symbol_or_line"] == "45"
    assert d["rule"] == "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL"
    assert d["owner"] == "@christianv"
    assert d["migration_reference"] == "PR #235"
    assert d["status"] == "unmigrated"
    assert d["severity"] == "error"
    assert d["notes"] == "Legacy downloader"

    # Test round trip from dict
    restored = MigrationEntry.from_dict(d)
    assert restored == entry


def test_migration_manifest_to_json_and_from_dict():
    entry = MigrationEntry(
        file="scripts/eeg_topology_ds005620.py",
        symbol_or_line="112",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@antigravity-c",
        migration_reference="RFC-008",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="security-lead",
        expires_at="2026-12-31",
        justification="Awaiting adapter migration",
    )
    manifest = MigrationManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        as_of_date="2026-09-11",
        entries=[entry],
        metadata={"test": True},
    )

    json_str = manifest.to_json()
    assert "NeuroTopology.DataAccessMigrationManifest.v1" in json_str

    parsed = json.loads(json_str)
    assert parsed["entry_count"] == 1
    assert parsed["entries"][0]["file"] == "scripts/eeg_topology_ds005620.py"

    restored = MigrationManifest.from_dict(parsed)
    assert len(restored.entries) == 1
    assert restored.entries[0].status == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION


def test_json_safe_rejects_nan_and_inf():
    assert json_safe(42) == 42
    assert json_safe("test") == "test"
    assert json_safe(MigrationStatus.UNMIGRATED) == "unmigrated"

    with pytest.raises(ValueError, match="Non-finite float value"):
        json_safe(float("nan"))

    with pytest.raises(ValueError, match="Non-finite float value"):
        json_safe(float("inf"))

    with pytest.raises(ValueError, match="Non-finite float value"):
        json_safe(float("-inf"))


def test_gate_report_checksum_determinism():
    report1 = GateReport(
        schema_version=REPORT_SCHEMA_VERSION,
        evaluation_date="2026-09-11",
        repository_root=".",
        gate_passed=True,
        compliance_claim_allowed=False,
        compliance_statement="Test statement",
    )
    checksum1 = report1.compute_checksum()
    assert isinstance(checksum1, str)
    assert len(checksum1) == 64

    report2 = GateReport(
        schema_version=REPORT_SCHEMA_VERSION,
        evaluation_date="2026-09-11",
        repository_root=".",
        gate_passed=True,
        compliance_claim_allowed=False,
        compliance_statement="Test statement",
    )
    assert report2.compute_checksum() == checksum1
