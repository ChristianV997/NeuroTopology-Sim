"""Fail-closed snapshot, path, label, and duplicate-ownership tests."""

from __future__ import annotations

import json
import math

import pytest
import yaml

from tools.retrofit_inventory.models import (
    ARTIFACT_LABEL_EMPIRICAL,
    ARTIFACT_LABEL_SYNTHETIC,
    ARTIFACT_LABEL_UNKNOWN,
    KIND_TEXT,
    OverlapOrDuplicateFinding,
)
from tools.retrofit_inventory.validators import (
    FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES,
    INVENTORY_CLAIM_STATUS_NOT_EVIDENCE,
    empirical_label_is_scientific_pass,
    inventory_claim_record,
    inventory_is_scientific_evidence,
    inventory_scientific_claim_status,
    validate_artifact_entry,
    validate_duplicate_ownership,
    validate_file_entry,
    validate_finite_numeric_fields,
    validate_inventory_snapshot,
    validate_inventory_snapshot_or_raise,
    validate_no_scientific_pass,
    validate_path_safety,
)

from .conftest import FIXTURES, make_artifact, make_file_entry, make_snapshot


def test_valid_snapshot_has_no_errors():
    errors = validate_inventory_snapshot(make_snapshot(), scan_text_contents=False)
    assert errors == []


def test_missing_required_file_fields_are_errors():
    errors = validate_file_entry({"kind": KIND_TEXT, "size": 1}, index=0)
    assert any("missing required field: path" in item for item in errors)
    assert any("content_hash" in item for item in errors)


def test_missing_snapshot_commit_sha_is_error():
    snapshot = make_snapshot(commit_sha="")
    errors = validate_inventory_snapshot(snapshot, scan_text_contents=False)
    assert any("commit_sha" in item for item in errors)


def test_size_rejects_negative_nan_and_inf():
    row = {"size": -1, "mtime": math.nan}
    errors = validate_finite_numeric_fields(row, prefix="files[0]")
    assert any("size" in item for item in errors)
    assert any("mtime" in item for item in errors)

    row_inf = {"size": 1, "mtime": math.inf}
    assert any(
        "mtime" in item
        for item in validate_finite_numeric_fields(row_inf, prefix="files[0]")
    )


def test_bool_size_is_rejected():
    entry = make_file_entry()
    entry.size = True  # type: ignore[assignment]
    errors = validate_file_entry(entry, index=0)
    assert any("size" in item for item in errors)


def test_path_safety_rejects_absolute_dotdot_and_null():
    assert validate_path_safety("/etc/passwd", prefix="files[0]")
    assert validate_path_safety("../escape.py", prefix="files[0]")
    assert validate_path_safety("foo/../../etc/passwd", prefix="files[0]")
    assert validate_path_safety("foo\x00bar.py", prefix="files[0]")
    assert validate_path_safety("src/app.py", prefix="files[0]") == []


def test_snapshot_rejects_unsafe_file_path():
    snapshot = make_snapshot(files=[make_file_entry(path="../../secret.txt")])
    errors = validate_inventory_snapshot(snapshot, scan_text_contents=False)
    assert any("traversal" in item or ".." in item for item in errors)


def test_allowed_artifact_labels_only():
    for label in (
        ARTIFACT_LABEL_SYNTHETIC,
        ARTIFACT_LABEL_EMPIRICAL,
        ARTIFACT_LABEL_UNKNOWN,
    ):
        errors = validate_artifact_entry(make_artifact(label=label), index=0)
        assert errors == []


def test_malformed_artifact_bad_label_and_schema_id():
    payload = json.loads(
        (FIXTURES / "malformed" / "artifact_bad_label.json").read_text(encoding="utf-8")
    )
    errors = validate_artifact_entry(payload, index=0)
    assert any("label" in item for item in errors)
    assert any("schema_id" in item for item in errors)


def test_malformed_artifact_missing_path():
    errors = validate_artifact_entry(
        {"label": ARTIFACT_LABEL_SYNTHETIC, "schema_id": "x"},
        index=0,
    )
    assert any("path" in item for item in errors)


def test_empirical_label_is_never_scientific_pass():
    assert empirical_label_is_scientific_pass(ARTIFACT_LABEL_EMPIRICAL) is False
    snapshot = make_snapshot(
        artifacts=[make_artifact(path="artifacts/empirical/x.json", label=ARTIFACT_LABEL_EMPIRICAL)]
    )
    assert inventory_scientific_claim_status(snapshot) == INVENTORY_CLAIM_STATUS_NOT_EVIDENCE
    assert inventory_scientific_claim_status(snapshot) not in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES
    assert inventory_is_scientific_evidence(snapshot) is False
    record = inventory_claim_record(snapshot)
    assert record["scientific_claim_status"] != "PASS"
    assert record["inventory_is_evidence"] is False
    assert validate_no_scientific_pass(snapshot) == []


def test_report_fields_pass_is_rejected():
    snapshot = make_snapshot(report_fields={"verdict": "PASS"})
    errors = validate_inventory_snapshot(snapshot, scan_text_contents=False)
    assert any("PASS" in item for item in errors)


def test_duplicate_file_paths_are_errors_not_warnings():
    snapshot = make_snapshot(
        files=[make_file_entry("src/a.py"), make_file_entry("src/a.py")]
    )
    errors = validate_duplicate_ownership(snapshot)
    assert any("duplicate ownership" in item and "src/a.py" in item for item in errors)
    assert not any("warning" in item.lower() for item in errors)


def test_duplicate_paths_in_overlap_finding_are_errors():
    snapshot = make_snapshot(
        overlaps=[
            OverlapOrDuplicateFinding(
                paths=["tools/a.py", "tools/a.py"],
                reason="same basename",
            )
        ]
    )
    errors = validate_inventory_snapshot(snapshot, scan_text_contents=False)
    assert any("duplicate path" in item for item in errors)


def test_overlapping_claimed_owners_are_errors():
    snapshot = make_snapshot(
        report_fields={
            "claimed_owners": [
                {"path": "src/app.py", "owner": "lead"},
                {"path": "src/app.py", "owner": "research"},
            ]
        }
    )
    errors = validate_duplicate_ownership(snapshot)
    assert any("overlapping claimed owners" in item for item in errors)


def test_or_raise_raises_value_error():
    snapshot = make_snapshot(files=[make_file_entry(path="/abs/escape.py")])
    with pytest.raises(ValueError, match="failed validation"):
        validate_inventory_snapshot_or_raise(snapshot, scan_text_contents=False)


def test_malformed_yaml_snippet_is_not_a_valid_tool_row():
    raw = yaml.safe_load(
        (FIXTURES / "malformed" / "tool_row_missing_keys.yaml").read_text(encoding="utf-8")
    )
    from tools.retrofit_inventory.validators import validate_tool_source_row

    errors = validate_tool_source_row(raw)
    assert errors, "incomplete YAML snippet must fail closed"
    assert any("missing required field" in item for item in errors)
