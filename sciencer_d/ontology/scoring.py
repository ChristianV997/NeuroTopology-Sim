"""Scoring and conservative status gates for Level O claims."""

from __future__ import annotations

from collections.abc import Mapping

from .schemas import OntologyClaim, OntologyScore, SCORE_DIMENSIONS


SCORE_WEIGHTS = {
    "empirical_support": 0.30,
    "phenomenological_depth": 0.20,
    "metaphysical_coherence": 0.15,
    "falsifiability": 0.20,
    "btc_icft_relevance": 0.15,
    "risk_of_overclaim": -0.25,
}

STATUS_CEILINGS = {
    "O5_SOUL_IDENTITY_INVARIANT": "O-C",
    "O6_SURVIVAL_AFTER_DEATH": "O-C",
    "O7_FIELD_CONSCIOUSNESS": "O-B",
    "O8_PANPSYCHISM_NEUTRAL_MONISM": "O-C",
    "O10_HOLOGRAPHIC_HOLARCHY": "O-B",
    "O11_COSMIC_NATURAL_SELECTION": "O-C",
    "O12_THERAVADA_REALMS_STATE_SPACE": "O-C",
}

_PROMOTION_RANK = {"O-C": 0, "O-B": 1, "O-A": 2}


def composite_score(values: Mapping[str, float]) -> float:
    """Calculate the issue-defined Level O composite score."""
    normalized: dict[str, float] = {}
    for dimension in SCORE_DIMENSIONS:
        value = float(values.get(dimension, 0.0))
        if not 0 <= value <= 5:
            raise ValueError(f"{dimension} must be between 0 and 5")
        normalized[dimension] = value
    return sum(normalized[name] * SCORE_WEIGHTS[name] for name in SCORE_DIMENSIONS)


def classify_score(values: Mapping[str, float], *, firewall_rejected: bool = False) -> str:
    """Apply Level O gates without promoting from coherence alone."""
    if firewall_rejected:
        return "O-X"
    empirical = float(values.get("empirical_support", 0.0))
    falsifiability = float(values.get("falsifiability", 0.0))
    overclaim_risk = float(values.get("risk_of_overclaim", 0.0))
    composite = composite_score(values)
    if overclaim_risk >= 5 and empirical < 4:
        return "O-X"
    if composite >= 3.8 and empirical >= 4 and falsifiability >= 4:
        return "O-A"
    if composite >= 3.0 and falsifiability >= 3:
        return "O-B"
    return "O-C"


def apply_status_ceiling(claim_id: str, status: str) -> tuple[str, str | None]:
    """Clamp sensitive claims to their policy ceiling."""
    if status == "O-X":
        return status, None
    ceiling = STATUS_CEILINGS.get(claim_id)
    if ceiling and _PROMOTION_RANK[status] > _PROMOTION_RANK[ceiling]:
        return ceiling, f"policy_ceiling:{ceiling}"
    return status, None


def score_claim(claim: OntologyClaim, *, firewall_rejected: bool = False) -> OntologyScore:
    values = {dimension: claim.score_inputs.get(dimension, 0.0) for dimension in SCORE_DIMENSIONS}
    calculated = classify_score(values, firewall_rejected=firewall_rejected)
    status, ceiling_reason = apply_status_ceiling(claim.claim_id, calculated)
    reasons = [ceiling_reason] if ceiling_reason else []
    if firewall_rejected:
        reasons.append("firewall_rejected")
    return OntologyScore(
        claim_id=claim.claim_id,
        **values,
        composite=round(composite_score(values), 4),
        status=status,
        gate_reasons=reasons,
    )
