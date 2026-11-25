from __future__ import annotations

from tools.research_report.compiler import compile_report
from tools.research_report.render_csv import render_csv_tables
from tools.research_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def test_complete_report_all_sections_available(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {
                        "pr_number": 218,
                        "branch": "claude/integration-reconciliation",
                        "base_branch": "main",
                        "state": "open",
                        "mergeable": True,
                        "ci_status": "passed",
                        "superseded_by_pr": None,
                        "depends_on": [],
                        "changed_files": ["tools/integration_reconciliation/report.py"],
                    }
                ]
            },
            "capability_snapshot": {"capabilities": [{"name": "mne_reader", "status": "available", "backend": "mne", "notes": None}]},
            "dataset_provenance": {
                "datasets": [{"dataset_id": "ds005620", "data_mode": "empirical", "source": "OpenNeuro", "license": "CC0", "checksum": "abc123", "n_subjects": 12}]
            },
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-001", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 3.2, "unit": None, "verdict": "PASS", "notes": None}
                ]
            },
            "performance_benchmark": {"benchmarks": [{"name": "pitnn_step", "metric": "latency", "value": 12.5, "unit": "ms", "baseline_value": 13.0, "regression_pct": -3.8, "status": "pass"}]},
            "memory_evidence": {"benchmarks": [{"name": "pitnn_rss", "metric": "rss", "value": 512.0, "unit": "MB", "baseline_value": 500.0, "regression_pct": 2.4, "status": "pass"}]},
            "interoperability": {"adapters": [{"name": "native_signal_adapter", "status": "supported", "contract_version": "1.0", "notes": None}]},
            "topology_validation": {"checks": [{"name": "global_efficiency_gate", "data_mode": "empirical", "Qabs": 1.2, "I_mean": 0.4, "verdict": "PASS", "notes": None}]},
            "test_runner": {"jobs": [{"name": "pytest_root", "status": "passed", "passed": 100, "failed": 0, "skipped": 2, "duration_s": 45.2}]},
            "merge_gate": {"decisions": [{"pr_number": 218, "decision": "allow", "reason": "read-only tool, no risk"}]},
            "pr_retirement": {"decisions": []},
        }
    )

    report = compile_report(manifest, now=NOW, repo="NeuroTopology-Sim", base_ref="main", base_commit="62637a4")

    assert report["status"] == "complete"
    assert all(v["available"] for v in report["completeness"].values())
    assert report["repository_and_baseline"] == {"repo": "NeuroTopology-Sim", "base_ref": "main", "base_commit": "62637a4"}
    assert report["pull_requests"]["by_state"]["open"] == [218]
    assert report["unresolved_conflicts"] == []
    assert report["recommended_merge_order"]["order"] == [218]
    assert report["final_release_recommendation"] == "proceed_with_recommended_merge_order"

    falsification = report["falsification_status"]["results"][0]
    assert falsification["is_formal_bayes_factor"] is True
    assert falsification["display_label"] == "Bayes factor"

    # Renders without raising, and carries the same key facts through.
    markdown = render_markdown(report)
    assert "proceed_with_recommended_merge_order" in markdown
    assert "218" in markdown

    csv_tables = render_csv_tables(report)
    assert "pull_requests.csv" in csv_tables
    assert "218" in csv_tables["pull_requests.csv"]
