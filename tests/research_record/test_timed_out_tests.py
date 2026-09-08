from __future__ import annotations

from tools.research_record.compiler import compile_record

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

    record = compile_record(manifest, now=NOW)

    counts = record["ci_status"]["test_runner"]["counts_by_status"]
    assert counts["passed"] == 1
    assert counts["timed_out"] == 1
    assert counts["not_started"] == 1
    assert counts["failed"] == 0

    assert record["timeouts"]["test_jobs"] == ["slow_integration_tests"]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"


def test_scientific_check_timeout_is_not_a_pass_fail_and_routes_to_engineering_status(manifest_factory):
    manifest = manifest_factory(
        {"topology_validation": {"checks": [{"name": "beta1_gate", "metric_family": "graph_beta_1", "data_mode": "empirical", "metric_value": None, "verdict": "TIMEOUT"}]}}
    )

    record = compile_record(manifest, now=NOW)

    check = record["topology_readiness"]["checks"][0]
    assert check["verdict"] == "TIMEOUT"
    counts = record["scientific_status"]["topology_family_verdict_counts"]["graph_beta_1"]
    assert counts["TIMEOUT"] == 1
    assert counts["PASS"] == 0
    assert counts["FAIL"] == 0

    assert record["timeouts"]["scientific_checks"] == ["beta1_gate"]
    assert record["engineering_status"]["scientific_check_timeouts"] == ["beta1_gate"]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"
    # A timeout is an engineering concern (rule 8/12), not a scientific-
    # validation failure.
    assert "BLOCKED_BY_SCIENTIFIC_VALIDATION" != record["final_release_recommendation"]
