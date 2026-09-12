"""Deterministic unit and contract test suite for Reviewed Exception Registry.

Validates:
- Strict schema enforcement (NeuroTopology.DataAccessReviewedException.v1).
- Rejection of wildcard, repository-wide, permanent, ownerless, or self-reviewed exceptions.
- Fail-closed behavior on expired or malformed records.
- Rejection of all forbidden unsafe behaviors:
  * full_dataset_download
  * unbounded_remote_read
  * missing_checksum
  * output_root_escape
  * network_enabled_default
  * fabricated_provenance
- Exact file, line, and symbol matching.
- Separation of concerns: exceptions NEVER suppress findings or grant compliance.
- Finite RFC 8259 JSON serialization (NaN and Infinity rejection).
- CLI execution and exit codes.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import shutil
import tempfile
import pytest

from tools.data_access.exception_registry import (
    EXCEPTION_REGISTRY_SCHEMA,
    FORBIDDEN_PERMITTED_BEHAVIORS,
    MAX_EXCEPTION_LIFESPAN_DAYS,
    REVIEWED_EXCEPTION_SCHEMA,
    ExceptionContractError,
    ExceptionRecordStatus,
    ExceptionRegistry,
    RejectionReasonCode,
    ReviewedExceptionRecord,
    canonical_hash,
    finite_value,
    validate_exception_record,
)
from scripts.validate_data_access_exceptions import main as cli_main


@pytest.fixture
def temp_dir():
    """Temporary workspace for testing exceptions."""
    d = tempfile.mkdtemp(prefix="test_exc_registry_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def valid_record_dict():
    """Fixture returning a canonical valid exception record dict."""
    return {
        "schema_version": REVIEWED_EXCEPTION_SCHEMA,
        "exception_id": "EXC-20260911-001",
        "exact_file": "dataset_acquisition/download_eeg.py",
        "exact_symbol": "download_file",
        "exact_line": 34,
        "rule_identifier": "unconstrained_download",
        "owner": "antigravity-a",
        "justification": "Temporary migration exemption while approved adapter is integrated.",
        "migration_issue": "GH-331",
        "created_date": "2026-09-11",
        "expiry_date": "2026-10-11",
        "reviewer": "codex-d",
        "permitted_behavior": [
            "legacy_script_execution_during_migration_window"
        ],
        "prohibited_behavior": [
            "full_dataset_download",
            "unbounded_remote_read",
            "missing_checksum",
            "output_root_escape",
            "network_enabled_default",
            "fabricated_provenance",
        ],
        "status": "ACTIVE",
    }


def test_valid_record_passes_validation(valid_record_dict):
    """A fully specified record within lifespan passes validation."""
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res = validate_exception_record(rec, as_of_date="2026-09-15")

    assert res.is_valid is True
    assert res.status == ExceptionRecordStatus.ACTIVE.value
    assert len(res.rejection_codes) == 0
    assert res.expires_in_days == 26


def test_expired_record_fails_closed(valid_record_dict):
    """An expired record must fail closed and report status EXPIRED."""
    valid_record_dict["expiry_date"] = "2026-09-10"
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res = validate_exception_record(rec, as_of_date="2026-09-12")

    assert res.is_valid is False
    assert res.status == ExceptionRecordStatus.EXPIRED.value
    assert RejectionReasonCode.EXPIRED.value in res.rejection_codes


def test_wildcard_file_rejected(valid_record_dict):
    """Wildcards in exact_file are strictly rejected."""
    for bad_file in ["*.py", "dataset_acquisition/*.py", "**/*.py", "tools/?/cache.py", "."]:
        valid_record_dict["exact_file"] = bad_file
        rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
        res = validate_exception_record(rec, as_of_date="2026-09-15")
        assert res.is_valid is False
        assert (
            RejectionReasonCode.WILDCARD_FILE.value in res.rejection_codes
            or RejectionReasonCode.REPOSITORY_WIDE_SCOPE.value in res.rejection_codes
        )


def test_wildcard_symbol_rejected(valid_record_dict):
    """Wildcards in exact_symbol are strictly rejected."""
    valid_record_dict["exact_symbol"] = "fetch_*"
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res = validate_exception_record(rec, as_of_date="2026-09-15")

    assert res.is_valid is False
    assert RejectionReasonCode.WILDCARD_SYMBOL.value in res.rejection_codes


def test_ownerless_and_wildcard_owner_rejected(valid_record_dict):
    """Missing or wildcard owner is rejected."""
    for bad_owner in ["", "all", "any", "nobody", "*", "unknown"]:
        valid_record_dict["owner"] = bad_owner
        rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
        res = validate_exception_record(rec, as_of_date="2026-09-15")
        assert res.is_valid is False
        assert RejectionReasonCode.OWNERLESS.value in res.rejection_codes


def test_self_review_prohibited(valid_record_dict):
    """Owner cannot review their own exception."""
    valid_record_dict["owner"] = "antigravity-a"
    valid_record_dict["reviewer"] = "antigravity-a"
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res = validate_exception_record(rec, as_of_date="2026-09-15")

    assert res.is_valid is False
    assert RejectionReasonCode.SELF_REVIEW_PROHIBITED.value in res.rejection_codes


def test_permanent_exception_rejected(valid_record_dict):
    """Permanent or excessive lifespan exceptions are strictly rejected."""
    # 1. Invalid / permanent string
    valid_record_dict["expiry_date"] = "never"
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res = validate_exception_record(rec, as_of_date="2026-09-15")
    assert res.is_valid is False
    assert RejectionReasonCode.PERMANENT_EXCEPTION.value in res.rejection_codes

    # 2. Excessive lifespan (> 90 days)
    valid_record_dict["created_date"] = "2026-09-11"
    valid_record_dict["expiry_date"] = "2027-01-01"  # 112 days
    rec2 = ReviewedExceptionRecord.from_dict(valid_record_dict)
    res2 = validate_exception_record(rec2, as_of_date="2026-09-15")
    assert res2.is_valid is False
    assert RejectionReasonCode.EXCESSIVE_LIFESPAN.value in res2.rejection_codes


def test_missing_migration_issue_rejected(valid_record_dict):
    """Missing or unformatted migration issue is rejected."""
    for bad_issue in ["", "none", "todo", "someday"]:
        valid_record_dict["migration_issue"] = bad_issue
        rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
        res = validate_exception_record(rec, as_of_date="2026-09-15")
        assert res.is_valid is False
        assert (
            RejectionReasonCode.MISSING_MIGRATION_ISSUE.value in res.rejection_codes
            or RejectionReasonCode.INVALID_MIGRATION_ISSUE.value in res.rejection_codes
        )


def test_forbidden_unsafe_behaviors_rejected(valid_record_dict):
    """Exceptions attempting to permit forbidden behaviors MUST fail validation."""
    forbidden_examples = [
        "full_dataset_download",
        "unbounded_remote_read",
        "missing_checksum",
        "output_root_escape",
        "network_enabled_default",
        "fabricated_provenance",
        "allow_bulk_dataset_fetch",
        "unbounded_stream_read",
        "skip_checksum_verification",
    ]

    for forbidden in forbidden_examples:
        valid_record_dict["permitted_behavior"] = [forbidden]
        rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
        res = validate_exception_record(rec, as_of_date="2026-09-15")
        assert res.is_valid is False
        assert res.status == ExceptionRecordStatus.UNSAFE_REJECTED.value
        assert RejectionReasonCode.UNSAFE_BEHAVIOR_PERMITTED.value in res.rejection_codes


def test_malformed_records_fail_closed(temp_dir):
    """Corrupted files or missing schema fail closed."""
    corrupt_file = temp_dir / "corrupted.json"
    corrupt_file.write_text("{ unclosed json", encoding="utf-8")

    registry = ExceptionRegistry(exceptions_dir=temp_dir)
    report = registry.load_from_directory(temp_dir)

    assert report.total_records == 1
    assert report.valid_active_count == 0
    assert report.rejected_count == 1
    assert report.records[0]["status"] == ExceptionRecordStatus.MALFORMED.value


def test_exact_location_matching(valid_record_dict):
    """Registry matches by exact line and symbol, but never across mismatched locations."""
    registry = ExceptionRegistry()
    rec = ReviewedExceptionRecord.from_dict(valid_record_dict)
    registry.register_record(rec, as_of_date="2026-09-15")

    # Match by exact file + exact line + rule
    match1 = registry.match_finding(
        file="dataset_acquisition/download_eeg.py",
        line=34,
        symbol=None,
        rule="unconstrained_download",
    )
    assert match1.matched is True
    assert match1.exception_id == "EXC-20260911-001"

    # Match by exact file + exact symbol + rule
    match2 = registry.match_finding(
        file="dataset_acquisition/download_eeg.py",
        line=999,  # Different line, but matching symbol
        symbol="download_file",
        rule="unconstrained_download",
    )
    assert match2.matched is True

    # No match for different rule
    match3 = registry.match_finding(
        file="dataset_acquisition/download_eeg.py",
        line=34,
        symbol="download_file",
        rule="other_rule",
    )
    assert match3.matched is False

    # No match for different file
    match4 = registry.match_finding(
        file="scripts/other_file.py",
        line=34,
        symbol="download_file",
        rule="unconstrained_download",
    )
    assert match4.matched is False


def test_registry_never_declares_repository_compliance(temp_dir, valid_record_dict):
    """CRITICAL INVARIANT: Exceptions do NOT declare compliance."""
    exc_file = temp_dir / "EXC-001.json"
    exc_file.write_text(json.dumps(valid_record_dict), encoding="utf-8")

    registry = ExceptionRegistry(exceptions_dir=temp_dir)
    report = registry.load_from_directory(temp_dir, as_of_date="2026-09-15")

    # Compliance is strictly False!
    assert report.repository_compliant is False
    assert report.compliance_declaration == "NON_COMPLIANT_WITH_EXCEPTIONS"
    assert report.findings_suppressed_count == 0
    assert report.valid_active_count == 1


def test_rfc8259_finite_json_rejection():
    """finite_value must reject non-finite floats."""
    with pytest.raises(ExceptionContractError):
        finite_value({"field": float("nan")})

    with pytest.raises(ExceptionContractError):
        finite_value({"field": float("inf")})

    with pytest.raises(ExceptionContractError):
        finite_value({"field": float("-inf")})


def test_cli_execution_and_markdown(temp_dir, valid_record_dict, capsys):
    """Test CLI execution producing JSON and Markdown reports."""
    exc_file = temp_dir / "EXC-001.json"
    exc_file.write_text(json.dumps(valid_record_dict), encoding="utf-8")

    # 1. Markdown format
    exit_code_md = cli_main([
        "--exceptions-dir", str(temp_dir),
        "--as-of-date", "2026-09-15",
        "--format", "markdown",
    ])
    captured_md = capsys.readouterr()
    assert exit_code_md == 0
    assert "Data-Access Reviewed Exceptions Audit" in captured_md.out
    assert "EXC-20260911-001" in captured_md.out

    # 2. JSON format with output file
    json_out_file = temp_dir / "audit.json"
    exit_code_json = cli_main([
        "--exceptions-dir", str(temp_dir),
        "--as-of-date", "2026-09-15",
        "--format", "json",
        "--output", str(json_out_file),
    ])
    assert exit_code_json == 0
    assert json_out_file.is_file()
    data = json.loads(json_out_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == EXCEPTION_REGISTRY_SCHEMA
    assert data["valid_active_count"] == 1
    assert data["repository_compliant"] is False

    # 3. Strict fail on expired exception
    valid_record_dict["expiry_date"] = "2026-09-10"
    exc_file.write_text(json.dumps(valid_record_dict), encoding="utf-8")
    exit_code_expired = cli_main([
        "--exceptions-dir", str(temp_dir),
        "--as-of-date", "2026-09-15",
        "--strict",
    ])
    assert exit_code_expired == 1
