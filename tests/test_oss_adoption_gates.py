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
from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1
from oss_opportunities.opportunity_batch import build_opportunities_from_candidates, compute_batch_id
from oss_opportunities.planner import compute_plan_id, plan_oss_integrations_from_opportunities
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


def test_unknown_schema_versions_fail_closed_across_pipeline_records():
    candidate = make_document_ingestion_candidate()
    candidate.schema_version = "future"
    assert any("schema_version" in error for error in candidate.validate())

    review = _review(make_document_ingestion_candidate())
    review.schema_version = "future"
    assert any("schema_version" in error for error in review.validate())

    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    batch.schema_version = "future"
    assert any("schema_version" in error for error in batch.validate())

    entry = batch.opportunities_ranked[0]
    opportunity = OpenSourceIntegrationOpportunityV1.from_dict(
        {key: value for key, value in entry.items() if key != "license_review"}
    )
    opportunity.schema_version = "future"
    assert any("schema_version" in error for error in opportunity.validate())

    valid_batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    plan = plan_oss_integrations_from_opportunities(valid_batch)
    plan.schema_version = "future"
    assert any("schema_version" in error for error in plan.validate())


def test_unknown_algorithm_versions_cannot_be_self_asserted_by_rehashing_ids():
    candidate = make_document_ingestion_candidate()
    review = _review(candidate)
    review.license_policy_version = "future"
    review.license_review_id = review.recompute_id()
    assert any("license_policy_version" in error for error in review.validate())

    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    entry = batch.opportunities_ranked[0]
    opportunity = OpenSourceIntegrationOpportunityV1.from_dict(
        {key: value for key, value in entry.items() if key != "license_review"}
    )
    opportunity.scoring_version = "future"
    opportunity.opportunity_id = opportunity.recompute_id()
    assert any("scoring_version" in error for error in opportunity.validate())

    batch.scoring_version = "future"
    batch.batch_id = compute_batch_id(
        opportunity_ids=[row["opportunity_id"] for row in batch.opportunities_ranked],
        sources_scanned=batch.sources_scanned,
        scoring_version=batch.scoring_version,
    )
    assert any("scoring_version" in error for error in batch.validate())

    valid_batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    plan = plan_oss_integrations_from_opportunities(valid_batch)
    plan.planner_version = "future"
    plan.plan_id = compute_plan_id(
        batch_id=plan.batch_id,
        selected_opportunity_ids=plan.selected_opportunity_ids,
        planner_version=plan.planner_version,
    )
    assert any("planner_version" in error for error in plan.validate())


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


def _sparse_observation(source: str, **overrides):
    """Keyword-less observation → leverage_category reject_or_defer."""
    candidate = make_document_ingestion_candidate(overrides.pop("repo_full_name", "acme/widget"))
    candidate.description = "a utility library"
    candidate.topics = []
    candidate.name = "widget"
    candidate.observed_categories = []
    candidate.source = source
    for name, value in overrides.items():
        setattr(candidate, name, value)
    candidate.candidate_id = candidate.recompute_id()
    return candidate


def test_license_conflict_on_reject_or_defer_category_still_requires_review():
    """Unresolved license evidence outranks category-based reject/defer.

    Sparse duplicates with conflicting SPDX labels must not be ranked away as
    reject/defer; the planner must still enqueue license review.
    """
    first = _sparse_observation(
        "github_manual_seed",
        license_spdx="MIT",
        license_name="MIT",
        source_snapshot_date="2026-01-01",
    )
    second = _sparse_observation(
        "github_metadata",
        license_spdx="GPL-3.0",
        license_name="GPL",
        source_snapshot_date="2026-01-02",
    )
    batch = build_opportunities_from_candidates([first, second])

    assert batch.metadata.get("license_conflicts") == 1
    assert len(batch.opportunities_ranked) == 1
    primary = batch.opportunities_ranked[0]
    assert primary["leverage_category"] == "reject_or_defer"
    assert primary["recommended_action"] == "license_review_required"
    assert primary["license_review"]["metadata"]["license_observation_status"] == "conflict"
    assert primary["recommended_action"] != "reject"
    assert "microsoft/markitdown" not in batch.top_immediate_adapters
    assert "acme/widget" not in batch.top_immediate_adapters

    plan = plan_oss_integrations_from_opportunities(batch)
    assert [item["repo_full_name"] for item in plan.license_review_queue] == ["acme/widget"]
    assert plan.immediate_adapter_candidates == []
    assert plan.external_tool_record_candidates == []
    assert plan.rejected_candidates  # duplicate observation only


def test_unknown_license_on_reject_or_defer_category_requires_review_not_silent_reject():
    candidate = _sparse_observation(
        "github_manual_seed",
        license_spdx="unknown",
        license_name="unknown",
    )
    result = score_opportunity(candidate, _review(candidate))
    assert result["leverage_category"] == "reject_or_defer"
    assert result["recommended_action"] == "license_review_required"

    batch = build_opportunities_from_candidates([candidate])
    assert batch.opportunities_ranked[0]["recommended_action"] == "license_review_required"
    plan = plan_oss_integrations_from_opportunities(batch)
    assert [item["repo_full_name"] for item in plan.license_review_queue] == ["acme/widget"]


def test_plan_selection_limit_never_hides_required_review_actions():
    candidates = []
    for repo in ("org/review-one", "org/review-two"):
        candidate = make_unknown_license_candidate(repo)
        candidate.owner = "org"
        candidate.name = repo.split("/", 1)[1]
        candidate.candidate_id = candidate.recompute_id()
        candidates.append(candidate)
    batch = build_opportunities_from_candidates(candidates)
    plan = plan_oss_integrations_from_opportunities(batch, max_selected=0)
    assert {row["repo_full_name"] for row in plan.license_review_queue} == {
        "org/review-one", "org/review-two"
    }


@pytest.mark.parametrize("max_selected", [-1, True, 1.5, "1"])
def test_plan_selection_limit_rejects_invalid_values(max_selected):
    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    with pytest.raises(OssOpportunityValidationError, match="max_selected"):
        plan_oss_integrations_from_opportunities(batch, max_selected=max_selected)


def test_plan_identifier_is_bound_to_batch_and_selected_rows():
    batch = build_opportunities_from_candidates([make_document_ingestion_candidate()])
    plan = plan_oss_integrations_from_opportunities(batch)
    plan.plan_id = "forged-plan-id"
    assert any("plan_id" in error for error in plan.validate())


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
    duplicate = batch.opportunities_rejected[0]
    assert "opportunity_id" not in duplicate
    assert duplicate["duplicate_of"] == batch.opportunities_ranked[0]["opportunity_id"]
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


# ── fail-closed hardening: malformed inputs, forged batches, entry points ──


import copy
import json

from oss_opportunities.export_oss_opportunities import main as cli_main
from oss_opportunities.opportunity_batch import OpenSourceLeverageBatchV1
from oss_opportunities.source_ingestion import (
    import_from_manual_seed,
    import_from_starmap_fixture,
    import_from_trendshift_fixture,
)


@pytest.mark.parametrize("bad", [None, 5, "abc", {}, [None], [{}], ["owner/repo"], [1]])
def test_builder_rejects_non_candidate_input_with_controlled_error(bad):
    with pytest.raises(OssOpportunityValidationError):
        build_opportunities_from_candidates(bad)


@pytest.mark.parametrize("bad", ["CONFLICT", " conflict ", "disputed", True, 1, ["conflict"], {"x": 1}, None, ""])
def test_unrecognised_license_observation_status_is_rejected(bad):
    candidate = make_document_ingestion_candidate()
    review = _review(candidate)
    review.metadata = {"license_observation_status": bad}
    assert any("license_observation_status" in e for e in review.validate())
    with pytest.raises(OssOpportunityValidationError):
        score_opportunity(candidate, review)


def test_non_string_metadata_key_is_rejected_not_serialised():
    candidate = make_document_ingestion_candidate()
    candidate.metadata = {("a",): 1}
    assert any("metadata" in e and "key" in e for e in candidate.validate())
    with pytest.raises(OssOpportunityValidationError):
        build_opportunities_from_candidates([candidate])


def test_credential_evidence_on_any_duplicate_observation_requires_security_review():
    plain = make_document_ingestion_candidate()
    credentialed = _observation("github_manual_seed", metadata={"requires_credentials": True})
    for order in ([plain, credentialed], [credentialed, plain]):
        batch = build_opportunities_from_candidates(order)
        assert [e["recommended_action"] for e in batch.opportunities_ranked] == ["security_review_required"]


def _ranked_batch():
    return build_opportunities_from_candidates([make_document_ingestion_candidate()])


def _forge(mutate):
    batch = copy.deepcopy(_ranked_batch())
    mutate(batch)
    return batch


def _forge_score_components(batch, mutate):
    entry = batch.opportunities_ranked[0]
    mutate(entry["score_components"])
    entry["total_score"] = round(sum(float(value) for value in entry["score_components"].values()), 2)


_FORGERIES = {
    "risk_downgrade_mismatch": lambda b: b.opportunities_ranked[0]["license_review"].update(license_risk="strong_copyleft_high"),
    "review_repo_swapped": lambda b: b.opportunities_ranked[0]["license_review"].update(repo_full_name="evil/other"),
    "review_license_swapped": lambda b: b.opportunities_ranked[0]["license_review"].update(license_spdx="GPL-3.0"),
    "review_none": lambda b: b.opportunities_ranked[0].update(license_review=None),
    "review_removed": lambda b: b.opportunities_ranked[0].pop("license_review"),
    "conflict_marker_but_adapter": lambda b: b.opportunities_ranked[0]["license_review"].update(
        metadata={"license_observation_status": "conflict"}),
    "score_nan": lambda b: b.opportunities_ranked[0].update(total_score=float("nan")),
    "score_str": lambda b: b.opportunities_ranked[0].update(total_score="9"),
    "opportunity_id_forged": lambda b: b.opportunities_ranked[0].update(opportunity_id="forged-id"),
    "score_component_nan": lambda b: b.opportunities_ranked[0]["score_components"].update(
        direct_product_leverage=float("nan")),
    "score_component_unknown": lambda b: _forge_score_components(
        b, lambda c: c.update(untrusted_bonus=1000.0)),
    "score_component_boolean": lambda b: _forge_score_components(
        b, lambda c: c.update(direct_product_leverage=True)),
    "score_components_empty": lambda b: (
        b.opportunities_ranked[0].update(score_components={}),
        b.opportunities_ranked[0].update(total_score=1000000.0),
    ),
    "unknown_action": lambda b: b.opportunities_ranked[0].update(recommended_action="adopt_now"),
    "action_unhashable_type": lambda b: b.opportunities_ranked[0].update(recommended_action=[]),
    "category_unhashable_type": lambda b: b.opportunities_ranked[0].update(leverage_category=[]),
    "blocked_actions_emptied": lambda b: b.opportunities_ranked[0].update(blocked_actions=[]),
    "entry_is_str": lambda b: b.opportunities_ranked.__setitem__(0, "x"),
    "entry_none": lambda b: b.opportunities_ranked.__setitem__(0, None),
    "ranked_not_list": lambda b: setattr(b, "opportunities_ranked", 5),
    "rejected_not_list": lambda b: setattr(b, "opportunities_rejected", 5),
    "rejected_entry_str": lambda b: setattr(b, "opportunities_rejected", ["x"]),
    "attribution_required_integer": lambda b: b.opportunities_ranked[0]["license_review"].update(
        attribution_required=0),
    "scientific_pass_field": lambda b: b.opportunities_ranked[0].update(scientific_pass=True),
    "fixture_claim_scope_field": lambda b: b.opportunities_ranked[0].update(claim_scope="empirical"),
    "scientific_status_in_metadata": lambda b: b.metadata.update(scientific_status="VALIDATED"),
}


@pytest.mark.parametrize("name", sorted(_FORGERIES))
def test_forged_batch_is_rejected_by_validate_and_planner(name):
    forged = _forge(_FORGERIES[name])
    assert forged.validate(), name
    with pytest.raises(OssOpportunityValidationError):
        plan_oss_integrations_from_opportunities(forged)


def test_invalid_license_review_identifier_cannot_be_scored():
    candidate = make_document_ingestion_candidate()
    review = _review(candidate)
    review.license_review_id = "forged-license-review-id"
    with pytest.raises(OssOpportunityValidationError, match="license_review_id"):
        score_opportunity(candidate, review)


def test_non_finite_score_components_are_rejected_before_json_serialization():
    forged = _forge(lambda batch: batch.opportunities_ranked[0]["score_components"].update(
        direct_product_leverage=float("nan")))
    assert any("score_components" in error for error in forged.validate())
    with pytest.raises(OssOpportunityValidationError):
        forged.to_json()


@pytest.mark.parametrize(
    "payload",
    [5, [], {"candidates_seen": "x"}, {"candidates_seen": float("nan")}, {"opportunities_ranked": 5}, {"metadata": [1]}],
)
def test_batch_from_dict_malformed_shapes_are_controlled(payload):
    with pytest.raises(OssOpportunityValidationError):
        OpenSourceLeverageBatchV1.from_dict(payload)


def test_batch_from_dict_does_not_coerce_boolean_candidate_count():
    payload = _ranked_batch().to_dict()
    payload["candidates_seen"] = True
    with pytest.raises(OssOpportunityValidationError, match="candidates_seen"):
        OpenSourceLeverageBatchV1.from_dict(payload)


def test_batch_from_dict_rejects_scientific_promotion_fields():
    payload = _ranked_batch().to_dict()
    payload["scientific_pass"] = True
    with pytest.raises(OssOpportunityValidationError, match="unsupported field"):
        OpenSourceLeverageBatchV1.from_dict(payload)


def test_batch_from_json_rejects_duplicate_license_keys():
    payload = _ranked_batch().to_json()
    needle = '"license_spdx": "MIT"'
    assert payload.count(needle) == 1
    payload = payload.replace(needle, '"license_spdx": "AGPL-3.0", ' + needle, 1)
    with pytest.raises(OssOpportunityValidationError, match="duplicate JSON key"):
        OpenSourceLeverageBatchV1.from_json(payload)


def test_manual_seed_rejects_duplicate_license_keys(tmp_path):
    seed = tmp_path / "duplicate-license-key.json"
    seed.write_text(
        '{"snapshot_date":"2026-10-23","repositories":[{"repo_full_name":"owner/repo",'
        '"license_spdx":"AGPL-3.0","license_spdx":"MIT"}]}',
        encoding="utf-8",
    )
    with pytest.raises(OssOpportunityValidationError, match="duplicate JSON key"):
        import_from_manual_seed(seed)


@pytest.mark.parametrize(
    ("loader", "payload"),
    [
        (import_from_trendshift_fixture, "[]"),
        (import_from_starmap_fixture, "[]"),
    ],
)
def test_snapshot_loaders_reject_non_mapping_payloads(loader, payload, tmp_path):
    path = tmp_path / "non-mapping.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(OssOpportunityValidationError, match="JSON object"):
        loader(path)


@pytest.mark.parametrize(
    ("loader", "payload"),
    [
        (import_from_trendshift_fixture, {"repositories": "owner/repo"}),
        (import_from_trendshift_fixture, {"repositories": [None]}),
        (import_from_trendshift_fixture, {"repositories": [{"name": "missing-repository-identity"}]}),
        (import_from_starmap_fixture, {"repositories": None}),
        (import_from_starmap_fixture, {"repositories": [5]}),
        (import_from_starmap_fixture, {"repositories": [{"name": "missing-repository-identity"}]}),
    ],
)
def test_snapshot_loaders_reject_malformed_repository_entries(loader, payload, tmp_path):
    path = tmp_path / "malformed-snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OssOpportunityValidationError):
        loader(path)


def test_manual_seed_does_not_silently_drop_missing_repository_identity(tmp_path):
    seed = tmp_path / "missing-repository.json"
    seed.write_text(json.dumps({"snapshot_date": "2026-10-23", "repositories": [{"license_spdx": "MIT"}]}))
    with pytest.raises(OssOpportunityValidationError, match="repo_full_name"):
        import_from_manual_seed(seed)


_BAD_SEEDS = {
    "list_payload": [],
    "entry_int": {"snapshot_date": "2026-10-01", "repositories": [5]},
    "entry_list": {"snapshot_date": "2026-10-01", "repositories": [["a/b"]]},
    "unknown_field": {"snapshot_date": "2026-10-01", "repositories": [{"repo_full_name": "a/b", "bogus_field": 1}]},
    "repositories_str": {"snapshot_date": "2026-10-01", "repositories": "a/b"},
    "non_string_name": {"snapshot_date": "2026-10-01", "repositories": [{"repo_full_name": 5}]},
}


@pytest.mark.parametrize("name", sorted(_BAD_SEEDS))
def test_malformed_manual_seed_is_a_controlled_failure_at_api_and_cli(name, tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps(_BAD_SEEDS[name]))
    with pytest.raises(OssOpportunityValidationError):
        import_from_manual_seed(seed)
    rc = cli_main(["from-manual-seed", "--seed", str(seed), "--out", str(tmp_path / "out")])
    assert rc == 1
