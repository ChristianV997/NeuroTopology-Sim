from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_failed_ci_job_blocks_release_recommendation(manifest_factory):
    manifest = manifest_factory(
        {"test_runner": {"jobs": [{"name": "pytest_root", "status": "failed", "passed": 90, "failed": 10, "skipped": 0, "duration_s": 30.0}]}}
    )

    record = compile_record(manifest, now=NOW)

    assert record["ci_status"]["test_runner"]["counts_by_status"]["failed"] == 1
    assert record["test_totals"]["failed"] == 10
    assert record["failures"]["failed_jobs"] == ["pytest_root"]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"
    assert record["engineering_status"]["label"] == "blocked"


def test_billing_blocked_job_marked_passed_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"test_runner": {"jobs": [{"name": "ci_billing_job", "status": "passed", "block_reason": "billing", "passed": 5, "failed": 0, "skipped": 0}]}}
    )

    record = compile_record(manifest, now=NOW)

    conflicts = [c for c in record["conflicts"] if c["kind"] == "billing_not_pass"]
    assert any(c["id"] == "ci_billing_job" for c in conflicts)
    # Billing is an infrastructure/engineering concern, not a scientific
    # one -- it must not be routed to BLOCKED_BY_SCIENTIFIC_VALIDATION.
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"


def test_pr_ci_blocked_status_category_surfaces_in_billing_runner_status(manifest_factory):
    manifest = manifest_factory(
        {"reconciliation": {"pull_requests": [{"pr_number": 7, "branch": "b", "base_branch": "main", "merge_status": "open", "status_category": "CI_BLOCKED", "mergeable": None, "ci_status": "not_started"}]}}
    )

    record = compile_record(manifest, now=NOW)
    assert record["billing_runner_status"]["ci_blocked_prs"] == [7]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"
