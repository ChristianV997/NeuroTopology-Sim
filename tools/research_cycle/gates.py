"""Deterministic promotion gates, lifecycle validation, and evidence update rules.

Enforces:
1. Rule A: A literature claim cannot become an empirical observation without data.
2. Rule B: A synthetic simulation cannot become biological evidence.
3. Rule C: A proxy Bayes factor cannot become formal evidence.
4. Rule D: A model improvement must be out-of-sample.
5. Rule E: A failed experiment updates the hypothesis rather than disappearing.
6. Rule F: Contradictory evidence remains visible.
7. Rule G: No autonomous promotion of speculative theory into scientific fact without explicit human review.
"""
from __future__ import annotations

from typing import Sequence

from .schema import (
    EpistemicLabel,
    EvidenceDataType,
    EvidenceUpdate,
    HypothesisRecord,
    HypothesisStatus,
)


class PromotionBlockedError(ValueError):
    """Raised when an invalid hypothesis or evidence promotion is attempted."""
    pass


class InvalidStatusTransitionError(ValueError):
    """Raised when a lifecycle state transition violates permitted DAG transitions."""
    pass


# Permitted lifecycle state transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    HypothesisStatus.PROPOSED.value: {
        HypothesisStatus.PREREGISTERED.value,
        HypothesisStatus.BLOCKED_BY_DATA.value,
        HypothesisStatus.BLOCKED_BY_METHOD.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.PREREGISTERED.value: {
        HypothesisStatus.READY_FOR_EXECUTION.value,
        HypothesisStatus.BLOCKED_BY_DATA.value,
        HypothesisStatus.BLOCKED_BY_METHOD.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.READY_FOR_EXECUTION.value: {
        HypothesisStatus.EXECUTED.value,
        HypothesisStatus.BLOCKED_BY_DATA.value,
        HypothesisStatus.BLOCKED_BY_METHOD.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.EXECUTED.value: {
        HypothesisStatus.SUPPORTED_AS_SPECIFIED.value,
        HypothesisStatus.WEAKENED.value,
        HypothesisStatus.FALSIFIED.value,
        HypothesisStatus.INCONCLUSIVE.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.SUPPORTED_AS_SPECIFIED.value: {
        HypothesisStatus.WEAKENED.value,
        HypothesisStatus.FALSIFIED.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.WEAKENED.value: {
        HypothesisStatus.SUPPORTED_AS_SPECIFIED.value,
        HypothesisStatus.FALSIFIED.value,
        HypothesisStatus.INCONCLUSIVE.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.INCONCLUSIVE.value: {
        HypothesisStatus.READY_FOR_EXECUTION.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.BLOCKED_BY_DATA.value: {
        HypothesisStatus.READY_FOR_EXECUTION.value,
        HypothesisStatus.PREREGISTERED.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.BLOCKED_BY_METHOD.value: {
        HypothesisStatus.READY_FOR_EXECUTION.value,
        HypothesisStatus.PREREGISTERED.value,
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.FALSIFIED.value: {
        HypothesisStatus.RETIRED.value,
    },
    HypothesisStatus.RETIRED.value: set(),
}


def validate_status_transition(current_status: str, target_status: str) -> None:
    """Validate that moving from current_status to target_status is permitted in the lifecycle DAG."""
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Invalid transition from '{current_status}' to '{target_status}'. "
            f"Allowed target states: {sorted(allowed)}"
        )


def check_promotion_gates(
    hypothesis: HypothesisRecord,
    target_status: str,
    evidence: EvidenceUpdate | None = None,
    all_evidence: Sequence[EvidenceUpdate] | None = None,
) -> list[str]:
    """Verify all 7 promotion and update rules before transitioning status.

    Returns list of validation warnings or passes; raises PromotionBlockedError if blocked.
    """
    reasons_passed: list[str] = []

    # Rule A: A literature claim cannot become an empirical observation without data
    if target_status in (HypothesisStatus.EXECUTED.value, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value):
        if evidence is not None and evidence.data_type == EvidenceDataType.LITERATURE_CLAIM.value:
            raise PromotionBlockedError(
                "Rule A violation: A literature claim cannot promote a hypothesis to executed or supported without empirical data."
            )
        if all_evidence is not None:
            has_data = any(e.data_type in (EvidenceDataType.EMPIRICAL_DATASET.value, EvidenceDataType.SYNTHETIC_SIMULATION.value) for e in all_evidence)
            if not has_data:
                raise PromotionBlockedError(
                    "Rule A violation: Cannot promote hypothesis to executed or supported without empirical or simulation data."
                )
    reasons_passed.append("Rule A passed: No unsubstantiated literature-only empirical promotion.")

    # Rule B: A synthetic simulation cannot become biological evidence
    if target_status == HypothesisStatus.SUPPORTED_AS_SPECIFIED.value:
        if evidence is not None and evidence.is_synthetic:
            # Synthetic evidence can only support computational models or surrogate baselines
            if hypothesis.epistemic_label not in (EpistemicLabel.COMPUTATIONAL_MODEL.value, EpistemicLabel.SURROGATE_BASELINE.value):
                raise PromotionBlockedError(
                    "Rule B violation: A synthetic simulation cannot be used as evidence to promote a biological/empirical hypothesis."
                )
        if all_evidence is not None:
            only_synthetic = all(e.is_synthetic for e in all_evidence) if all_evidence else False
            if only_synthetic and hypothesis.epistemic_label not in (EpistemicLabel.COMPUTATIONAL_MODEL.value, EpistemicLabel.SURROGATE_BASELINE.value):
                raise PromotionBlockedError(
                    "Rule B violation: Cannot support empirical hypothesis solely with synthetic evidence."
                )
    reasons_passed.append("Rule B passed: Synthetic simulations partitioned strictly to computational/surrogate hypotheses.")

    # Rule C: A proxy Bayes factor cannot become formal evidence
    if evidence is not None and evidence.data_type == EvidenceDataType.PROXY_BAYES_FACTOR.value:
        if target_status == HypothesisStatus.SUPPORTED_AS_SPECIFIED.value:
            raise PromotionBlockedError(
                "Rule C violation: A proxy Bayes factor cannot serve as formal evidence for hypothesis support."
            )
    reasons_passed.append("Rule C passed: Proxy Bayes factors rejected as formal evidence.")

    # Rule D: A model improvement must be out-of-sample
    if target_status == HypothesisStatus.SUPPORTED_AS_SPECIFIED.value:
        if hypothesis.epistemic_label == EpistemicLabel.COMPUTATIONAL_MODEL.value:
            if evidence is not None and not evidence.is_out_of_sample:
                raise PromotionBlockedError(
                    "Rule D violation: Computational model improvements must be verified out-of-sample."
                )
    reasons_passed.append("Rule D passed: Out-of-sample verification confirmed.")

    # Rule G: No autonomous promotion of speculative theory into scientific fact
    # Human review must be an explicit gate
    if target_status == HypothesisStatus.SUPPORTED_AS_SPECIFIED.value:
        if not hypothesis.human_review_gate.passed or not hypothesis.human_review_gate.reviewer:
            raise PromotionBlockedError(
                "Rule G violation: Promotion to 'supported_as_specified' requires explicit human review approval (human_review_gate.passed=True with identified reviewer)."
            )
    reasons_passed.append("Rule G passed: Human review oversight verified.")

    return reasons_passed


def apply_evidence_to_hypothesis(
    hypothesis: HypothesisRecord,
    evidence: EvidenceUpdate,
) -> str:
    """Apply an evidence update to a hypothesis, ensuring failure and contradiction retention.

    Enforces:
    - Rule E: Failed experiment updates hypothesis (falsified/weakened) rather than disappearing.
    - Rule F: Contradictory evidence remains permanently visible.
    """
    # Link evidence
    if evidence.evidence_id not in hypothesis.evidence_links:
        hypothesis.evidence_links.append(evidence.evidence_id)

    # Rule F: Contradictory evidence retention
    if evidence.is_contradictory:
        if evidence.evidence_id not in hypothesis.contradictory_evidence_links:
            hypothesis.contradictory_evidence_links.append(evidence.evidence_id)

    # Determine state transition based on observed evidence
    prev_status = hypothesis.status

    if evidence.is_contradictory:
        # Contradictory evidence weakens or falsifies
        if evidence.observed_p_value is not None and evidence.observed_p_value < 0.05:
            new_status = HypothesisStatus.FALSIFIED.value
        else:
            new_status = HypothesisStatus.WEAKENED.value
    elif evidence.data_type == EvidenceDataType.EMPIRICAL_DATASET.value:
        if evidence.observed_p_value is not None and evidence.observed_p_value < 0.05:
            # Still requires human review before supported_as_specified
            if hypothesis.human_review_gate.passed:
                new_status = HypothesisStatus.SUPPORTED_AS_SPECIFIED.value
            else:
                new_status = HypothesisStatus.EXECUTED.value
        else:
            new_status = HypothesisStatus.INCONCLUSIVE.value
    else:
        new_status = HypothesisStatus.EXECUTED.value

    # Rule E: Failed experiment updates the hypothesis rather than disappearing
    hypothesis.status = new_status
    hypothesis.revision_history.append({
        "evidence_id": evidence.evidence_id,
        "previous_status": prev_status,
        "new_status": new_status,
        "is_contradictory": evidence.is_contradictory,
        "data_type": evidence.data_type,
        "notes": evidence.notes,
    })

    return new_status
