"""Tests for classification logic and untracked/hidden finding detection."""

from __future__ import annotations

import pytest

from tools.data_access.migration_gate.classifier import MigrationClassifier
from tools.data_access.migration_gate.types import (
    MigrationEntry,
    MigrationManifest,
    MigrationStatus,
)


def test_classify_valid_unmigrated_finding():
    entry = MigrationEntry(
        file="scripts/eeg_topology_ds005620.py",
        symbol_or_line="112",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@antigravity-c",
        migration_reference="RFC-008",
        status=MigrationStatus.UNMIGRATED,
    )
    manifest = MigrationManifest(entries=[entry])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/eeg_topology_ds005620.py",
        "line": 112,
        "rule": "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        "severity": "error",
        "category": "remote_reader",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.UNMIGRATED
    assert classification.is_resolved is False
    assert classification.is_blocker is False
    assert hidden is None
    assert stale is None
    assert unsafe is None


def test_classify_valid_temporary_exception_finding():
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #235",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="security-lead",
        expires_at="2026-12-31",
        justification="Valid transition window",
    )
    manifest = MigrationManifest(entries=[entry])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/fetch_real_datasets.py",
        "line": 45,
        "rule": "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        "severity": "error",
        "category": "remote_reader",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION
    assert classification.is_resolved is False
    assert classification.is_blocker is False
    assert hidden is None
    assert stale is None
    assert unsafe is None


def test_classify_untracked_hidden_finding():
    # Empty manifest
    manifest = MigrationManifest(entries=[])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/hidden_download.py",
        "line": 22,
        "rule": "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        "severity": "error",
        "category": "remote_reader",
        "remediation": "Replace direct HTTP",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.UNSAFE_BLOCKED
    assert classification.is_blocker is True
    assert classification.is_resolved is False
    assert hidden is not None
    assert hidden["file"] == "scripts/hidden_download.py"
    assert "Untracked finding" in classification.reason


def test_classify_false_migration_claim():
    # Manifest claims it was safely migrated, but scanner STILL emitted finding!
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #235",
        status=MigrationStatus.SAFELY_MIGRATED,
    )
    manifest = MigrationManifest(entries=[entry])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/fetch_real_datasets.py",
        "line": 45,
        "rule": "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        "severity": "error",
        "category": "remote_reader",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.UNSAFE_BLOCKED
    assert classification.is_blocker is True
    assert "scanner still detected an active violation" in classification.reason
    assert unsafe is not None


def test_classify_stale_exception_finding():
    # Exception expired in 2025
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #201",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="past-lead",
        expires_at="2025-01-01",
        justification="Expired transition window",
    )
    manifest = MigrationManifest(entries=[entry])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/fetch_real_datasets.py",
        "line": 45,
        "rule": "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        "severity": "error",
        "category": "remote_reader",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.UNSAFE_BLOCKED
    assert classification.is_blocker is True
    assert stale is not None
    assert stale["expires_at"] == "2025-01-01"


def test_classify_prohibited_rule_approval():
    # Prohibited rule UNAUTHORIZED_OPENNEURO_DOWNLOAD
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="10",
        rule="UNAUTHORIZED_OPENNEURO_DOWNLOAD",
        owner="@rogue",
        migration_reference="RFC-BAD",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="lenient-reviewer",
        expires_at="2026-12-31",
        justification="Prohibited exception",
    )
    manifest = MigrationManifest(entries=[entry])
    classifier = MigrationClassifier(manifest, current_date="2026-09-11")

    finding = {
        "file": "scripts/fetch_real_datasets.py",
        "line": 10,
        "rule": "UNAUTHORIZED_OPENNEURO_DOWNLOAD",
        "severity": "critical",
        "category": "full_dataset_download",
    }
    classification, hidden, stale, unsafe = classifier.classify_finding(finding)

    assert classification.status == MigrationStatus.UNSAFE_BLOCKED
    assert classification.is_blocker is True
    assert unsafe is not None
    assert "Prohibited exception rule" in unsafe["reason"]
