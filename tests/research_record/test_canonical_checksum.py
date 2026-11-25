"""JSON requirement: deterministic canonical checksum."""
from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_checksum_is_a_64_char_hex_sha256(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    checksum = record["canonical_checksum"]
    assert isinstance(checksum, str)
    assert len(checksum) == 64
    int(checksum, 16)  # raises if not valid hex


def test_checksum_is_deterministic_for_identical_pinned_inputs(manifest_factory):
    manifest = manifest_factory({"reconciliation": {"pull_requests": [{"pr_number": 1, "branch": "a", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]}})
    record1 = compile_record(manifest, now=NOW)
    record2 = compile_record(manifest, now=NOW)
    assert record1["canonical_checksum"] == record2["canonical_checksum"]


def test_checksum_changes_when_content_changes(manifest_factory):
    # manifest_factory reuses the same tmp_path/filenames across calls, so
    # each manifest must be fully compiled before the next one overwrites
    # those files on disk.
    manifest_a = manifest_factory({"reconciliation": {"pull_requests": [{"pr_number": 1, "branch": "a", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]}})
    record_a = compile_record(manifest_a, now=NOW)

    manifest_b = manifest_factory({"reconciliation": {"pull_requests": [{"pr_number": 2, "branch": "b", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]}})
    record_b = compile_record(manifest_b, now=NOW)

    assert record_a["canonical_checksum"] != record_b["canonical_checksum"]


def test_checksum_field_itself_is_excluded_from_its_own_computation(manifest_factory):
    # Sanity: the checksum must be over the record's *other* content, not
    # a checksum-of-a-checksum tautology.
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    stripped = {k: v for k, v in record.items() if k != "canonical_checksum"}
    import hashlib
    import json

    expected = hashlib.sha256(json.dumps(stripped, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    assert record["canonical_checksum"] == expected
