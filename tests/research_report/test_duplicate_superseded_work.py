from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_superseded_pr_excluded_from_merge_order(manifest_factory):
    # Modeled on the real #216 (evidence-bundle-release) vs #225
    # (release-evidence-compilation "superseding #216 inventory").
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {
                        "pr_number": 216,
                        "branch": "grok-bot/evidence-bundle-release",
                        "base_branch": "main",
                        "state": "open",
                        "mergeable": True,
                        "ci_status": "passed",
                        "superseded_by_pr": 225,
                        "changed_files": ["tools/evidence_bundle/compile.py"],
                    },
                    {
                        "pr_number": 225,
                        "branch": "cursor/release-evidence-compilation-9077",
                        "base_branch": "main",
                        "state": "open",
                        "mergeable": True,
                        "ci_status": "passed",
                        "superseded_by_pr": None,
                        "changed_files": ["tools/evidence_bundle/compile.py"],
                    },
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    excluded = report["recommended_merge_order"]["excluded"]
    assert excluded["216"] == "superseded_by_pr_225"
    assert report["recommended_merge_order"]["order"] == [225]

    # Both PRs touch the same file: duplicate/overlapping ownership must be
    # surfaced as an unresolved conflict, not silently merged.
    conflicts = report["unresolved_conflicts"]
    duplicate_conflicts = [c for c in conflicts if c["kind"] == "duplicate_ownership"]
    assert len(duplicate_conflicts) == 1
    assert duplicate_conflicts[0]["pr_numbers"] == [216, 225]
    assert duplicate_conflicts[0]["path"] == "tools/evidence_bundle/compile.py"
