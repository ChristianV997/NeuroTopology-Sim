from __future__ import annotations

from oss_opportunities.license_review import RepositoryLicenseReviewV1
from oss_opportunities.scoring import score_opportunity
from tests._oss_opportunity_fixtures import (
    make_agpl_scraper_candidate,
    make_document_ingestion_candidate,
    make_frontend_stack_candidate,
    make_sparse_candidate,
)


def _review_for(candidate):
    return RepositoryLicenseReviewV1.make(
        repo_full_name=candidate.repo_full_name, license_spdx=candidate.license_spdx,
        license_name=candidate.license_name, provenance="fixture", limitations=["synthetic"],
    )


def test_document_ingestion_scores_high_for_awareness_studio_and_literature():
    c = make_document_ingestion_candidate()
    result = score_opportunity(c, _review_for(c))
    assert result["leverage_category"] == "document_ingestion"
    assert result["relevance_to_literature_pipeline"] in ("moderate", "high")
    assert result["relevance_to_awareness_studio"] in ("moderate", "high")
    assert result["recommended_action"] == "integrate_as_optional_adapter"


def test_agpl_scraper_scores_high_for_external_adapter_but_blocked_for_commercial_core_copy():
    c = make_agpl_scraper_candidate()
    review = _review_for(c)
    result = score_opportunity(c, review)
    assert result["leverage_category"] == "web_literature_acquisition"
    assert result["recommended_action"] == "integrate_as_external_tool_record"
    assert result["recommended_action"] != "integrate_as_optional_adapter"
    assert review.commercial_core_policy != "allowed_with_attribution"


def test_frontend_stack_scores_high_for_saas_low_for_python_core():
    c = make_frontend_stack_candidate()
    result = score_opportunity(c, _review_for(c))
    assert result["leverage_category"] == "frontend_stack"
    assert result["relevance_to_saas_future"] in ("moderate", "high")
    assert result["recommended_action"] == "emulate_architecture_pattern"
    assert result["score_components"]["dependency_weight_penalty"] < 0


def test_trending_stars_alone_do_not_force_immediate_integration():
    c = make_frontend_stack_candidate()
    c.stars = 500000
    c.star_gain = 50000
    result = score_opportunity(c, _review_for(c))
    # Even with enormous star counts, a non-Python-core frontend stack still
    # emulates rather than becoming an immediate adapter/dependency.
    assert result["recommended_action"] == "emulate_architecture_pattern"


def test_unknown_license_lowers_score_vs_permissive():
    c_mit = make_document_ingestion_candidate("some/mit-repo")
    c_unknown = make_document_ingestion_candidate("some/unknown-repo")
    c_unknown.license_spdx = "unknown"
    c_unknown.license_name = "unknown"

    result_mit = score_opportunity(c_mit, _review_for(c_mit))
    result_unknown = score_opportunity(c_unknown, _review_for(c_unknown))
    assert result_unknown["total_score"] < result_mit["total_score"]
    assert result_unknown["score_components"]["license_safety"] < result_mit["score_components"]["license_safety"]


def test_sparse_candidate_falls_back_to_reject_or_defer():
    c = make_sparse_candidate()
    result = score_opportunity(c, _review_for(c))
    assert result["leverage_category"] == "reject_or_defer"
    assert result["recommended_action"] in ("reject", "defer")


def test_score_components_sum_to_total():
    c = make_document_ingestion_candidate()
    result = score_opportunity(c, _review_for(c))
    assert round(sum(result["score_components"].values()), 2) == result["total_score"]


def test_blocked_actions_always_include_required_floor():
    from oss_opportunities.validation import REQUIRED_BLOCKED_ACTIONS

    c = make_document_ingestion_candidate()
    result = score_opportunity(c, _review_for(c))
    assert set(result["blocked_actions"]) >= REQUIRED_BLOCKED_ACTIONS


def test_weak_copyleft_document_ingestion_uses_external_tool_record_not_optional_adapter():
    # Only permissive_low may recommend integrate_as_optional_adapter (the
    # one action that implies in-process code copy) -- weak_copyleft_medium
    # (e.g. LGPL) is a real, common license tier for document-ingestion
    # tooling and must consistently get the external-tool-record path
    # instead, matching validate_opportunity_against_license_review's
    # cross-object gate.
    c = make_document_ingestion_candidate("some/lgpl-repo")
    c.license_spdx = "LGPL-2.1"
    c.license_name = "GNU LGPL v2.1"
    review = _review_for(c)
    assert review.license_risk == "weak_copyleft_medium"
    result = score_opportunity(c, review)
    assert result["recommended_action"] == "integrate_as_external_tool_record"


def test_never_recommends_execution_or_install_actions():
    for maker in (make_document_ingestion_candidate, make_agpl_scraper_candidate, make_frontend_stack_candidate):
        c = maker()
        result = score_opportunity(c, _review_for(c))
        assert result["recommended_action"] not in ("execute_untrusted_code", "auto_install_dependency")
