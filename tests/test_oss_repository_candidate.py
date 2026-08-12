from __future__ import annotations

from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1, compute_candidate_id
from tests._oss_opportunity_fixtures import make_document_ingestion_candidate, make_unknown_license_candidate


def test_valid_candidate_has_no_errors():
    c = make_document_ingestion_candidate()
    assert c.validate() == []


def test_candidate_id_deterministic():
    id1 = compute_candidate_id(repo_full_name="a/b", source="trendshift_daily", source_timeframe="daily", source_snapshot_date="2026-08-12")
    id2 = compute_candidate_id(repo_full_name="a/b", source="trendshift_daily", source_timeframe="daily", source_snapshot_date="2026-08-12")
    assert id1 == id2
    id3 = compute_candidate_id(repo_full_name="a/c", source="trendshift_daily", source_timeframe="daily", source_snapshot_date="2026-08-12")
    assert id1 != id3


def test_candidate_id_different_snapshot_date_differs():
    id1 = compute_candidate_id(repo_full_name="a/b", source="trendshift_daily", source_timeframe="daily", source_snapshot_date="2026-08-12")
    id2 = compute_candidate_id(repo_full_name="a/b", source="trendshift_daily", source_timeframe="daily", source_snapshot_date="2026-08-13")
    assert id1 != id2


def test_dict_roundtrip():
    c = make_document_ingestion_candidate()
    d = c.to_dict()
    c2 = OpenSourceRepositoryCandidateV1.from_dict(d)
    assert c2.to_dict() == d


def test_json_roundtrip():
    c = make_document_ingestion_candidate()
    c2 = OpenSourceRepositoryCandidateV1.from_json(c.to_json())
    assert c2.to_dict() == c.to_dict()


def test_missing_limitations_fails():
    c = make_document_ingestion_candidate()
    c.limitations = []
    errs = c.validate()
    assert any("limitations" in e for e in errs)


def test_missing_provenance_fails():
    c = make_document_ingestion_candidate()
    c.provenance = ""
    errs = c.validate()
    assert any("provenance" in e for e in errs)


def test_missing_source_fails():
    c = make_document_ingestion_candidate()
    c.source = ""
    errs = c.validate()
    assert any("source" in e for e in errs)


def test_invalid_source_fails():
    c = make_document_ingestion_candidate()
    c.source = "not_a_real_source"
    errs = c.validate()
    assert any("source" in e for e in errs)


def test_unknown_license_accepted_but_no_risk_field_on_candidate():
    c = make_unknown_license_candidate()
    errs = c.validate()
    assert errs == []
    assert c.license_spdx == "unknown"


def test_trendshift_signal_raw_payload_rejected():
    c = make_document_ingestion_candidate()
    c.source = "trendshift_signal"
    c.metadata = {"raw_response": {"some": "payload"}}
    errs = c.validate()
    assert any("rule 13" in e for e in errs)


def test_trendshift_signal_redistribution_flag_rejected():
    c = make_document_ingestion_candidate()
    c.source = "trendshift_signal"
    c.metadata = {"redistributes_raw_signal_data": True}
    errs = c.validate()
    assert any("rule 13" in e for e in errs)


def test_claim_scope_injected_via_setattr_fails():
    c = make_document_ingestion_candidate()
    setattr(c, "claim_scope", "confirmed")
    errs = c.validate()
    assert any("claim_scope" in e for e in errs)


def test_banned_phrase_in_description_fails():
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    c = make_document_ingestion_candidate()
    c.description = f"this {BANNED_REPORT_PHRASES[0]}"
    errs = c.validate()
    assert any("banned phrase" in e for e in errs)
