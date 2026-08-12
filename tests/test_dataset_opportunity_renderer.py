from __future__ import annotations

import pytest

from dataset_opportunities.opportunity_batch import build_opportunities_from_candidates
from dataset_opportunities.planner import plan_next_actions_from_opportunities
from dataset_opportunities.renderer import render_opportunity_summary, write_opportunity_summary
from dataset_opportunities.validation import DatasetOpportunityStoreError
from tests._dataset_opportunity_fixtures import make_blocked_candidate, make_good_candidate


def _batch_and_plan():
    batch = build_opportunities_from_candidates([make_good_candidate(), make_blocked_candidate()], query_summary="fixture render test")
    plan = plan_next_actions_from_opportunities(batch)
    return batch, plan


def test_render_contains_required_sections():
    batch, plan = _batch_and_plan()
    text = render_opportunity_summary(batch, plan)
    for heading in (
        "## Query summary", "## Candidate counts", "## Top opportunities",
        "## Recommended next actions", "## Dataset risks", "## Acquisition planning candidates",
        "## Benchmark-pack proposal candidates", "## Literature-review tasks",
        "## Researcher-outreach candidates", "## Limitations", "## Blocked actions",
        "## Reproducibility", "## Awareness Studio ingest path",
    ):
        assert heading in text


def test_render_without_plan_still_works():
    batch, _ = _batch_and_plan()
    text = render_opportunity_summary(batch)
    assert "# Dataset Opportunity Scouting Report" in text


def test_render_is_deterministic():
    batch, plan = _batch_and_plan()
    t1 = render_opportunity_summary(batch, plan)
    t2 = render_opportunity_summary(batch, plan)
    assert t1 == t2


def test_render_never_claims_evidence():
    batch, plan = _batch_and_plan()
    text = render_opportunity_summary(batch, plan)
    assert "does not create evidence" in text


def test_render_raises_on_banned_phrase():
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    batch, plan = _batch_and_plan()
    batch.query_summary = f"this {BANNED_REPORT_PHRASES[0]}"
    with pytest.raises(DatasetOpportunityStoreError):
        render_opportunity_summary(batch, plan)


def test_write_opportunity_summary_creates_file(tmp_path):
    batch, plan = _batch_and_plan()
    out = tmp_path / "summary.md"
    written = write_opportunity_summary(batch, plan, out)
    assert written.exists()
    assert "# Dataset Opportunity Scouting Report" in written.read_text(encoding="utf-8")
