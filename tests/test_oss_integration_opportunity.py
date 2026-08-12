from __future__ import annotations

from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1, compute_opportunity_id
from oss_opportunities.license_review import RepositoryLicenseReviewV1
from oss_opportunities.validation import REQUIRED_BLOCKED_ACTIONS, validate_opportunity_against_license_review


def _make(**overrides):
    kwargs = dict(
        repo_full_name="a/b", candidate_id="cand123", license_review_id="lic123",
        leverage_category="document_ingestion", recommended_action="integrate_as_optional_adapter",
        blocked_actions=list(REQUIRED_BLOCKED_ACTIONS),
        score_components={"direct_product_leverage": 2.0, "license_safety": 3.0},
        total_score=5.0,
        limitations=["synthetic fixture only"], provenance="synthetic fixture",
    )
    kwargs.update(overrides)
    return OpenSourceIntegrationOpportunityV1.make(**kwargs)


def test_valid_opportunity_has_no_errors():
    o = _make()
    assert o.validate() == []


def test_opportunity_id_deterministic():
    id1 = compute_opportunity_id(repo_full_name="a/b", candidate_id="c1")
    id2 = compute_opportunity_id(repo_full_name="a/b", candidate_id="c1")
    assert id1 == id2
    id3 = compute_opportunity_id(repo_full_name="a/c", candidate_id="c1")
    assert id1 != id3


def test_dict_roundtrip():
    o = _make()
    d = o.to_dict()
    o2 = OpenSourceIntegrationOpportunityV1.from_dict(d)
    assert o2.to_dict() == d


def test_missing_blocked_actions_fails():
    o = _make(blocked_actions=["copy_code_without_license_review"])
    errs = o.validate()
    assert any("blocked_actions" in e for e in errs)


def test_total_score_must_equal_sum_of_components():
    o = _make(score_components={"a": 1.0, "b": 1.0}, total_score=5.0)
    errs = o.validate()
    assert any("total_score" in e for e in errs)


def test_invalid_leverage_category_fails():
    o = _make(leverage_category="not_a_real_category")
    errs = o.validate()
    assert any("leverage_category" in e for e in errs)


def test_invalid_recommended_action_fails():
    o = _make(recommended_action="not_a_real_action")
    errs = o.validate()
    assert any("recommended_action" in e for e in errs)


def test_missing_candidate_or_license_review_id_fails():
    o = _make(candidate_id="")
    assert any("candidate_id" in e for e in o.validate())
    o2 = _make(license_review_id="")
    assert any("license_review_id" in e for e in o2.validate())


def test_claim_scope_injected_via_setattr_fails():
    o = _make()
    setattr(o, "evidence_level", "confirmed")
    errs = o.validate()
    assert any("evidence_level" in e for e in errs)


def test_missing_limitations_fails():
    o = _make(limitations=[])
    assert any("limitations" in e for e in o.validate())


def _review(**overrides):
    # Built via the raw dataclass constructor (not .make()) so tests can
    # freely set arbitrary (commercial_core_policy, license_risk)
    # combinations -- including tampered/mismatched ones -- to exercise
    # the cross-object check. .make() derives license_risk from
    # license_spdx and does not accept it as a direct override.
    kwargs = dict(
        repo_full_name="a/b", license_spdx="GPL-3.0", license_name="GPLv3",
        provenance="fixture", limitations=["synthetic"],
        commercial_core_policy="external_process_only", license_risk="strong_copyleft_high",
        allowed_use_modes=["external_process_only"], blocked_use_modes=["commercial_core_copy"],
    )
    kwargs.update(overrides)
    return RepositoryLicenseReviewV1(license_review_id="fixed-test-id", **kwargs)


def test_cross_check_fails_closed_for_non_copy_permitting_policy_mismatch():
    # Regression for a real gap: the cross-object check previously only
    # ran when commercial_core_policy was ALREADY copy-permitting, so a
    # mismatched pair like external_process_only/strong_copyleft_high
    # paired with integrate_as_optional_adapter silently passed.
    o = _make(recommended_action="integrate_as_optional_adapter")
    review = _review(commercial_core_policy="external_process_only", license_risk="strong_copyleft_high")
    errs = validate_opportunity_against_license_review(o, review)
    assert any("rule 7/8" in e for e in errs)


def test_cross_check_fails_closed_for_docs_reference_only_mismatch():
    o = _make(recommended_action="integrate_as_optional_adapter")
    review = _review(commercial_core_policy="docs_reference_only", license_risk="source_available_or_fair_code_high")
    errs = validate_opportunity_against_license_review(o, review)
    assert any("rule 7/8" in e for e in errs)


def test_cross_check_passes_for_permissive_optional_adapter():
    o = _make(recommended_action="integrate_as_optional_adapter")
    review = _review(commercial_core_policy="allowed_with_attribution", license_risk="permissive_low")
    assert validate_opportunity_against_license_review(o, review) == []


def test_cross_check_ignores_other_recommended_actions():
    o = _make(recommended_action="integrate_as_external_tool_record")
    review = _review(commercial_core_policy="blocked", license_risk="missing_high")
    assert validate_opportunity_against_license_review(o, review) == []
