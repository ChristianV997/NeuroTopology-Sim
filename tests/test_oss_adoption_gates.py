"""Adoption/compatibility gates for oss_opportunities (offline, synthetic).

Covers: missing and ambiguous source identity, unresolved license (unknown
or unmatched string), duplicate observations of one repository, keyword-only
capability claims, and adoption blocked by credential requirements.

Nothing here clones a repository, installs a dependency, or calls the network.
These are engineering-adoption checks only, not scientific or legal review.
"""
from __future__ import annotations

import pytest

from oss_opportunities.license_review import RepositoryLicenseReviewV1
from oss_opportunities.opportunity_batch import build_opportunities_from_candidates
from oss_opportunities.planner import plan_oss_integrations_from_opportunities
from oss_opportunities.scoring import score_opportunity
from oss_opportunities.validation import OssOpportunityValidationError
from tests._oss_opportunity_fixtures import (
    make_document_ingestion_candidate,
    make_unknown_license_candidate,
)


def _review(candidate):
    return RepositoryLicenseReviewV1.make(
        repo_full_name=candidate.repo_full_name,
        license_spdx=candidate.license_spdx,
        license_name=candidate.license_name,
        provenance="synthetic fixture",
        limitations=["synthetic fixture only"],
    )


def _observation(source, **overrides):
    """Another observation of the same repository, from a different source."""
    candidate = make_document_ingestion_candidate()
    candidate.source = source
    for name, value in overrides.items():
        setattr(candidate, name, value)
    candidate.candidate_id = candidate.recompute_id()
    return candidate


# ── missing / ambiguous source identity ─────────────────────────────────────


def test_bare_repo_name_without_owner_is_ambiguous():
    candidate = make_document_ingestion_candidate("markitdown")
    assert any("ambiguous source identity" in e for e in candidate.validate())
    with pytest.raises(OssOpportunityValidationError, match="ambiguous source identity"):
        build_opportunities_from_candidates([candidate])


def test_owner_that_disagrees_with_repo_full_name_is_ambiguous():
    candidate = make_document_ingestion_candidate()
    candidate.owner = "someone-else"
    assert any("does not match repo_full_name" in e for e in candidate.validate())


def test_repo_url_pointing_at_another_repository_is_ambiguous():
    candidate = make_document_ingestion_candidate()
    candidate.repo_url = "https://github.com/other-org/markitdown"
    assert any("does not point to repo_full_name" in e for e in candidate.validate())


def test_repo_url_matching_case_insensitively_is_accepted():
    candidate = make_document_ingestion_candidate()
    candidate.repo_url = "https://GitHub.com/Microsoft/MarkItDown/"
    assert candidate.validate() == []


def test_candidate_without_repo_url_is_accepted():
    candidate = make_document_ingestion_candidate()
    candidate.repo_url = ""
    assert candidate.validate() == []


@pytest.mark.parametrize(("field", "bad_value"), [("repo_full_name", 123), ("owner", ["microsoft"]), ("repo_url", 42)])
def test_non_string_identity_field_is_reported_not_raised(field, bad_value):
    candidate = make_document_ingestion_candidate()
    setattr(candidate, field, bad_value)
    assert any(f"{field} must be a string" in e for e in candidate.validate())


def test_non_string_identity_field_fails_closed_at_batch_build():
    candidate = make_document_ingestion_candidate()
    candidate.owner = ["microsoft"]
    with pytest.raises(OssOpportunityValidationError, match="owner must be a string"):
        build_opportunities_from_candidates([candidate])


def test_unhashable_source_is_reported_not_raised():
    candidate = make_document_ingestion_candidate()
    candidate.source = ["github_manual_seed"]
    errors = candidate.validate()
    assert any("source must be a string" in error for error in errors)
    with pytest.raises(OssOpportunityValidationError, match="source must be a string"):
        build_opportunities_from_candidates([candidate])


def test_malformed_metadata_and_incomplete_provenance_fail_closed():
    candidate = make_document_ingestion_candidate()
    candidate.source = "trendshift_signal"
    candidate.metadata = ["requires_credentials"]
    assert any("metadata must be a mapping" in error for error in candidate.validate())

    candidate = make_document_ingestion_candidate()
    candidate.provenance = 17
    candidate.limitations = "not a list"
    errors = candidate.validate()
    assert any("provenance is required" in error for error in errors)
    assert any("limitations must be a non-empty list" in error for error in errors)


@pytest.mark.parametrize("bad_value", ["many", True, -1])
def test_malformed_or_negative_star_gain_is_rejected_before_scoring(bad_value):
    candidate = make_document_ingestion_candidate()
    candidate.star_gain = bad_value
    errors = candidate.validate()
    assert any("star_gain" in error for error in errors)
    with pytest.raises(OssOpportunityValidationError, match="star_gain"):
        score_opportunity(candidate, _review(candidate))


def test_candidate_id_must_match_its_observation_provenance():
    candidate = make_document_ingestion_candidate()
    candidate.candidate_id = "forged-observation-id"
    assert any("candidate_id does not match observation identity" in error for error in candidate.validate())
    with pytest.raises(OssOpportunityValidationError, match="candidate_id does not match observation identity"):
        build_opportunities_from_candidates([candidate])


def test_missing_source_fails_closed_at_batch_build():
    candidate = make_document_ingestion_candidate()
    candidate.source = ""
    candidate.candidate_id = candidate.recompute_id()
    with pytest.raises(OssOpportunityValidationError, match="must be one of"):
        build_opportunities_from_candidates([candidate])


# ── unresolved license ──────────────────────────────────────────────────────


def test_unmatched_license_string_requires_license_review_not_adapter():
    candidate = make_document_ingestion_candidate("some/other-licensed-tool")
    candidate.license_spdx = "Other"
    candidate.license_name = "Other"
    review = _review(candidate)
    assert review.license_risk == "proprietary_or_unknown_high"
    result = score_opportunity(candidate, review)
    assert result["recommended_action"] == "license_review_required"


def test_unmatched_license_is_routed_to_license_review_queue_in_plan():
    candidate = make_document_ingestion_candidate("some/other-licensed-tool")
    candidate.license_spdx = "Other"
    candidate.license_name = "Other"
    batch = build_opportunities_from_candidates([candidate])
    plan = plan_oss_integrations_from_opportunities(batch)
    assert [item["repo_full_name"] for item in plan.license_review_queue] == ["some/other-licensed-tool"]
    assert plan.immediate_adapter_candidates == []
    assert plan.external_tool_record_candidates == []


def test_missing_license_still_requires_license_review():
    candidate = make_unknown_license_candidate()
    result = score_opportunity(candidate, _review(candidate))
    assert result["recommended_action"] == "license_review_required"


# ── duplicate candidates ────────────────────────────────────────────────────


def test_same_repo_from_two_sources_is_not_ranked_twice():
    first = make_document_ingestion_candidate()
    second = _observation("github_manual_seed")
    batch = build_opportunities_from_candidates([first, second])

    assert batch.candidates_seen == 2
    assert len(batch.opportunities_ranked) == 1
    assert len(batch.opportunities_rejected) == 1
    duplicate = batch.opportunities_rejected[0]
    assert duplicate["duplicate_of"] == batch.opportunities_ranked[0]["opportunity_id"]
    assert duplicate["reason"].startswith("duplicate_of:")
    assert batch.metadata == {"duplicate_observations": 1}
    assert batch.validate() == []
    assert batch.top_by_category == {"document_ingestion": ["microsoft/markitdown"]}
    assert "microsoft/markitdown" not in batch.top_rejections


def test_duplicate_matching_is_case_insensitive():
    first = make_document_ingestion_candidate("microsoft/markitdown")
    second = _observation("github_manual_seed", repo_full_name="Microsoft/MarkItDown", owner="Microsoft", name="MarkItDown")
    batch = build_opportunities_from_candidates([first, second])
    assert len(batch.opportunities_ranked) == 1
    assert batch.metadata == {"duplicate_observations": 1}


def test_conflicting_duplicate_license_observations_require_review():
    permissive = make_document_ingestion_candidate()
    copyleft = _observation("github_manual_seed", license_spdx="AGPL-3.0", license_name="GNU AGPLv3")
    batch = build_opportunities_from_candidates([copyleft, permissive])

    ranked = batch.opportunities_ranked
    assert len(ranked) == 1
    assert ranked[0]["recommended_action"] == "license_review_required"
    assert ranked[0]["license_review"]["license_risk"] == "missing_high"
    assert ranked[0]["license_review"]["metadata"]["license_observation_status"] == "conflict"
    assert ranked[0]["license_review"]["metadata"]["observed_license_spdx"] == ["AGPL-3.0", "MIT"]
    assert batch.opportunities_rejected[0]["duplicate_of"] == ranked[0]["opportunity_id"]

    plan = plan_oss_integrations_from_opportunities(batch)
    assert [item["repo_full_name"] for item in plan.license_review_queue] == ["microsoft/markitdown"]
    assert plan.immediate_adapter_candidates == []
    assert plan.external_tool_record_candidates == []


def test_conflicting_license_result_is_independent_of_input_order():
    first = make_document_ingestion_candidate()
    second = _observation("github_manual_seed", license_spdx="AGPL-3.0", license_name="GNU AGPLv3")
    forward = build_opportunities_from_candidates([first, second])
    reverse = build_opportunities_from_candidates([second, first])
    left = forward.opportunities_ranked[0]["license_review"]
    right = reverse.opportunities_ranked[0]["license_review"]
    assert left["license_risk"] == right["license_risk"] == "missing_high"
    assert left["metadata"] == right["metadata"]
    assert left["license_review_id"] == right["license_review_id"]


def test_case_only_duplicate_license_spelling_does_not_create_conflict():
    first = make_document_ingestion_candidate()
    second = _observation("github_manual_seed", license_spdx="mit", license_name="MIT")
    batch = build_opportunities_from_candidates([first, second])
    assert len(batch.opportunities_ranked) == 1
    assert batch.opportunities_ranked[0]["recommended_action"] == "integrate_as_optional_adapter"
    assert batch.opportunities_ranked[0]["license_review"]["license_risk"] == "permissive_low"
    assert batch.metadata["duplicate_observations"] == 1


def test_direct_scoring_rejects_mismatched_license_review_and_repository():
    candidate = make_document_ingestion_candidate()
    review = RepositoryLicenseReviewV1.make(
        repo_full_name="different/repository",
        license_spdx="MIT",
        provenance="synthetic fixture",
        limitations=["synthetic fixture only"],
    )
    with pytest.raises(OssOpportunityValidationError, match="license review does not match candidate"):
        score_opportunity(candidate, review)


def test_rejected_or_unknown_license_review_status_cannot_score_as_adoptable():
    candidate = make_document_ingestion_candidate()
    review = _review(candidate)
    review.review_status = "rejected"
    assert any("review_status" in error for error in review.validate())
    with pytest.raises(OssOpportunityValidationError, match="review_status"):
        score_opportunity(candidate, review)


@pytest.mark.parametrize("field", ["license_risk", "commercial_core_policy"])
def test_unhashable_license_review_enums_are_reported_not_raised(field):
    review = _review(make_document_ingestion_candidate())
    setattr(review, field, ["invalid"])
    errors = review.validate()
    assert any(field in error for error in errors)


def test_identical_observation_twice_is_deduplicated():
    batch = build_opportunities_from_candidates(
        [make_document_ingestion_candidate(), make_document_ingestion_candidate()]
    )
    assert batch.candidates_seen == 2
    assert len(batch.opportunities_ranked) == 1
    assert batch.metadata == {"duplicate_observations": 1}


def test_single_observation_reports_no_duplicates():
    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    assert batch.metadata == {"duplicate_observations": 0}


# ── unsupported capability claims ───────────────────────────────────────────


def test_keyword_only_category_gets_half_adapter_surface_credit():
    candidate = make_document_ingestion_candidate()
    result = score_opportunity(candidate, _review(candidate))
    assert result["score_components"]["adapter_surface_clarity"] == 0.5


def test_documented_homepage_earns_full_adapter_surface_credit():
    candidate = make_document_ingestion_candidate()
    candidate.homepage_url = "https://example.org/markitdown-docs"
    result = score_opportunity(candidate, _review(candidate))
    assert result["score_components"]["adapter_surface_clarity"] == 1.0


def test_explicit_adapter_docs_metadata_counts_as_documented_surface():
    candidate = make_document_ingestion_candidate()
    candidate.metadata = {"adapter_docs_url": "https://example.org/adapter"}
    result = score_opportunity(candidate, _review(candidate))
    assert result["score_components"]["adapter_surface_clarity"] == 1.0


def test_security_category_gets_no_adapter_surface_credit():
    candidate = make_unknown_license_candidate()
    result = score_opportunity(candidate, _review(candidate))
    assert result["leverage_category"] == "security_compliance"
    assert result["score_components"]["adapter_surface_clarity"] == 0.0


def test_documentation_changes_the_score_but_does_not_gate_adoption():
    """Documented limitation: the capability gate lowers credit for keyword-only
    claims. It does not convert the recommended adoption action, which stays a
    review-level decision rather than a verified capability."""
    keyword_only = make_document_ingestion_candidate()
    documented = make_document_ingestion_candidate()
    documented.homepage_url = "https://example.org/markitdown-docs"
    before = score_opportunity(keyword_only, _review(keyword_only))
    after = score_opportunity(documented, _review(documented))
    assert round(after["total_score"] - before["total_score"], 2) == 0.5
    assert before["recommended_action"] == after["recommended_action"] == "integrate_as_optional_adapter"


# ── adoption blocked by unresolved risk ─────────────────────────────────────


def test_credentialed_permissive_tool_waits_for_security_review():
    candidate = make_document_ingestion_candidate()
    candidate.metadata = {"requires_credentials": True}
    result = score_opportunity(candidate, _review(candidate))
    assert result["recommended_action"] == "security_review_required"
    assert "credential_required_execution" in result["blocked_actions"]


def test_credentialed_tool_lands_in_security_queue_not_adapter_bucket():
    candidate = make_document_ingestion_candidate()
    candidate.metadata = {"requires_credentials": True}
    batch = build_opportunities_from_candidates([candidate])
    plan = plan_oss_integrations_from_opportunities(batch)
    assert [item["repo_full_name"] for item in plan.security_review_queue] == ["microsoft/markitdown"]
    assert plan.immediate_adapter_candidates == []
    assert plan.external_tool_record_candidates == []


def test_uncredentialed_permissive_tool_still_gets_adapter_recommendation():
    candidate = make_document_ingestion_candidate()
    result = score_opportunity(candidate, _review(candidate))
    assert result["recommended_action"] == "integrate_as_optional_adapter"


def test_engineering_recommendation_does_not_claim_science_security_or_legal_clearance():
    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    opportunity = batch.opportunities_ranked[0]
    assert not {"scientific_validity", "security_certified", "legal_approved"} & set(opportunity)
    limitations = " ".join(opportunity["limitations"]).casefold()
    assert "does not establish scientific validity" in limitations
    assert "security certification" in limitations
    assert "legal approval" in limitations


# ── malformed evidence fails closed (PR 386 audit regressions) ─────────────

def test_malformed_snapshot_date_is_rejected_even_with_a_recomputed_id():
    candidate = make_document_ingestion_candidate()
    candidate.source_snapshot_date = "not-a-date"
    candidate.candidate_id = candidate.recompute_id()
    assert any("source_snapshot_date" in error for error in candidate.validate())


def test_well_formed_snapshot_date_is_accepted():
    candidate = make_document_ingestion_candidate()
    assert candidate.source_snapshot_date == "2026-08-12"
    assert not any("source_snapshot_date" in error for error in candidate.validate())


@pytest.mark.parametrize("bad_url", ["javascript:alert(1)", "not a url", "ftp:/x"])
def test_non_http_homepage_cannot_earn_documented_surface_credit(bad_url):
    candidate = make_document_ingestion_candidate()
    candidate.homepage_url = bad_url
    assert any("homepage_url" in error for error in candidate.validate())
    with pytest.raises(OssOpportunityValidationError):
        score_opportunity(candidate, _review(candidate))


def test_non_http_adapter_docs_url_is_rejected():
    candidate = make_document_ingestion_candidate()
    candidate.metadata = {"adapter_docs_url": "javascript:alert(1)"}
    assert any("adapter_docs_url" in error for error in candidate.validate())


def test_human_reviewed_status_requires_a_named_reviewer():
    candidate = make_document_ingestion_candidate()
    unnamed = RepositoryLicenseReviewV1.make(
        repo_full_name=candidate.repo_full_name,
        license_spdx=candidate.license_spdx,
        license_name=candidate.license_name,
        provenance="synthetic fixture",
        limitations=["synthetic fixture only"],
        review_status="human_reviewed",
    )
    assert any("reviewer" in error for error in unnamed.validate())
    with pytest.raises(OssOpportunityValidationError):
        score_opportunity(candidate, unnamed)
    named = RepositoryLicenseReviewV1.make(
        repo_full_name=candidate.repo_full_name,
        license_spdx=candidate.license_spdx,
        license_name=candidate.license_name,
        provenance="synthetic fixture",
        limitations=["synthetic fixture only"],
        review_status="human_reviewed",
        metadata={"reviewer": "synthetic reviewer"},
    )
    assert named.validate() == []
