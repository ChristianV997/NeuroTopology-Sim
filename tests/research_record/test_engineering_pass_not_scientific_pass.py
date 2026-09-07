"""Rule 5: never promote an engineering PASS to a scientific PASS."""
from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_all_tests_and_dashboard_passing_does_not_produce_a_scientific_pass(manifest_factory):
    manifest = manifest_factory(
        {
            "test_runner": {"jobs": [{"name": "unit_tests", "status": "passed", "passed": 500, "failed": 0, "skipped": 0}]},
            "dashboard_isolation": {"ok": True, "scanned_files": 10, "violations": [], "evidence": "clean"},
            "performance_benchmark": {"benchmarks": [{"name": "latency", "metric": "ms", "value": 1.0, "status": "pass"}]},
        }
    )

    record = compile_record(manifest, now=NOW)

    assert record["engineering_status"]["label"] == "clear"
    # No formal/empirical scientific evidence was supplied -- the verdict
    # must be NOT_APPLICABLE, never PASS, no matter how green CI is.
    assert record["scientific_verdict"] == "NOT_APPLICABLE"

    epi = record["epistemic_classification"]
    assert all(i["verdict"] is None for i in epi["confirmed_engineering_facts"])
    assert all(i["verdict"] is None for i in epi["benchmark_results"])


def test_proxy_and_synthetic_evidence_never_reaches_scientific_verdict(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-1", "claim_class": "synthetic", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "PASS"},
                    {"hypothesis_id": "HYP-2", "claim_class": "proxy", "data_mode": "empirical", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "PASS"},
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    # Both results are flagged as synthetic_pass_claim conflicts, so
    # neither counts as PASS-eligible evidence, and no eligible item exists.
    assert record["scientific_verdict"] == "NOT_APPLICABLE"
    assert len(record["conflicts"]) == 2


def test_formal_empirical_pass_does_reach_scientific_verdict(manifest_factory):
    manifest = manifest_factory(
        {"falsification": {"results": [{"hypothesis_id": "HYP-1", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 12.0, "verdict": "PASS"}]}}
    )

    record = compile_record(manifest, now=NOW)
    assert record["scientific_verdict"] == "PASS"


def test_a_scientific_fail_takes_precedence_over_a_pass(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-PASS", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 12.0, "verdict": "PASS"},
                    {"hypothesis_id": "HYP-FAIL", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 0.1, "verdict": "FAIL"},
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    assert record["scientific_verdict"] == "FAIL"
