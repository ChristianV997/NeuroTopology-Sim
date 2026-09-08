from __future__ import annotations

from tools.mobile_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_partial_report_when_most_inputs_missing(manifest_factory):
    manifest = manifest_factory(
        overrides={
            "reconciliation": {
                "pull_requests": [{"pr_number": 1, "branch": "feature/x", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]
            }
        },
        omit=["dataset_provenance", "falsification", "test_runner", "merge_gate"],
    )

    report = compile_report(manifest, now=NOW)

    assert report["status"] == "partial"
    assert report["completeness"]["dataset_provenance"] == {"available": False, "error": "not_provided"}
    assert report["completeness"]["falsification"] == {"available": False, "error": "not_provided"}
    assert report["completeness"]["reconciliation"]["available"] is True
    assert report["final_release_recommendation"] == "INCOMPLETE_EVIDENCE"
    assert report["pr_state"]["by_merge_status"]["open"] == [1]
