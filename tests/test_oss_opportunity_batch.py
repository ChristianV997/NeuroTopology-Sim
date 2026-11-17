from __future__ import annotations

import pytest

from oss_opportunities.opportunity_batch import (
    OpenSourceLeverageBatchV1,
    build_opportunities_from_candidates,
    compute_batch_id,
)
from oss_opportunities.validation import OssOpportunityValidationError
from tests._oss_opportunity_fixtures import (
    make_document_ingestion_candidate,
    make_frontend_stack_candidate,
    make_sparse_candidate,
)


def test_build_batch_ranks_deterministically():
    good = make_document_ingestion_candidate()
    sparse = make_sparse_candidate()
    batch = build_opportunities_from_candidates([good, sparse])
    assert batch.validate() == []
    assert batch.candidates_seen == 2
    # The sparse candidate has an unresolved (unknown) license, so it is
    # surfaced for license review rather than silently rejected.
    assert len(batch.opportunities_ranked) == 2
    assert batch.opportunities_rejected == []
    assert batch.opportunities_ranked[0]["repo_full_name"] == good.repo_full_name
    assert batch.opportunities_ranked[1]["recommended_action"] == "license_review_required"


def test_no_candidate_silently_dropped():
    good = make_document_ingestion_candidate()
    sparse = make_sparse_candidate()
    batch = build_opportunities_from_candidates([good, sparse])
    ranked_ids = {e["repo_full_name"] for e in batch.opportunities_ranked}
    rejected_ids = {e["repo_full_name"] for e in batch.opportunities_rejected}
    assert ranked_ids | rejected_ids == {good.repo_full_name, sparse.repo_full_name}


def test_batch_id_deterministic():
    good = make_document_ingestion_candidate()
    b1 = build_opportunities_from_candidates([good])
    b2 = build_opportunities_from_candidates([good])
    assert b1.batch_id == b2.batch_id


def test_compute_batch_id_direct():
    id1 = compute_batch_id(opportunity_ids=["a", "b"], sources_scanned=["trendshift_daily"])
    id2 = compute_batch_id(opportunity_ids=["b", "a"], sources_scanned=["trendshift_daily"])
    assert id1 == id2


def test_dict_roundtrip():
    good = make_document_ingestion_candidate()
    batch = build_opportunities_from_candidates([good])
    d = batch.to_dict()
    b2 = OpenSourceLeverageBatchV1.from_dict(d)
    assert b2.to_dict() == d


def test_empty_candidate_list_raises():
    with pytest.raises(OssOpportunityValidationError):
        build_opportunities_from_candidates([])


def test_invalid_candidate_raises():
    bad = make_document_ingestion_candidate()
    bad.limitations = []
    with pytest.raises(OssOpportunityValidationError):
        build_opportunities_from_candidates([bad])


def test_top_n_limits_ranked_but_not_seen_count():
    a = make_document_ingestion_candidate("a/repo1")
    b = make_document_ingestion_candidate("a/repo2")
    batch = build_opportunities_from_candidates([a, b], top_n=1)
    assert batch.candidates_seen == 2
    assert len(batch.opportunities_ranked) == 1
    assert len(batch.opportunities_rejected) == 1
    assert batch.opportunities_rejected[0]["reason"].startswith("top_n_limit:")
    assert batch.validate() == []


def _unknown_license_document_candidate(repo_full_name):
    candidate = make_document_ingestion_candidate(repo_full_name)
    candidate.owner = repo_full_name.split("/", 1)[0]
    candidate.name = repo_full_name.split("/", 1)[1]
    candidate.license_spdx = "unknown"
    candidate.license_name = "unknown"
    candidate.candidate_id = candidate.recompute_id()
    return candidate


def test_top_n_never_hides_unresolved_license_reviews():
    candidates = [
        _unknown_license_document_candidate("org/one"),
        _unknown_license_document_candidate("org/two"),
    ]
    batch = build_opportunities_from_candidates(candidates, top_n=1)
    assert {entry["repo_full_name"] for entry in batch.opportunities_ranked} == {"org/one", "org/two"}
    assert all(entry["recommended_action"] == "license_review_required" for entry in batch.opportunities_ranked)
    assert batch.opportunities_rejected == []


@pytest.mark.parametrize("top_n", [-1, True, 1.5, "1"])
def test_top_n_rejects_invalid_limits(top_n):
    with pytest.raises(OssOpportunityValidationError, match="top_n"):
        build_opportunities_from_candidates([make_document_ingestion_candidate()], top_n=top_n)


def test_top_by_category_and_action_lists_populated():
    good = make_document_ingestion_candidate()
    frontend = make_frontend_stack_candidate()
    batch = build_opportunities_from_candidates([good, frontend])
    assert good.repo_full_name in batch.top_by_category.get("document_ingestion", [])
    assert frontend.repo_full_name in batch.top_by_category.get("frontend_stack", [])
    assert good.repo_full_name in batch.top_immediate_adapters
    assert frontend.repo_full_name in batch.top_architecture_emulation


def test_claim_scope_on_batch_fails_validation():
    good = make_document_ingestion_candidate()
    batch = build_opportunities_from_candidates([good])
    setattr(batch, "claim_scope", "confirmed")
    errs = batch.validate()
    assert any("claim_scope" in e for e in errs)


def test_no_dependency_installation_or_execution_in_ranked_output():
    good = make_document_ingestion_candidate()
    batch = build_opportunities_from_candidates([good])
    for entry in batch.opportunities_ranked:
        for action in ("auto_install_dependency", "execute_untrusted_code"):
            assert action in entry["blocked_actions"]
