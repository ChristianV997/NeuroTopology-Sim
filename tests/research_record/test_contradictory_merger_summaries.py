from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_reconciliation_and_agent_contributions_disagree_on_merge_status(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 216, "branch": "grok-bot/evidence-bundle-release", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}
                ]
            },
            "agent_contributions": {
                "repository": None,
                "baseline_commit": None,
                "evidence_source": "github_api",
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [
                    {
                        "id": "nts-pr-216",
                        "agent": "grok-bot",
                        "branch": "grok-bot/evidence-bundle-release",
                        "pr_number": 216,
                        "merge_status": "merged",
                        "verification_status": {},
                        "research_classification": {},
                        "limitations": [],
                    }
                ],
            },
        }
    )

    record = compile_record(manifest, now=NOW)

    conflicts = [c for c in record["conflicts"] if c["kind"] == "conflicting_merger_summary"]
    assert len(conflicts) == 1
    assert conflicts[0]["pr_number"] == 216
    assert "open" in conflicts[0]["detail"] and "merged" in conflicts[0]["detail"]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"
