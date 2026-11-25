from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_status_category_duplicate_without_pointer_is_flagged(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 153, "branch": "duplicate/pr-153", "base_branch": "main", "merge_status": "open", "status_category": "DUPLICATE", "duplicate_of_pr": None, "mergeable": True, "ci_status": "passed"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    conflicts = [c for c in record["conflicts"] if c["kind"] == "duplicate_marked_without_pointer"]
    assert any(c["pr_number"] == 153 for c in conflicts)


def test_status_category_duplicate_with_pointer_is_a_clean_decision(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 153, "branch": "duplicate/pr-153", "base_branch": "main", "merge_status": "open", "status_category": "DUPLICATE", "duplicate_of_pr": 154, "mergeable": True, "ci_status": "passed"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    assert not [c for c in record["conflicts"] if c["kind"] == "duplicate_marked_without_pointer"]
    decisions = {d["pr_number"]: d for d in record["duplicate_superseded_decisions"]}
    assert decisions[153]["recommended_action"] == "close_as_duplicate_of_pr_154"


def test_two_active_prs_sharing_a_branch_is_a_duplicate_branch_conflict(manifest_factory):
    # Mirrors evidence_schema.yaml's no_duplicate_branches_in_compiled_report
    # hard rule: two active (non-superseded, non-blocked) entries sharing a
    # branch is a contradiction, not a coincidence.
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 141, "branch": "claude/consciousness-transitions-tests-ggx7ph", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"},
                    {"pr_number": 205, "branch": "claude/consciousness-transitions-tests-ggx7ph", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"},
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    conflicts = [c for c in record["conflicts"] if c["kind"] == "duplicate_branch"]
    assert {c["pr_number"] for c in conflicts} == {141, 205}


def test_superseded_pr_sharing_a_branch_is_not_a_duplicate_branch_conflict(manifest_factory):
    # A superseded entry is no longer "active", so a reused branch name
    # there is a known, benign situation (see the real docs/release
    # inventory's "reused Claude branch name" limitation notes) -- not a
    # fresh contradiction.
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 141, "branch": "claude/reused-lane", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed", "superseded_by_pr": 205},
                    {"pr_number": 205, "branch": "claude/reused-lane", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"},
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    conflicts = [c for c in record["conflicts"] if c["kind"] == "duplicate_branch"]
    assert conflicts == []
