"""Claim-scope / evidence-level governance for transition artifacts.

This is a *minimal, transition-specific* validator. The repository already
has a claim/promotion taxonomy for the DS005620 M/T/C/Q/O ontology track
(`sciencer_d.btc_icft.ontology.schema.ClaimScope`/`PromotionState`), but its
eight values (engineering_runtime, marker_association, topology_residual,
mechanism_candidate, theory_consistency, ontology_candidate,
blocked_overreach, rejected) encode a different, narrower promotion ladder
for that specific label-contract track and do not cover this package's
transition-artifact scopes (computational_artifact, exploratory_metric,
dataset_specific, cross_subject_dataset_specific). Rather than force-fit an
unrelated vocabulary, this module defines its own — deliberately small and
explicit — and reuses the repo's actual single source of truth for banned
overclaim language, `sciencer_d.btc_icft.report_guardrails`, instead of
declaring a fifth copy of that phrase list.
"""
from __future__ import annotations

from typing import Any

from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

ALLOWED_CLAIM_SCOPES: frozenset[str] = frozenset(
    {
        "computational_artifact",
        "exploratory_metric",
        "dataset_specific",
        "cross_subject_dataset_specific",
    }
)

# Always rejected by this milestone's automated validator, regardless of
# evidence supplied. `mechanistic_causal` is included here (not merely
# capped) because this milestone provides no mechanism for the "stronger
# evidence" override the mission spec allows for in principle.
BLOCKED_CLAIM_SCOPES: frozenset[str] = frozenset(
    {
        "clinical",
        "diagnostic",
        "treatment",
        "consciousness_biomarker",
        "mechanistic_causal",
        "spiritual_attainment",
        "enlightenment_detection",
        "jhana_detection",
        "cessation_detection",
    }
)

ALLOWED_EVIDENCE_LEVELS: frozenset[str] = frozenset(
    {
        "L0_computational_artifact",
        "L1_synthetic_validation",
        "L2_single_subject_real_signal",
        "L3_dataset_specific_effect",
        "L4_cross_subject_dataset_specific",
    }
)

NULL_CONTROL_STATUSES: frozenset[str] = frozenset(
    {"not_provided", "not_applicable", "failed", "passed"}
)

DEFAULT_NULL_CONTROL_SUMMARY: dict[str, Any] = {"status": "not_provided"}

# Additive to sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES —
# transition-artifact-specific overreach phrases not already covered there.
TRANSITION_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "consciousness biomarker validated",
    "jhana detected",
    "jhana detection",
    "cessation detected",
    "cessation detection",
    "spiritual attainment",
    "clinical diagnosis",
    "psychiatric diagnosis",
    "meditation stage detected",
    "meditation stage detection",
    "mechanistic proof",
    "causal proof",
    "proves causation",
    "validated biomarker",
    "treatment recommendation",
)


class GovernanceError(ValueError):
    """Raised when a transition record fails claim/evidence governance."""


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    """Recursively scan free text in `value` for banned overclaim phrases."""
    if isinstance(value, str):
        low = value.lower()
        for phrase in BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def validate_governance(record: Any) -> list[str]:
    """Validate a TransitionRecordV1-shaped object's governance fields.

    Returns a list of error strings (empty = valid). Fails closed: any
    ambiguous or unrecognized value is treated as an error, never silently
    accepted. Does not mutate `record`.
    """
    errors: list[str] = []

    scope = record.claim_scope
    level = record.evidence_level

    if scope in BLOCKED_CLAIM_SCOPES:
        errors.append(
            f"claim_scope '{scope}' is blocked for automated transition artifacts"
        )
    elif scope not in ALLOWED_CLAIM_SCOPES:
        errors.append(
            f"claim_scope '{scope}' is not a recognized scope "
            f"(allowed: {sorted(ALLOWED_CLAIM_SCOPES)})"
        )

    if level not in ALLOWED_EVIDENCE_LEVELS:
        errors.append(
            f"evidence_level '{level}' is not a recognized level "
            f"(allowed: {sorted(ALLOWED_EVIDENCE_LEVELS)})"
        )

    if scope == "dataset_specific":
        if not record.dataset_id:
            errors.append("claim_scope 'dataset_specific' requires dataset_id")
        if not record.source_state or not record.target_state:
            errors.append(
                "claim_scope 'dataset_specific' requires source_state and target_state"
            )
        if record.state_label_confidence is None:
            errors.append(
                "claim_scope 'dataset_specific' requires state_label_confidence"
            )

    if scope == "cross_subject_dataset_specific":
        subject_count = None
        if isinstance(record.metadata, dict):
            subject_count = record.metadata.get("subject_count")
        has_cohort_evidence = record.record_level == "cohort" or (
            isinstance(subject_count, int) and subject_count >= 2
        )
        if not has_cohort_evidence:
            errors.append(
                "claim_scope 'cross_subject_dataset_specific' requires "
                "record_level='cohort' or metadata.subject_count >= 2"
            )

    feature_names = record.feature_names or []
    from transitions.features import is_restricted_feature

    if any(is_restricted_feature(name) for name in feature_names) and scope not in (
        "computational_artifact",
        "exploratory_metric",
    ):
        errors.append(
            "experimental.* features cannot exceed claim_scope 'exploratory_metric'"
        )

    null_summary = record.null_control_summary
    if not isinstance(null_summary, dict) or "status" not in null_summary:
        errors.append(
            "null_control_summary must be an explicit dict with a 'status' key "
            "(never silently absent)"
        )
    elif null_summary["status"] not in NULL_CONTROL_STATUSES:
        errors.append(
            f"null_control_summary.status '{null_summary['status']}' must be one "
            f"of {sorted(NULL_CONTROL_STATUSES)}"
        )

    if not record.limitations:
        errors.append("limitations must be a non-empty list")
    elif any(not str(item).strip() for item in record.limitations):
        errors.append("limitations must not contain empty strings")

    _scan_banned_phrases(record.limitations, "limitations", errors)
    _scan_banned_phrases(record.metadata, "metadata", errors)
    _scan_banned_phrases(record.transition_class, "transition_class", errors)
    _scan_banned_phrases(record.intervention, "intervention", errors)
    _scan_banned_phrases(record.preprocessing_provenance, "preprocessing_provenance", errors)

    return errors


def validate_governance_or_raise(record: Any) -> None:
    errors = validate_governance(record)
    if errors:
        raise GovernanceError("; ".join(errors))
