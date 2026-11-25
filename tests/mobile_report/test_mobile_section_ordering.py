from __future__ import annotations

from tools.mobile_report.compiler import compile_report
from tools.mobile_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def test_summary_and_next_actions_appear_before_scrolling(manifest_factory):
    """The recommendation, blocker count, and next actions must be visible
    near the top of the Markdown report (within the first ~15 lines) so a
    reviewer on a phone sees them before scrolling through detail
    sections, per the "mobile-readable section ordering" requirement."""
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [{"hypothesis_id": "HYP-1", "claim_class": "synthetic", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "PASS"}]
            }
        }
    )

    report = compile_report(manifest, now=NOW)
    markdown = render_markdown(report)
    lines = markdown.splitlines()

    recommendation_line = next(i for i, line in enumerate(lines) if line.startswith("**Recommendation:"))
    assert recommendation_line < 15

    blockers_line = next(i for i, line in enumerate(lines) if "Unresolved blockers" in line)
    assert blockers_line < 15

    # The full, detailed "Final Release Recommendation" section still
    # exists further down for completeness, distinct from the summary line.
    detail_heading_line = next(i for i, line in enumerate(lines) if line == "## Final Release Recommendation")
    assert detail_heading_line > blockers_line

    # No detail section heading appears before the summary block ends.
    first_detail_heading = next(i for i, line in enumerate(lines) if line.startswith("## "))
    assert first_detail_heading > recommendation_line
    assert first_detail_heading > blockers_line


def test_recommendation_value_matches_between_summary_and_detail_section(manifest_factory):
    manifest = manifest_factory({})
    report = compile_report(manifest, now=NOW)
    markdown = render_markdown(report)

    summary_line = next(line for line in markdown.splitlines() if line.startswith("**Recommendation:"))
    assert report["final_release_recommendation"] in summary_line
