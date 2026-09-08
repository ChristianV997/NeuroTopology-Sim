from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_partial_record_when_most_inputs_missing(manifest_factory):
    manifest = manifest_factory(
        overrides={
            "reconciliation": {
                "pull_requests": [{"pr_number": 1, "branch": "feature/x", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]
            }
        },
        omit=["dataset_provenance", "falsification", "test_runner", "merge_gate", "cohort_readiness"],
    )

    record = compile_record(manifest, now=NOW)

    assert record["status"] == "partial"
    assert record["completeness"]["dataset_provenance"] == {"available": False, "error": "not_provided"}
    assert record["completeness"]["cohort_readiness"] == {"available": False, "error": "not_provided"}
    assert record["completeness"]["falsification"] == {"available": False, "error": "not_provided"}
    assert record["completeness"]["reconciliation"]["available"] is True
    assert record["final_release_recommendation"] == "INCOMPLETE_EVIDENCE"
    assert record["pr_buckets"]["open"] == [1]
    assert record["engineering_status"]["label"] == "unknown"
    assert record["scientific_status"]["label"] == "unknown"
