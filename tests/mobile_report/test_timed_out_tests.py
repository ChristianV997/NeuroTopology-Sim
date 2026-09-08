from __future__ import annotations

from tools.mobile_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_timed_out_job_is_distinct_from_failed_and_not_started(manifest_factory):
    manifest = manifest_factory(
        {
            "test_runner": {
                "jobs": [
                    {"name": "unit_tests", "status": "passed", "passed": 10, "failed": 0, "skipped": 0},
                    {"name": "slow_integration_tests", "status": "timed_out", "passed": None, "failed": None, "skipped": None},
                    {"name": "not_yet_run", "status": "not_started", "passed": None, "failed": None, "skipped": None},
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    counts = report["ci_status"]["test_runner"]["counts_by_status"]
    assert counts["passed"] == 1
    assert counts["timed_out"] == 1
    assert counts["not_started"] == 1
    assert counts["failed"] == 0

    assert report["timeouts"]["test_jobs"] == ["slow_integration_tests"]
    assert report["final_release_recommendation"] == "BLOCKED_BY_CI"


def test_pr_ci_status_timed_out_is_tracked_separately_from_failed(manifest_factory):
    manifest = manifest_factory(
        {"reconciliation": {"pull_requests": [{"pr_number": 3, "branch": "b", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "timed_out"}]}}
    )

    report = compile_report(manifest, now=NOW)
    counts = report["ci_status"]["pr_ci_status_counts"]
    assert counts["timed_out"] == 1
    assert counts["failed"] == 0
