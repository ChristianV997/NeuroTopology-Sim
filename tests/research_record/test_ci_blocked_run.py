from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_ci_blocked_run_is_engineering_blocked_not_scientific_blocked(manifest_factory):
    manifest = manifest_factory(
        {
            "test_runner": {"jobs": [{"name": "windows_runner", "status": "not_started", "block_reason": "infrastructure", "passed": None, "failed": None, "skipped": None}]},
            "reconciliation": {"pull_requests": [{"pr_number": 42, "branch": "b", "base_branch": "main", "merge_status": "open", "status_category": "CI_BLOCKED", "mergeable": None, "ci_status": "not_started"}]},
        }
    )

    record = compile_record(manifest, now=NOW)

    assert record["engineering_status"]["label"] == "blocked"
    assert record["engineering_status"]["infrastructure_blocked_jobs"] == ["windows_runner"]
    assert record["billing_runner_status"]["ci_blocked_prs"] == [42]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"
    # An infrastructure-blocked run must not be conflated with a scientific
    # validation problem.
    assert record["final_release_recommendation"] != "BLOCKED_BY_SCIENTIFIC_VALIDATION"
    assert record["scientific_verdict"] == "NOT_APPLICABLE"
