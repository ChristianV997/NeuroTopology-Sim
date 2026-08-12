from __future__ import annotations

from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1, compute_opportunity_id
from oss_opportunities.validation import REQUIRED_BLOCKED_ACTIONS


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
