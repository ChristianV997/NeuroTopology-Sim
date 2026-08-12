from __future__ import annotations

import pytest

from dataset_opportunities.opportunity_batch import (
    DatasetOpportunityBatchV1,
    build_opportunities_from_candidates,
    compute_batch_id,
)
from dataset_opportunities.validation import DatasetOpportunityValidationError
from tests._dataset_opportunity_fixtures import make_blocked_candidate, make_good_candidate, make_sparse_candidate


def test_build_batch_ranks_good_above_blocked():
    good = make_good_candidate()
    blocked = make_blocked_candidate()
    batch = build_opportunities_from_candidates([good, blocked], query_summary="fixture test")
    assert batch.validate() == []
    assert batch.total_candidates_seen == 2
    assert batch.total_opportunities_ranked == 1
    assert len(batch.rejected_opportunities) == 1
    assert batch.ranked_opportunities[0]["source_dataset_id"] == "ds000123"


def test_no_candidate_silently_dropped():
    good = make_good_candidate()
    blocked = make_blocked_candidate()
    batch = build_opportunities_from_candidates([good, blocked], query_summary="fixture test")
    ranked_ids = {o["source_dataset_id"] for o in batch.ranked_opportunities}
    rejected_ids = {o["source_dataset_id"] for o in batch.rejected_opportunities}
    assert ranked_ids | rejected_ids == {"ds000123", "ds000999"}


def test_batch_id_deterministic():
    good = make_good_candidate()
    b1 = build_opportunities_from_candidates([good], query_summary="q")
    b2 = build_opportunities_from_candidates([good], query_summary="q")
    assert b1.batch_id == b2.batch_id


def test_compute_batch_id_direct():
    id1 = compute_batch_id(source_catalog="eegdash", query_summary="q", opportunity_ids=["a", "b"])
    id2 = compute_batch_id(source_catalog="eegdash", query_summary="q", opportunity_ids=["b", "a"])
    assert id1 == id2  # order-independent (sorted internally)


def test_dict_roundtrip():
    good = make_good_candidate()
    batch = build_opportunities_from_candidates([good], query_summary="q")
    d = batch.to_dict()
    b2 = DatasetOpportunityBatchV1.from_dict(d)
    assert b2.to_dict() == d


def test_empty_candidate_list_raises():
    with pytest.raises(DatasetOpportunityValidationError):
        build_opportunities_from_candidates([], query_summary="empty")


def test_invalid_candidate_raises():
    bad = make_good_candidate()
    bad.risks = []  # violates dataset_importers validation rule 3
    with pytest.raises(DatasetOpportunityValidationError):
        build_opportunities_from_candidates([bad], query_summary="q")


def test_top_n_limits_ranked_but_not_seen_count():
    a = make_good_candidate("ds000001")
    b = make_good_candidate("ds000002")
    batch = build_opportunities_from_candidates([a, b], query_summary="q", top_n=1)
    assert batch.total_candidates_seen == 2
    assert batch.total_opportunities_ranked == 1


def test_sparse_candidate_scored_and_included_or_rejected_not_dropped():
    sparse = make_sparse_candidate()
    batch = build_opportunities_from_candidates([sparse], query_summary="q")
    assert batch.total_candidates_seen == 1
    assert batch.total_opportunities_ranked + len(batch.rejected_opportunities) == 1


def test_total_ranked_matches_len_ranked_opportunities():
    good = make_good_candidate()
    batch = build_opportunities_from_candidates([good], query_summary="q")
    assert batch.total_opportunities_ranked == len(batch.ranked_opportunities)


def test_claim_scope_on_batch_fails_validation():
    good = make_good_candidate()
    batch = build_opportunities_from_candidates([good], query_summary="q")
    setattr(batch, "claim_scope", "confirmed")
    errs = batch.validate()
    assert any("claim_scope" in e for e in errs)
