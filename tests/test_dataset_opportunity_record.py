from __future__ import annotations

from dataset_opportunities.opportunity_record import DatasetOpportunityRecordV1, compute_opportunity_id
from dataset_opportunities.validation import REQUIRED_BLOCKED_ACTIONS


def _make_valid_record(**overrides):
    kwargs = dict(
        source_catalog="eegdash",
        source_dataset_id="ds000123",
        source_candidate_id="abc123",
        dataset_name="Test Dataset",
        modality="EEG",
        access_status="public",
        license="CC0",
        license_risk="permissive_low",
        recommended_next_actions=["metadata_review"],
        blocked_actions=list(REQUIRED_BLOCKED_ACTIONS),
        score_components={"modality_relevance": 1.0, "access_license_safety": 2.0},
        total_score=3.0,
        limitations=["metadata-only scouting record, not evidence"],
        provenance="synthetic fixture",
    )
    kwargs.update(overrides)
    return DatasetOpportunityRecordV1.make(**kwargs)


def test_valid_record_has_no_errors():
    r = _make_valid_record()
    assert r.validate() == []


def test_opportunity_id_deterministic():
    id1 = compute_opportunity_id(source_catalog="eegdash", source_dataset_id="ds1", source_candidate_id="c1")
    id2 = compute_opportunity_id(source_catalog="eegdash", source_dataset_id="ds1", source_candidate_id="c1")
    assert id1 == id2
    id3 = compute_opportunity_id(source_catalog="eegdash", source_dataset_id="ds2", source_candidate_id="c1")
    assert id1 != id3


def test_opportunity_id_excludes_timestamp():
    r1 = _make_valid_record()
    r2 = _make_valid_record()
    assert r1.opportunity_id == r2.opportunity_id
    assert r1.created_at != "" and r2.created_at != ""


def test_dict_roundtrip():
    r = _make_valid_record()
    d = r.to_dict()
    r2 = DatasetOpportunityRecordV1.from_dict(d)
    assert r2.to_dict() == d


def test_json_roundtrip():
    r = _make_valid_record()
    text = r.to_json()
    r2 = DatasetOpportunityRecordV1.from_json(text)
    assert r2.to_dict() == r.to_dict()


def test_missing_limitations_fails():
    r = _make_valid_record(limitations=[])
    errs = r.validate()
    assert any("limitations" in e for e in errs)


def test_missing_provenance_fails():
    r = _make_valid_record(provenance="")
    errs = r.validate()
    assert any("provenance" in e for e in errs)


def test_missing_source_candidate_fails():
    r = _make_valid_record()
    r.source_candidate_id = ""
    errs = r.validate()
    assert any("source_candidate_id" in e for e in errs)


def test_total_score_must_equal_sum_of_components():
    r = _make_valid_record(score_components={"a": 1.0, "b": 1.0}, total_score=5.0)
    errs = r.validate()
    assert any("total_score" in e for e in errs)


def test_invalid_recommended_action_fails():
    r = _make_valid_record(recommended_next_actions=["not_a_real_action"])
    errs = r.validate()
    assert any("recommended_next_actions" in e for e in errs)


def test_missing_required_blocked_action_fails():
    r = _make_valid_record(blocked_actions=["direct_evidence_claim"])
    errs = r.validate()
    assert any("blocked_actions" in e for e in errs)


def test_claim_scope_injected_via_setattr_fails():
    r = _make_valid_record()
    object.__setattr__(r, "claim_scope", "confirmed") if False else setattr(r, "claim_scope", "confirmed")
    errs = r.validate()
    assert any("claim_scope" in e for e in errs)


def test_unknown_access_blocks_execution_oriented_actions():
    r = _make_valid_record(access_status="unknown", recommended_next_actions=["acquisition_plan_only"])
    errs = r.validate()
    assert any("rule 12" in e for e in errs)


def test_restricted_access_blocks_execution_oriented_actions():
    r = _make_valid_record(access_status="restricted", recommended_next_actions=["benchmark_pack_proposal"])
    errs = r.validate()
    assert any("rule 12" in e for e in errs)


def test_unknown_license_blocks_execution_oriented_actions():
    r = _make_valid_record(access_status="public", license_risk="unknown_high", recommended_next_actions=["local_availability_check"])
    errs = r.validate()
    assert any("rule 12" in e for e in errs)


def test_banned_phrase_in_dataset_name_fails():
    # Sourced from the canonical list rather than hardcoded, so this tests the
    # real firewall and does not itself plant banned text in the repository.
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    r = _make_valid_record(dataset_name=f"this {BANNED_REPORT_PHRASES[0]}")
    errs = r.validate()
    assert any("banned phrase" in e for e in errs)
