"""Tests for migration entry validation rules and fail-closed security invariants."""

from __future__ import annotations

import pytest

from tools.data_access.migration_gate.types import (
    PROHIBITED_EXCEPTION_RULES,
    MigrationEntry,
    MigrationStatus,
)
from tools.data_access.migration_gate.validator import (
    is_permanent_expiration,
    is_prohibited_exception_rule,
    is_stale_expiration,
    is_wildcard_string,
    validate_migration_entry,
)


def test_valid_unmigrated_entry():
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #235",
        status=MigrationStatus.UNMIGRATED,
    )
    result = validate_migration_entry(entry)
    assert result.is_valid is True
    assert result.status == MigrationStatus.UNMIGRATED
    assert len(result.errors) == 0


def test_valid_temporary_exception():
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@christianv",
        migration_reference="PR #235",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="lead-reviewer",
        expires_at="2027-01-01",
        justification="Legitimate transition period",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is True
    assert result.status == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION
    assert len(result.errors) == 0


def test_reject_missing_required_fields():
    # Empty file, owner, ref
    entry = MigrationEntry(
        file="",
        symbol_or_line="",
        rule="",
        owner="",
        migration_reference="",
        status=MigrationStatus.UNMIGRATED,
    )
    result = validate_migration_entry(entry)
    assert result.is_valid is False
    assert result.status == MigrationStatus.UNABLE_TO_ASSESS
    assert any("file" in err for err in result.errors)
    assert any("symbol_or_line" in err for err in result.errors)
    assert any("rule" in err for err in result.errors)
    assert any("owner" in err for err in result.errors)
    assert any("migration_reference" in err for err in result.errors)


@pytest.mark.parametrize("wildcard", ["*", "?", "scripts/*", "data/**/adapter.py", "test[1-3]"])
def test_reject_wildcards_in_file(wildcard):
    assert is_wildcard_string(wildcard) is True
    entry = MigrationEntry(
        file=wildcard,
        symbol_or_line="10",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@dev",
        migration_reference="RFC-01",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="rev",
        expires_at="2027-01-01",
        justification="test",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is False
    assert result.is_wildcard is True
    assert result.status == MigrationStatus.UNSAFE_BLOCKED
    assert any("Wildcard in 'file'" in err for err in result.errors)


@pytest.mark.parametrize("permanent_token", ["permanent", "never", "none", "null", "infinite", "forever", "unlimited"])
def test_reject_permanent_exceptions(permanent_token):
    assert is_permanent_expiration(permanent_token) is True
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@dev",
        migration_reference="RFC-01",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="rev",
        expires_at=permanent_token,
        justification="test",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is False
    assert result.is_permanent is True
    assert result.status == MigrationStatus.UNSAFE_BLOCKED
    assert any("Permanent or unbounded exceptions are strictly prohibited" in err for err in result.errors)


def test_reject_stale_exceptions():
    assert is_stale_expiration("2025-01-01", current_date="2026-09-11") is True
    assert is_stale_expiration("2027-01-01", current_date="2026-09-11") is False

    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@dev",
        migration_reference="RFC-01",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="rev",
        expires_at="2025-01-01",
        justification="test",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is False
    assert result.is_stale is True
    assert result.status == MigrationStatus.UNSAFE_BLOCKED
    assert any("stale exceptions are rejected" in err for err in result.errors)


@pytest.mark.parametrize(
    "prohibited_rule",
    [
        "UNAUTHORIZED_OPENNEURO_DOWNLOAD",
        "UNAUTHORIZED_AWS_FULL_TRANSFER",
        "UNAUTHORIZED_SHELL_TRANSFER",
        "UNAUTHORIZED_BOTO3_FULL_OBJECT",
        "UNBOUNDED_REMOTE_MATERIALIZATION",
        "MISSING_CACHE_BOUND",
        "MISSING_CHECKSUM",
        "OUTPUT_ROOT_ESCAPE",
        "NETWORK_ENABLED_BY_DEFAULT",
        "POLICY_READ_FAILURE",
        "POLICY_PARSE_FAILURE",
    ],
)
def test_reject_prohibited_rules_for_exceptions(prohibited_rule):
    is_prohibited, msg = is_prohibited_exception_rule(prohibited_rule)
    assert is_prohibited is True

    entry = MigrationEntry(
        file="scripts/data_runner.py",
        symbol_or_line="10",
        rule=prohibited_rule,
        owner="@dev",
        migration_reference="RFC-PROHIBITED",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="lenient-rev",
        expires_at="2027-01-01",
        justification="Attempted prohibited exception",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is False
    assert result.is_prohibited_exception is True
    assert result.status == MigrationStatus.UNSAFE_BLOCKED
    assert any("Prohibited exception rule" in err for err in result.errors)


def test_reviewed_exception_requires_reviewer_and_justification():
    entry = MigrationEntry(
        file="scripts/fetch_real_datasets.py",
        symbol_or_line="45",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@dev",
        migration_reference="RFC-01",
        status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
        reviewer="",
        expires_at="2027-01-01",
        justification="",
    )
    result = validate_migration_entry(entry, current_date="2026-09-11")
    assert result.is_valid is False
    assert any("requires a named 'reviewer'" in err for err in result.errors)
    assert any("requires a non-empty 'justification'" in err for err in result.errors)


def test_not_applicable_requires_justification():
    entry = MigrationEntry(
        file="scripts/test_helper.py",
        symbol_or_line="1",
        rule="UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL",
        owner="@dev",
        migration_reference="RFC-01",
        status=MigrationStatus.NOT_APPLICABLE,
        justification="",
    )
    result = validate_migration_entry(entry)
    assert result.is_valid is False
    assert any("requires a non-empty 'justification'" in err for err in result.errors)
