"""Requirement 2/3: one self-contained Markdown report, readable on a
mobile device without opening multiple files."""
from __future__ import annotations

from tools.research_record.compiler import compile_record
from tools.research_record.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"

_REQUIRED_HEADINGS = [
    "## Execution Timestamp and Source Commits",
    "## Repository and Branch State",
    "## Merged-to-Main Work",
    "## Integration-Only Work",
    "## Open PRs",
    "## Duplicate / Superseded Decisions",
    "## Billing / Runner Status",
    "## Memory Evidence",
    "## Provenance",
    "## Topology Readiness",
    "## Scientific Falsification Status",
    "## Confirmed Engineering Facts",
    "## Benchmark Results",
    "## Hypotheses",
    "## Speculation",
    "## Unsupported Claims",
    "## Final Conclusions",
    "## Next Priorities",
]


def test_markdown_is_a_single_self_contained_document_with_all_required_sections(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    markdown = render_markdown(record)

    for heading in _REQUIRED_HEADINGS:
        assert heading in markdown, f"missing section: {heading}"


def test_summary_block_is_readable_before_scrolling(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    markdown = render_markdown(record)
    lines = markdown.splitlines()

    recommendation_line = next(i for i, line in enumerate(lines) if line.startswith("**Recommendation:"))
    assert recommendation_line < 10

    scientific_caveat_line = next(i for i, line in enumerate(lines) if "does not itself constitute" in line)
    assert scientific_caveat_line < 15

    first_detail_heading = next(i for i, line in enumerate(lines) if line.startswith("## "))
    assert first_detail_heading > recommendation_line


def test_no_table_exceeds_five_columns(manifest_factory):
    # Mobile-width guardrail: every markdown table row in the render must
    # stay narrow enough to avoid horizontal scrolling.
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    markdown = render_markdown(record)

    for line in markdown.splitlines():
        if line.startswith("|") and line.endswith("|"):
            column_count = line.count("|") - 1
            assert column_count <= 5, f"table row too wide for mobile: {line!r}"


def test_markdown_never_asserts_the_report_itself_is_scientific_evidence(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    markdown = render_markdown(record)
    assert "does not itself constitute scientific evidence" in markdown
