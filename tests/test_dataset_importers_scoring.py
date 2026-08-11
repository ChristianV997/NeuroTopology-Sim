"""Candidate scoring: planning heuristics only, never evidence. Synthetic
fixtures only.
"""
from __future__ import annotations

from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_importers.scoring import CandidateScore, rank_candidates, score_candidate


def _record(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-1"),
        display_name="Fixture dataset",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        download_required="true",
        modalities=["EEG"],
        condition_labels=["a", "b"],
        subject_count=10,
        available_metadata=["subject_count", "license"],
        transition_readiness="candidate_transition_possible",
        benchmark_role_recommendation="development_candidate",
        compatible_adapters=["adapters.mne_bids"],
        risks=["r"],
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetCandidateRecordV1.make(**kwargs)


def test_public_permissive_explicit_condition_candidate_ranks_higher():
    strong = _record(source_dataset_id="strong")
    weak = _record(
        source_dataset_id="weak",
        license="unknown",
        license_risk="unknown_high",
        access_status="unknown",
        condition_labels=[],
        subject_count=None,
        transition_readiness="blocked_missing_metadata",
        benchmark_role_recommendation="blocked",
    )
    ranked = rank_candidates([weak, strong])
    assert ranked[0].candidate_id == strong.candidate_id
    assert ranked[0].total_score > ranked[1].total_score


def test_unknown_license_and_access_candidate_ranks_lower():
    known = _record(source_dataset_id="known")
    unknown = _record(source_dataset_id="unknown_ds", license="unknown", license_risk="unknown_high", access_status="unknown")
    score_known = score_candidate(known)
    score_unknown = score_candidate(unknown)
    assert score_unknown.total_score < score_known.total_score
    assert score_unknown.license_score == 0
    assert score_unknown.access_score == 0


def test_restricted_access_blocks_high_ranking():
    strong_but_restricted = _record(
        source_dataset_id="restricted",
        access_status="restricted",
        transition_readiness="blocked_license_or_access",
        benchmark_role_recommendation="blocked",
    )
    modest_public = _record(
        source_dataset_id="modest",
        condition_labels=[],
        subject_count=None,
        transition_readiness="explicit_condition_mapping_needed",
        benchmark_role_recommendation="exploration_candidate",
    )
    ranked = rank_candidates([strong_but_restricted, modest_public])
    assert ranked[0].candidate_id == modest_public.candidate_id
    restricted_score = next(s for s in ranked if s.candidate_id == strong_but_restricted.candidate_id)
    assert restricted_score.total_score <= 3


def test_metadata_only_is_not_treated_as_evidence():
    """A candidate score is a planning heuristic -- it never implies the
    candidate itself is evidence, regardless of how high it ranks."""
    strong = _record(source_dataset_id="strong2")
    score = score_candidate(strong)
    assert isinstance(score, CandidateScore)
    # The score object carries no evidence-shaped field (no claim_scope,
    # no evidence_level, no null_control) -- only planning heuristics.
    d = score.to_dict()
    for forbidden_key in ("claim_scope", "evidence_level", "null_control_summary"):
        assert forbidden_key not in d


def test_score_rationale_non_empty():
    rec = _record()
    score = score_candidate(rec)
    assert score.rationale
    assert all(isinstance(r, str) and r for r in score.rationale)


def test_bids_mne_compatibility_improves_score():
    with_adapter = _record(source_dataset_id="with_adapter", compatible_adapters=["adapters.mne_bids"])
    without_adapter = _record(source_dataset_id="without_adapter", compatible_adapters=[])
    s_with = score_candidate(with_adapter)
    s_without = score_candidate(without_adapter)
    assert s_with.adapter_fit_score > s_without.adapter_fit_score
    assert s_with.total_score > s_without.total_score


def test_unsupported_modality_penalizes():
    supported = _record(source_dataset_id="supported_modality", modalities=["EEG"])
    unsupported = _record(
        source_dataset_id="unsupported_modality",
        modalities=["fnirs-nonstandard-label"],
        transition_readiness="blocked_unsupported_modality",
        benchmark_role_recommendation="blocked",
    )
    s_supported = score_candidate(supported)
    s_unsupported = score_candidate(unsupported)
    assert s_unsupported.modality_score == 0
    assert s_unsupported.risk_penalty > 0
    assert s_unsupported.total_score < s_supported.total_score


def test_rank_candidates_deterministic_tie_break():
    a = _record(source_dataset_id="tie-a")
    b = _record(source_dataset_id="tie-b")
    ranked_1 = rank_candidates([a, b])
    ranked_2 = rank_candidates([b, a])
    assert [s.candidate_id for s in ranked_1] == [s.candidate_id for s in ranked_2]
