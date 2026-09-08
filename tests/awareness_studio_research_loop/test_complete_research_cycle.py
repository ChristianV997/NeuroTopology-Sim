from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tools.awareness_studio_research_loop.render_csv import render_csv_tables

from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_complete_research_cycle_reaches_paper_draft_ready(manifest_factory):
    manifest = manifest_factory(complete_cycle_overrides())

    report = compile_research_cycle(manifest, now=NOW, repo="NeuroTopology-Sim")

    assert report["status"] == "complete"
    assert all(v["available"] for v in report["completeness"].values())
    assert report["cycle_states"]["H1"]["state"] == "PAPER_DRAFT_READY"
    assert all(g["passed"] for g in report["gate_results"].values()), report["gate_results"]
    assert report["unsupported_promotion_violations"] == []

    ledger_row = report["artifact_ledger"][0]
    assert ledger_row["experiment_id"] == "E1"
    assert ledger_row["scientific_status"] == "formal"
    assert ledger_row["reviewer_status"] == "approved"

    markdown = report["paper_draft_markdown"]
    assert "## Research Question" in markdown
    assert "[H1]" in markdown
    assert "[C1]" in markdown
    assert "[E1]" in markdown
    assert "does not itself constitute" in markdown or "not itself" in markdown

    csv_tables = render_csv_tables(report)
    assert "H1" in csv_tables["cycle_states.csv"]
