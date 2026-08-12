from __future__ import annotations

from dataset_opportunities.opportunity_batch import build_opportunities_from_candidates
from dataset_opportunities.planner import DatasetOpportunityPlanV1, plan_next_actions_from_opportunities
from tests._dataset_opportunity_fixtures import make_good_candidate


def _make_plan(**kwargs):
    batch = build_opportunities_from_candidates([make_good_candidate()], query_summary="fixture")
    return plan_next_actions_from_opportunities(batch, **kwargs), batch


def test_plan_has_no_validation_errors():
    plan, _ = _make_plan()
    assert plan.validate() == []


def test_every_outreach_candidate_requires_human_review():
    plan, _ = _make_plan()
    for candidate in plan.planned_outreach_candidates:
        assert candidate["requires_human_review"] is True


def test_outreach_candidates_marked_not_sent():
    plan, _ = _make_plan()
    for candidate in plan.planned_outreach_candidates:
        assert candidate.get("not_sent") is True


def test_acquisition_candidates_marked_not_executed():
    plan, _ = _make_plan()
    for candidate in plan.planned_acquisition_candidates:
        assert "not executed" in candidate["safety_notes"]


def test_plan_id_deterministic():
    plan1, batch = _make_plan()
    plan2 = plan_next_actions_from_opportunities(batch)
    assert plan1.plan_id == plan2.plan_id


def test_dict_roundtrip():
    plan, _ = _make_plan()
    d = plan.to_dict()
    p2 = DatasetOpportunityPlanV1.from_dict(d)
    assert p2.to_dict() == d


def test_max_selected_limits_selection():
    a = make_good_candidate("ds000001")
    b = make_good_candidate("ds000002")
    batch = build_opportunities_from_candidates([a, b], query_summary="fixture")
    plan = plan_next_actions_from_opportunities(batch, max_selected=1)
    assert len(plan.selected_opportunity_ids) == 1


def test_no_execution_occurs_only_proposals():
    plan, _ = _make_plan()
    assert plan.awareness_studio_manifest_path in ("", None) or isinstance(plan.awareness_studio_manifest_path, str)
    for line in plan.limitations:
        assert "does not execute" in line or "no researcher has been contacted" in line
