from __future__ import annotations

from dataset_opportunities.scoring import score_opportunity
from dataset_opportunities.validation import REQUIRED_BLOCKED_ACTIONS
from tests._dataset_opportunity_fixtures import make_blocked_candidate, make_good_candidate, make_sparse_candidate


def test_good_candidate_scores_higher_than_blocked():
    good_result = score_opportunity(make_good_candidate())
    blocked_result = score_opportunity(make_blocked_candidate())
    assert good_result["total_score"] > blocked_result["total_score"]


def test_score_components_sum_to_total():
    result = score_opportunity(make_good_candidate())
    assert round(sum(result["score_components"].values()), 2) == result["total_score"]


def test_blocked_actions_always_include_required_floor():
    result = score_opportunity(make_good_candidate())
    assert set(result["blocked_actions"]) >= REQUIRED_BLOCKED_ACTIONS


def test_unknown_access_excludes_execution_oriented_actions():
    result = score_opportunity(make_blocked_candidate())
    for action in ("acquisition_plan_only", "benchmark_pack_proposal", "local_availability_check"):
        assert action not in result["recommended_next_actions"]


def test_missing_task_labels_lowers_mapping_signal():
    good = score_opportunity(make_good_candidate())
    sparse = score_opportunity(make_sparse_candidate())
    assert sparse["score_components"]["task_state_relevance"] <= good["score_components"]["task_state_relevance"]


def test_outreach_potential_insufficient_without_identifier_or_contact():
    from dataset_importers.candidate_record import DatasetCandidateRecordV1

    no_identifier = DatasetCandidateRecordV1.make(
        source_catalog="eegdash", source_dataset_id="ds000777",
        public_url="", repository_url="", documentation_url="",
        license_risk="unknown_high", access_status="unknown",
        transition_readiness="blocked_missing_metadata",
        provenance="fixture", limitations=["synthetic"], risks=["no identifiers present"],
    )
    result = score_opportunity(no_identifier)
    assert result["outreach_potential"] == "insufficient_data"


def test_outreach_potential_not_insufficient_with_public_url():
    result = score_opportunity(make_good_candidate())
    assert result["outreach_potential"] != "insufficient_data"


def test_blocked_candidate_recommends_reject():
    result = score_opportunity(make_blocked_candidate())
    assert "reject" in result["recommended_next_actions"]


def test_risk_flags_present_for_unknown_signal():
    result = score_opportunity(make_blocked_candidate())
    assert any("unknown_or_restricted" in f for f in result["risk_flags"])


def test_never_promotes_to_evidence_vocabulary():
    result = score_opportunity(make_good_candidate())
    for action in result["recommended_next_actions"]:
        assert "evidence" not in action
        assert "clinical" not in action
