from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_test_runner_section_is_explicit(manifest_factory):
    manifest = manifest_factory(omit=["test_runner"])

    report = compile_report(manifest, now=NOW)

    ci = report["ci_and_infrastructure_status"]
    assert ci["test_runner"]["available"] is False
    assert ci["test_runner"]["error"] == "not_provided"
    assert ci["test_runner"]["jobs"] == []


def test_job_that_has_not_started_is_never_counted_as_passed(manifest_factory):
    manifest = manifest_factory(
        {
            "test_runner": {
                "jobs": [
                    {"name": "unit_tests", "status": "passed", "passed": 10, "failed": 0, "skipped": 0, "duration_s": 5.0},
                    {"name": "integration_tests", "status": "not_started", "passed": None, "failed": None, "skipped": None, "duration_s": None},
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)
    counts = report["ci_and_infrastructure_status"]["test_runner"]["counts_by_status"]
    assert counts["passed"] == 1
    assert counts["not_started"] == 1
    jobs_by_name = {j["name"]: j for j in report["ci_and_infrastructure_status"]["test_runner"]["jobs"]}
    assert jobs_by_name["integration_tests"]["status"] == "not_started"
    assert jobs_by_name["integration_tests"]["passed"] is None


def test_pr_missing_ci_status_is_unknown_not_passed(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [{"pr_number": 5, "branch": "feature/no-ci", "base_branch": "main", "state": "open", "mergeable": True}]
            }
        }
    )

    report = compile_report(manifest, now=NOW)
    pr = report["pull_requests"]["pull_requests"][0]
    assert pr["ci_status"] == "unknown"
    counts = report["ci_and_infrastructure_status"]["pr_ci_status_counts"]
    assert counts["unknown"] == 1
    assert counts["passed"] == 0
