"""Candidate scoring -- planning heuristics only, never evidence.

`score_candidate`/`rank_candidates` produce a `CandidateScore`: a simple,
documented, additive heuristic (mirrors
`external_tools.registry.ExternalToolRegistry.recommended_next`'s own
"simple, documented, four-key sort -- not a scored/weighted model" stance).
Nothing here evaluates scientific/clinical validity; it only estimates how
much *scouting* work a candidate still needs before it could feed a real
adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dataset_importers.candidate_record import DatasetCandidateRecordV1, SUPPORTED_MODALITIES

_LICENSE_SCORE: dict[str, int] = {
    "permissive_low": 3,
    "copyleft_medium": 1,
    "agpl_high": 0,
    "proprietary_high": 0,
    "unknown_high": 0,
}

_ACCESS_SCORE: dict[str, int] = {
    "public": 3,
    "public_requires_download": 2,
    "requires_registration": 1,
    "restricted": 0,
    "unknown": 0,
}

_TRANSITION_SCORE: dict[str, int] = {
    "candidate_transition_possible": 3,
    "explicit_condition_mapping_needed": 1,
    "derived_feature_extraction_needed": 1,
    "metadata_only": 0,
    "blocked_missing_metadata": -1,
    "blocked_license_or_access": -2,
    "blocked_unsupported_modality": -2,
}

# A candidate ranked "restricted" access is capped here regardless of every
# other component score (mission Phase E: "restricted access blocks high
# ranking").
_RESTRICTED_ACCESS_SCORE_CAP = 3


@dataclass
class CandidateScore:
    candidate_id: str
    total_score: float
    license_score: float
    access_score: float
    metadata_score: float
    transition_score: float
    modality_score: float
    adapter_fit_score: float
    risk_penalty: float
    recommended_next_action: str
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "total_score": self.total_score,
            "license_score": self.license_score,
            "access_score": self.access_score,
            "metadata_score": self.metadata_score,
            "transition_score": self.transition_score,
            "modality_score": self.modality_score,
            "adapter_fit_score": self.adapter_fit_score,
            "risk_penalty": self.risk_penalty,
            "recommended_next_action": self.recommended_next_action,
            "rationale": list(self.rationale),
        }


def score_candidate(record: DatasetCandidateRecordV1) -> CandidateScore:
    rationale: list[str] = []

    license_score = float(_LICENSE_SCORE.get(record.license_risk, 0))
    rationale.append(f"license_risk={record.license_risk} -> license_score={license_score}")

    access_score = float(_ACCESS_SCORE.get(record.access_status, 0))
    rationale.append(f"access_status={record.access_status} -> access_score={access_score}")

    metadata_score = 0.0
    if record.task_labels:
        metadata_score += 1
    if record.condition_labels:
        metadata_score += 1.5
        rationale.append(f"{len(record.condition_labels)} explicit condition label(s) -> +1.5 metadata_score")
    if record.subject_count is not None:
        metadata_score += 1
    if record.modalities:
        metadata_score += 0.5
    if record.available_metadata:
        metadata_score += 1
    rationale.append(f"metadata_score={metadata_score}")

    transition_score = float(_TRANSITION_SCORE.get(record.transition_readiness, 0))
    rationale.append(f"transition_readiness={record.transition_readiness} -> transition_score={transition_score}")

    supported = {m.strip().upper() for m in record.modalities} & SUPPORTED_MODALITIES
    unsupported = bool(record.modalities) and not supported
    modality_score = 1.0 if supported else 0.0
    if unsupported:
        rationale.append(f"modalities={record.modalities} contain no adapter-supported modality -> risk penalty")
    else:
        rationale.append(f"modality_score={modality_score}")

    adapter_fit_score = min(2.0, float(len(record.compatible_adapters)))
    if record.compatible_adapters:
        rationale.append(f"compatible_adapters={record.compatible_adapters} -> adapter_fit_score={adapter_fit_score}")

    risk_penalty = 0.0
    if record.license_risk == "unknown_high":
        risk_penalty += 2
    if record.access_status in ("restricted", "unknown"):
        risk_penalty += 2
    if record.transition_readiness.startswith("blocked_"):
        risk_penalty += 3
    if unsupported:
        risk_penalty += 2
    if risk_penalty:
        rationale.append(f"risk_penalty={risk_penalty}")

    total_score = (
        license_score
        + access_score
        + metadata_score
        + transition_score
        + modality_score
        + adapter_fit_score
        - risk_penalty
    )

    if record.access_status == "restricted":
        capped = min(total_score, _RESTRICTED_ACCESS_SCORE_CAP)
        if capped != total_score:
            rationale.append(f"access_status=restricted caps total_score at {_RESTRICTED_ACCESS_SCORE_CAP}")
        total_score = capped

    return CandidateScore(
        candidate_id=record.candidate_id,
        total_score=round(total_score, 2),
        license_score=license_score,
        access_score=access_score,
        metadata_score=metadata_score,
        transition_score=transition_score,
        modality_score=modality_score,
        adapter_fit_score=adapter_fit_score,
        risk_penalty=risk_penalty,
        recommended_next_action=record.recommended_next_action,
        rationale=rationale,
    )


def rank_candidates(records: list[DatasetCandidateRecordV1]) -> list[CandidateScore]:
    """Descending by total_score, tie-broken by candidate_id for a
    deterministic order regardless of input ordering."""
    scores = [score_candidate(r) for r in records]
    scores.sort(key=lambda s: (-s.total_score, s.candidate_id))
    return scores
