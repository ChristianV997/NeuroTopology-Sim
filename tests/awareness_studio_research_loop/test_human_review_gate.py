from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_reviewer_decision_blocks_paper_draft(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["reviewer_decisions"] = {"decisions": []}
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "HUMAN_REVIEW_REQUIRED"
    assert "H1" in report["human_review_summary"]["hypotheses_requiring_review"]


def test_pending_reviewer_decision_blocks_paper_draft(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["reviewer_decisions"]["decisions"][0]["decision"] = "pending"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "HUMAN_REVIEW_REQUIRED"


def test_rejected_reviewer_decision_blocks_paper_draft(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["reviewer_decisions"]["decisions"][0]["decision"] = "rejected"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "HUMAN_REVIEW_REQUIRED"


def test_not_required_reviewer_decision_allows_paper_draft(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["reviewer_decisions"]["decisions"][0]["decision"] = "not_required"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "PAPER_DRAFT_READY"
    assert "H1" not in report["human_review_summary"]["hypotheses_requiring_review"]
