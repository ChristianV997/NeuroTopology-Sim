from __future__ import annotations

from tools.mobile_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_draft_pr_recorded_as_merged_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 210, "branch": "feature/draft-thing", "base_branch": "main", "merge_status": "merged", "is_draft": True, "mergeable": None, "ci_status": "unknown"}
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    conflicts = [c for c in report["conflicts"] if c["kind"] == "open_pr_represented_as_merged"]
    assert any(c["pr_number"] == 210 and "draft" in c["detail"] for c in conflicts)


def test_integration_only_pr_recorded_as_merged_is_a_conflict(manifest_factory):
    # Modeled on the real situation: PR #236 (codex/integration-all-open-prs)
    # bundles many PRs' content into one integration branch. Being present
    # there is not the same claim as being merged to main.
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {
                        "pr_number": 211,
                        "branch": "cursor/streaming-performance-benchmarks",
                        "base_branch": "main",
                        "merge_status": "merged",
                        "is_draft": False,
                        "integration_status": "integrated_only",
                        "mergeable": True,
                        "ci_status": "passed",
                    }
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    conflicts = [c for c in report["conflicts"] if c["kind"] == "open_pr_represented_as_merged"]
    assert any(c["pr_number"] == 211 and "integration" in c["detail"] for c in conflicts)


def test_open_pr_correctly_recorded_as_open_is_not_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"reconciliation": {"pull_requests": [{"pr_number": 212, "branch": "b", "base_branch": "main", "merge_status": "open", "is_draft": False, "mergeable": True, "ci_status": "passed"}]}}
    )

    report = compile_report(manifest, now=NOW)
    assert not [c for c in report["conflicts"] if c["kind"] == "open_pr_represented_as_merged"]
