"""Opportunity scoring -- wraps `dataset_importers.scoring.score_candidate`
rather than reimplementing an additive heuristic from scratch. A
`DatasetCandidateRecordV1` has already been scored once (license/access/
metadata/transition/modality/adapter-fit + risk penalty, deterministic,
tie-broken ranking) by that module; this module translates that
already-computed `CandidateScore` plus the source candidate record into the
richer opportunity vocabulary (`state_mapping_potential`,
`transition_analysis_potential`, `benchmark_pack_potential`,
`literature_link_potential`, `outreach_potential`,
`commercial_demo_potential`, `recommended_next_actions`, `blocked_actions`).

Like `dataset_importers.scoring`, this is a simple, documented, additive
heuristic -- not a scored/weighted model, not a scientific judgment of
dataset quality or clinical relevance.
"""
from __future__ import annotations

from typing import Any

from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_importers.scoring import CandidateScore, score_candidate
from dataset_opportunities.validation import REQUIRED_BLOCKED_ACTIONS

_UNKNOWN_SIGNAL_ACCESS = frozenset({"unknown", "restricted"})


def _potential_from_score(component_score: float, *, blocked: bool) -> str:
    if blocked:
        return "not_applicable"
    if component_score >= 2.0:
        return "high"
    if component_score >= 1.0:
        return "moderate"
    if component_score > 0.0:
        return "low"
    return "insufficient_data"


def score_opportunity(candidate: DatasetCandidateRecordV1) -> dict[str, Any]:
    """Return a plain dict (never a partially-built dataclass) with every
    field `dataset_opportunities.opportunity_batch.build_opportunities_from_candidates`
    needs to construct a `DatasetOpportunityRecordV1` -- keeps this function
    trivially unit-testable without importing the schema module."""
    candidate_score: CandidateScore = score_candidate(candidate)
    blocked = candidate.transition_readiness.startswith("blocked_")

    unknown_signal = (
        candidate.access_status in _UNKNOWN_SIGNAL_ACCESS
        or candidate.license_risk == "unknown_high"
    )

    # Component translation -- transparent, each traceable back to a single
    # CandidateScore field or a directly-observable candidate field.
    modality_relevance = candidate_score.modality_score
    task_state_relevance = 1.0 if candidate.task_labels else 0.0
    metadata_completeness = candidate_score.metadata_score
    access_license_safety = candidate_score.license_score + candidate_score.access_score
    bids_or_loadability_signal = 0.5 if "bids" in [m.lower() for m in candidate.available_metadata] else 0.0
    participant_or_duration_signal = 0.5 if candidate.subject_count is not None else 0.0
    mapping_feasibility = 1.0 if candidate.condition_labels else 0.0
    adapter_compatibility = candidate_score.adapter_fit_score
    benchmark_pack_usefulness = 1.0 if (candidate.task_labels and not blocked) else 0.0
    literature_link_usefulness = 0.5 if candidate.public_url or candidate.documentation_url else 0.0

    # outreach_potential requires an explicit identifier (public/repo/doc
    # URL) or an author/contact metadata field -- never inferred from a
    # dataset name alone.
    has_identifier = bool(candidate.public_url or candidate.repository_url or candidate.documentation_url)
    has_contact_metadata = any(
        key in (candidate.metadata or {}) for key in ("authors", "contact", "contact_email", "pi", "corresponding_author")
    )
    outreach_relevance = 1.0 if (has_identifier or has_contact_metadata) else 0.0

    risk_penalty = candidate_score.risk_penalty

    score_components = {
        "modality_relevance": round(modality_relevance, 2),
        "task_state_relevance": round(task_state_relevance, 2),
        "metadata_completeness": round(metadata_completeness, 2),
        "access_license_safety": round(access_license_safety, 2),
        "bids_or_loadability_signal": round(bids_or_loadability_signal, 2),
        "participant_or_duration_signal": round(participant_or_duration_signal, 2),
        "mapping_feasibility": round(mapping_feasibility, 2),
        "adapter_compatibility": round(adapter_compatibility, 2),
        "benchmark_pack_usefulness": round(benchmark_pack_usefulness, 2),
        "literature_link_usefulness": round(literature_link_usefulness, 2),
        "outreach_relevance": round(outreach_relevance, 2),
        "risk_penalty": round(-risk_penalty, 2),
    }
    total_score = round(sum(score_components.values()), 2)

    state_mapping_potential = _potential_from_score(mapping_feasibility + task_state_relevance, blocked=blocked)
    transition_analysis_potential = _potential_from_score(
        2.0 if candidate.transition_readiness == "candidate_transition_possible"
        else (1.0 if candidate.transition_readiness in ("explicit_condition_mapping_needed", "derived_feature_extraction_needed") else 0.0),
        blocked=blocked,
    )
    benchmark_pack_potential = _potential_from_score(benchmark_pack_usefulness + adapter_compatibility, blocked=blocked)
    literature_link_potential = _potential_from_score(literature_link_usefulness, blocked=False)
    commercial_demo_potential = _potential_from_score(
        modality_relevance + (1.0 if candidate.benchmark_role_recommendation == "development_candidate" else 0.0),
        blocked=blocked,
    )

    if not (has_identifier or has_contact_metadata):
        outreach_potential = "insufficient_data"
    else:
        outreach_potential = _potential_from_score(outreach_relevance, blocked=False)

    recommended_next_actions: list[str] = []
    execution_ok = not unknown_signal and not blocked
    if metadata_completeness > 0:
        recommended_next_actions.append("metadata_review")
    if execution_ok and candidate.transition_readiness == "candidate_transition_possible":
        recommended_next_actions.append("acquisition_plan_only")
    if execution_ok and mapping_feasibility == 0 and candidate.task_labels:
        recommended_next_actions.append("mapping_feasibility_review")
    if execution_ok and benchmark_pack_potential in ("moderate", "high"):
        recommended_next_actions.append("benchmark_pack_proposal")
    if literature_link_potential in ("moderate", "high"):
        recommended_next_actions.append("literature_review_task")
    if outreach_potential in ("moderate", "high"):
        recommended_next_actions.append("researcher_outreach_candidate")
    if blocked:
        recommended_next_actions.append("reject")
    if not recommended_next_actions:
        recommended_next_actions.append("defer")
    recommended_next_actions.append("candidate_curation")
    # De-duplicate while preserving first-seen order (deterministic).
    seen: set[str] = set()
    deduped: list[str] = []
    for action in recommended_next_actions:
        if action not in seen:
            seen.add(action)
            deduped.append(action)
    recommended_next_actions = deduped

    blocked_actions = sorted(REQUIRED_BLOCKED_ACTIONS)

    risk_flags: list[str] = []
    if unknown_signal:
        risk_flags.append("unknown_or_restricted_access_or_license")
    if blocked:
        risk_flags.append(f"candidate_transition_readiness={candidate.transition_readiness}")
    if not candidate.task_labels:
        risk_flags.append("no_task_labels_available")

    return {
        "score_components": score_components,
        "total_score": total_score,
        "state_mapping_potential": state_mapping_potential,
        "transition_analysis_potential": transition_analysis_potential,
        "benchmark_pack_potential": benchmark_pack_potential,
        "literature_link_potential": literature_link_potential,
        "outreach_potential": outreach_potential,
        "commercial_demo_potential": commercial_demo_potential,
        "recommended_next_actions": recommended_next_actions,
        "blocked_actions": blocked_actions,
        "risk_flags": risk_flags,
    }
