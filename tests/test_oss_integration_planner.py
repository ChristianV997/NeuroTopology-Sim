from __future__ import annotations

from oss_opportunities.opportunity_batch import build_opportunities_from_candidates
from oss_opportunities.planner import OpenSourceIntegrationPlanV1, plan_oss_integrations_from_opportunities
from tests._oss_opportunity_fixtures import (
    make_agpl_scraper_candidate,
    make_document_ingestion_candidate,
    make_frontend_stack_candidate,
    make_sparse_candidate,
)


def _make_plan(**kwargs):
    batch = build_opportunities_from_candidates(
        [make_document_ingestion_candidate(), make_frontend_stack_candidate(), make_agpl_scraper_candidate()]
    )
    return plan_oss_integrations_from_opportunities(batch, **kwargs), batch


def test_plan_has_no_validation_errors():
    plan, _ = _make_plan()
    assert plan.validate() == []


def test_immediate_adapter_and_external_tool_record_populated():
    plan, _ = _make_plan()
    all_repos = {c["repo_full_name"] for c in plan.immediate_adapter_candidates} | {
        c["repo_full_name"] for c in plan.external_tool_record_candidates
    }
    assert "microsoft/markitdown" in all_repos
    assert "D4Vinci/Scrapling" in all_repos


def test_architecture_emulation_candidates_populated():
    plan, _ = _make_plan()
    repos = {c["repo_full_name"] for c in plan.architecture_emulation_candidates}
    assert "TanStack/router" in repos


def test_all_candidates_marked_not_executed_not_installed():
    plan, _ = _make_plan()
    for bucket in (
        plan.immediate_adapter_candidates, plan.external_tool_record_candidates,
        plan.architecture_emulation_candidates, plan.documentation_reference_candidates,
    ):
        for item in bucket:
            assert item["not_executed"] is True
            assert item["not_installed"] is True


def test_rejected_candidates_recorded_not_dropped():
    batch = build_opportunities_from_candidates([make_document_ingestion_candidate(), make_sparse_candidate()])
    plan = plan_oss_integrations_from_opportunities(batch)
    assert len(plan.rejected_candidates) == len(batch.opportunities_rejected)
    for r in plan.rejected_candidates:
        assert r["not_executed"] is True


def test_proposed_next_prs_generated_and_conservative():
    plan, _ = _make_plan()
    assert plan.proposed_next_prs
    assert "Document Ingestion Adapter Registry v1" in plan.proposed_next_prs
    # No proposed PR name implies the integration was already performed.
    for name in plan.proposed_next_prs:
        assert "implemented" not in name.lower()
        assert "complete" not in name.lower()


def test_plan_id_deterministic():
    plan1, batch = _make_plan()
    plan2 = plan_oss_integrations_from_opportunities(batch)
    assert plan1.plan_id == plan2.plan_id


def test_dict_roundtrip():
    plan, _ = _make_plan()
    d = plan.to_dict()
    p2 = OpenSourceIntegrationPlanV1.from_dict(d)
    assert p2.to_dict() == d


def test_max_selected_limits_selection():
    batch = build_opportunities_from_candidates(
        [make_document_ingestion_candidate("a/repo1"), make_document_ingestion_candidate("a/repo2")]
    )
    plan = plan_oss_integrations_from_opportunities(batch, max_selected=1)
    assert len(plan.selected_opportunity_ids) == 1


def test_no_automatic_outreach_or_marketing_in_plan_output():
    plan, _ = _make_plan()
    text = plan.to_json().lower()
    assert "email sent" not in text
    assert "contacted maintainer" not in text
