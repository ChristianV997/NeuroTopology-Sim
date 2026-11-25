from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_pr_retirement_retire_contradicts_open_reconciliation(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 100, "branch": "feature/a", "base_branch": "main", "state": "open", "mergeable": True, "ci_status": "passed", "superseded_by_pr": None}
                ]
            },
            "pr_retirement": {"decisions": [{"pr_number": 100, "action": "retire", "superseded_by": None, "reason": "looks stale"}]},
        }
    )

    report = compile_report(manifest, now=NOW)

    assert report["status"] == "complete"
    conflicts = report["unresolved_conflicts"]
    assert any(c["kind"] == "contradictory_pr_status" and c["pr_number"] == 100 for c in conflicts)
    assert report["final_release_recommendation"] == "hold_unresolved_conflicts"


def test_merge_gate_allow_contradicts_non_open_reconciliation(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 101, "branch": "feature/b", "base_branch": "main", "state": "closed", "mergeable": None, "ci_status": "unknown"}
                ]
            },
            "merge_gate": {"decisions": [{"pr_number": 101, "decision": "allow", "reason": "looks fine"}]},
        }
    )

    report = compile_report(manifest, now=NOW)

    conflicts = report["unresolved_conflicts"]
    assert any(c["kind"] == "contradictory_pr_status" and c["pr_number"] == 101 for c in conflicts)


def test_mismatched_superseded_by_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 216, "branch": "grok-bot/evidence-bundle-release", "base_branch": "main", "state": "open", "mergeable": True, "ci_status": "passed", "superseded_by_pr": None}
                ]
            },
            "pr_retirement": {"decisions": [{"pr_number": 216, "action": "superseded", "superseded_by": 225, "reason": "release-evidence-compilation supersedes this"}]},
        }
    )

    report = compile_report(manifest, now=NOW)

    conflicts = report["unresolved_conflicts"]
    assert any(c["kind"] == "contradictory_pr_status" and c["pr_number"] == 216 for c in conflicts)
