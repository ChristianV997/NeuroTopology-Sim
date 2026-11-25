"""Positive (non-conflicting) cases for the integration-only and
merged-to-main branch states -- the conflict/contradiction cases live in
test_open_pr_incorrectly_marked_merged.py."""
from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_integration_only_branch_is_not_reported_as_merged(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 211, "branch": "cursor/streaming-performance-benchmarks", "base_branch": "main", "merge_status": "open", "is_draft": False, "integration_status": "integrated_only", "mergeable": True, "ci_status": "passed"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)

    assert record["pr_buckets"]["integrated_only"] == [211]
    assert record["pr_buckets"]["merged"] == []
    assert record["conflicts"] == []
    integration_only_rows = [p for p in record["pr_state"]["pull_requests"] if p["integration_status"] == "integrated_only"]
    assert integration_only_rows[0]["merge_status"] == "open"


def test_merged_to_main_branch_is_a_clean_engineering_fact(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 218, "branch": "codex/integration-reconciliation", "base_branch": "main", "merge_status": "merged", "is_draft": False, "is_ancestor_of_target": True, "integration_status": "merged_to_main", "mergeable": True, "ci_status": "passed"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)

    assert record["pr_buckets"]["merged"] == [218]
    assert record["conflicts"] == []
    fact = next(i for i in record["epistemic_classification"]["items"] if i["source"] == "reconciliation" and i["id"] == "218")
    assert fact["label"] == "engineering fact"
