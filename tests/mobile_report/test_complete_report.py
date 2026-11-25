from __future__ import annotations

from tools.mobile_report.compiler import compile_report
from tools.mobile_report.render_csv import render_csv_tables
from tools.mobile_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def test_complete_report_all_sections_available(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {
                        "pr_number": 236,
                        "branch": "codex/integration-all-open-prs",
                        "base_branch": "main",
                        "merge_status": "open",
                        "status_category": "OPEN_REVIEW",
                        "is_draft": False,
                        "integration_status": "integrated_only",
                        "mergeable": True,
                        "ci_status": "passed",
                        "superseded_by_pr": None,
                        "changed_files": ["tools/mobile_report/compiler.py"],
                    }
                ]
            },
            "agent_contributions": {
                "repository": "https://github.com/ChristianV997/NeuroTopology-Sim",
                "baseline_commit": "be277ecdac301d49dca27ef9612ebe6c560245ad",
                "evidence_source": "github_api",
                "inventory_is_not_evidence": True,
                "required_warnings": ["Synthetic data cannot establish scientific PASS."],
                "contributions": [
                    {
                        "id": "nts-pr-236",
                        "title": "Integration: merge validated open PR groups",
                        "agent": "codex",
                        "branch": "codex/integration-all-open-prs",
                        "pr_number": 236,
                        "section": "OPEN",
                        "merge_status": "open",
                        "is_draft": False,
                        "changed_file_count": 138,
                        "additions": 18499,
                        "deletions": 1459,
                        "verification_status": {
                            "existence": "verified",
                            "merge_status": "verified",
                            "scientific_pass": "not_claimed",
                            "author_test_results": "unverified",
                            "implementation_report": "not_located",
                        },
                        "research_classification": {
                            "value_class": "engineering",
                            "claim_class": "none",
                            "data_mode": "none",
                            "empirical_pass_allowed": False,
                        },
                        "limitations": ["Integration branch only; not yet merged to main."],
                    }
                ],
            },
            "dashboard_isolation": {"ok": True, "scanned_files": 12, "violations": [], "evidence": "static AST import scan"},
            "test_runner": {"jobs": [{"name": "pytest_root", "status": "passed", "passed": 100, "failed": 0, "skipped": 2, "duration_s": 45.2}]},
            "performance_benchmark": {"benchmarks": [{"name": "pitnn_step", "metric": "latency", "value": 12.5, "unit": "ms", "status": "pass"}]},
            "memory_evidence": {"benchmarks": [{"name": "pitnn_rss", "metric": "rss", "value": 512.0, "unit": "MB", "status": "pass", "kind": "rss", "independently_verified": False}]},
            "dataset_provenance": {"datasets": [{"dataset_id": "ds005620", "data_mode": "empirical", "source": "OpenNeuro", "checksum": "abc123", "checksum_source": "local", "n_subjects": 12}]},
            "topology_validation": {"checks": [{"name": "global_efficiency_gate", "metric_family": "graph_beta_1", "data_mode": "empirical", "metric_value": 1.2, "verdict": "PASS"}]},
            "falsification": {"results": [{"hypothesis_id": "HYP-001", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 3.2, "verdict": "PASS"}]},
            "merge_gate": {"decisions": [{"pr_number": 236, "decision": "hold", "block_reason": None, "reason": "awaiting human review"}]},
        }
    )

    report = compile_report(manifest, now=NOW, repo="NeuroTopology-Sim", integration_ref="codex/integration-all-open-prs", integration_commit="be277ecdac301d49dca27ef9612ebe6c560245ad")

    assert report["status"] == "complete"
    assert all(v["available"] for v in report["completeness"].values())
    assert report["conflicts"] == []
    assert report["pr_state"]["by_merge_status"]["open"] == [236]
    assert report["recommended_merge_order"]["order"] == [236]
    assert report["final_release_recommendation"] == "READY_FOR_MERGE_REVIEW"

    falsification = report["falsification_status"]["results"][0]
    assert falsification["is_formal_bayes_factor"] is True

    markdown = render_markdown(report)
    assert "READY_FOR_MERGE_REVIEW" in markdown
    assert markdown.index("Recommendation") < markdown.index("## Agent Contribution Table")

    csv_tables = render_csv_tables(report)
    assert "236" in csv_tables["pr_state.csv"]
