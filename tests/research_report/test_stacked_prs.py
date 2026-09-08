from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"

# Modeled on the real stacked chain in this repo:
# #211 (cursor/streaming-performance-benchmarks, base main)
#   <- #215 (cursor/rss-memory-telemetry, base cursor/streaming-performance-benchmarks)
#     <- #224 (cursor/adaptive-streaming-budget, base cursor/rss-memory-telemetry)
#       <- #232 (cursor/streaming-checkpoints-replay-64cc, base cursor/adaptive-streaming-budget)


def _pr(number, branch, base_branch):
    return {
        "pr_number": number,
        "branch": branch,
        "base_branch": base_branch,
        "state": "open",
        "mergeable": True,
        "ci_status": "passed",
        "superseded_by_pr": None,
        "depends_on": [],
    }


def test_stacked_pr_chain_produces_ordered_layers_and_merge_order(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    _pr(211, "cursor/streaming-performance-benchmarks", "main"),
                    _pr(215, "cursor/rss-memory-telemetry", "cursor/streaming-performance-benchmarks"),
                    _pr(224, "cursor/adaptive-streaming-budget", "cursor/rss-memory-telemetry"),
                    _pr(232, "cursor/streaming-checkpoints-replay-64cc", "cursor/adaptive-streaming-budget"),
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    graph = report["dependency_and_stacking_graph"]
    assert graph["edges"]["215"] == [211]
    assert graph["edges"]["224"] == [215]
    assert graph["edges"]["232"] == [224]
    assert graph["edges"]["211"] == []
    assert graph["cycles"] == []
    assert graph["layers"] == [[211], [215], [224], [232]]

    # None of these are "merged" yet, so a dependent can only be recommended
    # once its base is no longer excluded -- here nothing is excluded, so
    # the whole stack is recommended in dependency order.
    assert report["recommended_merge_order"]["order"] == [211, 215, 224, 232]
    assert report["recommended_merge_order"]["excluded"] == {}


def test_stacked_pr_blocked_base_blocks_the_whole_stack(manifest_factory):
    prs = [
        _pr(211, "cursor/streaming-performance-benchmarks", "main"),
        _pr(215, "cursor/rss-memory-telemetry", "cursor/streaming-performance-benchmarks"),
    ]
    prs[0]["mergeable"] = False  # base of the stack is not mergeable

    manifest = manifest_factory({"reconciliation": {"pull_requests": prs}})
    report = compile_report(manifest, now=NOW)

    excluded = report["recommended_merge_order"]["excluded"]
    assert excluded["211"] == "not_mergeable"
    assert excluded["215"] == "blocked_on_dependency_211"
    assert report["recommended_merge_order"]["order"] == []
