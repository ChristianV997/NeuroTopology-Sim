from __future__ import annotations

from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1, compute_opportunity_id
from oss_opportunities.license_review import RepositoryLicenseReviewV1, compute_license_review_id
from oss_opportunities.validation import (
    EXPECTED_SCORE_COMPONENTS,
    LICENSE_POLICY_VERSION,
    REQUIRED_BLOCKED_ACTIONS,
    validate_opportunity_against_license_review,
)


def _make(**overrides):
    kwargs = dict(
        repo_full_name="a/b", candidate_id="cand123",
        license_review_id=compute_license_review_id(repo_full_name="a/b", license_spdx="GPL-3.0"),
        leverage_category="document_ingestion", recommended_action="integrate_as_optional_adapter",
        blocked_actions=list(REQUIRED_BLOCKED_ACTIONS),
        score_components={name: 0.0 for name in EXPECTED_SCORE_COMPONENTS},
        total_score=0.0,
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
    components = {name: 0.0 for name in EXPECTED_SCORE_COMPONENTS}
    components["direct_product_leverage"] = 2.0
    components["license_safety"] = 3.0
    o = _make(score_components=components, total_score=99.0)
    errs = o.validate()
    assert any("total_score" in e for e in errs)


def test_component_sum_overflow_cannot_pass_with_finite_total():
    components = {name: 0.0 for name in sorted(EXPECTED_SCORE_COMPONENTS)}
    keys = list(components)
    for key, value in zip(keys[:4], (-1e308, -1e308, 1e308, 1e308)):
        components[key] = value
    opportunity = _make(score_components=components, total_score=0.0)
    assert any("score_components" in error or "total_score" in error for error in opportunity.validate())


def test_unhashable_enum_values_are_reported_not_raised():
    for override, field in (
        ({"leverage_category": []}, "leverage_category"),
        ({"recommended_action": {}}, "recommended_action"),
    ):
        errors = _make(**override).validate()
        assert any(field in error for error in errors)


def test_malformed_text_and_surface_fields_are_rejected():
    cases = (
        ({"limitations": "synthetic fixture only"}, "limitations"),
        ({"provenance": ["synthetic fixture"]}, "provenance"),
        ({"integration_surface": "adapter"}, "integration_surface"),
        ({"emulation_surface": [17]}, "emulation_surface"),
    )
    for overrides, field in cases:
        errors = _make(**overrides).validate()
        assert any(field in error for error in errors)


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
    kwargs = dict(
        repo_full_name="a/b", license_spdx="GPL-3.0", license_name="GPLv3",
        provenance="fixture", limitations=["synthetic"],
        commercial_core_policy="external_process_only",
        allowed_use_modes=["external_process_only", "docs_reference"],
        blocked_use_modes=["commercial_core_copy", "code_copy_of_any_kind"],
    )
    kwargs.update(overrides)
    return RepositoryLicenseReviewV1.make(license_policy_version=LICENSE_POLICY_VERSION, **kwargs)


def test_cross_check_fails_closed_for_non_copy_permitting_policy_mismatch():
    # Regression for a real gap: the cross-object check previously only
    # ran when commercial_core_policy was ALREADY copy-permitting, so a
    # mismatched pair like external_process_only/strong_copyleft_high
    # paired with integrate_as_optional_adapter silently passed.
    o = _make(recommended_action="integrate_as_optional_adapter")
    review = _review(commercial_core_policy="external_process_only")
    errs = validate_opportunity_against_license_review(o, review)
    assert any("rule 7/8" in e for e in errs)


def test_cross_check_fails_closed_for_docs_reference_only_mismatch():
    o = _make(recommended_action="integrate_as_optional_adapter")
    review = _review(
        license_spdx="BSL-1.1", commercial_core_policy="docs_reference_only",
        allowed_use_modes=["docs_reference", "external_process_only_if_terms_permit"],
        blocked_use_modes=["commercial_core_copy", "code_copy_of_any_kind", "resale_without_review"],
    )
    errs = validate_opportunity_against_license_review(o, review)
    assert any("rule 7/8" in e for e in errs)


def test_cross_check_passes_for_permissive_optional_adapter():
    review = _review(
        license_spdx="MIT", license_name="MIT", commercial_core_policy="allowed_with_attribution",
        allowed_use_modes=["adapter_only", "docs_reference", "attributed_snippet_copy"],
        blocked_use_modes=["unattributed_copy"],
    )
    o = _make(license_review_id=review.license_review_id, recommended_action="integrate_as_optional_adapter")
    assert validate_opportunity_against_license_review(o, review) == []


def test_cross_check_ignores_other_recommended_actions():
    review = _review(license_spdx="unknown", license_name="unknown", commercial_core_policy="blocked")
    o = _make(
        license_review_id=review.license_review_id,
        recommended_action="integrate_as_external_tool_record",
    )
    assert validate_opportunity_against_license_review(o, review) == []
