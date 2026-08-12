"""Structural validation and shared vocabulary for
`DatasetOpportunityRecordV1`/`DatasetOpportunityBatchV1`/
`DatasetOpportunityPlanV1`.

Reuses this repository's existing banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`) plus
`dataset_importers.validation.DATASET_IMPORTER_EXTRA_BANNED_PHRASES`
(candidate-scouting overclaim phrases already vetted there) and
`dataset_acquisition.store.ALLOWED_TARGET_ROOT_PREFIXES` for output-root
safety, mirroring every other validation module in this repository.
"""
from __future__ import annotations

from typing import Any

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from dataset_importers.validation import DATASET_IMPORTER_EXTRA_BANNED_PHRASES
from phase_space.coordinate import scan_banned_phrases
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES

ALLOWED_RECOMMENDED_NEXT_ACTIONS: frozenset[str] = frozenset(
    {
        "metadata_review",
        "candidate_curation",
        "acquisition_plan_only",
        "local_availability_check",
        "mapping_feasibility_review",
        "benchmark_pack_proposal",
        "literature_review_task",
        "researcher_outreach_candidate",
        "defer",
        "reject",
    }
)

# Any opportunity's blocked_actions must be a superset of this floor --
# these describe things this scout can never authorize regardless of how
# well-scored a candidate is.
REQUIRED_BLOCKED_ACTIONS: frozenset[str] = frozenset(
    {
        "direct_evidence_claim",
        "direct_report_generation",
        "clinical_claim",
        "spiritual_attainment_claim",
        "automatic_contact",
        "automatic_download",
    }
)

# recommended_next_actions that would eventually touch execution (running a
# job, downloading, extracting features) -- rule 12: unknown license/
# access/size must block these specifically, not just lower a score.
_EXECUTION_ORIENTED_ACTIONS: frozenset[str] = frozenset(
    {"acquisition_plan_only", "benchmark_pack_proposal", "local_availability_check"}
)

ALLOWED_ACCESS_STATUS: frozenset[str] = frozenset(
    {"public", "public_requires_download", "requires_registration", "restricted", "unknown"}
)

DATASET_OPPORTUNITY_EXTRA_BANNED_PHRASES: tuple[str, ...] = DATASET_IMPORTER_EXTRA_BANNED_PHRASES

_ALL_OPPORTUNITY_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES + DATASET_OPPORTUNITY_EXTRA_BANNED_PHRASES
)


class DatasetOpportunityValidationError(ValueError):
    """Raised when a dataset-opportunity object fails structural validation."""


class DatasetOpportunityStoreError(ValueError):
    """Raised for dataset-opportunity store-level problems (unsafe output_root, missing input, ...)."""


def scan_text_for_banned_phrases(text: str) -> list[str]:
    low = text.lower()
    return [phrase for phrase in _ALL_OPPORTUNITY_BANNED_PHRASES if phrase in low]


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    if isinstance(value, str):
        low = value.lower()
        for phrase in DATASET_OPPORTUNITY_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def validate_repo_relative_root(value: Any, field_name: str) -> list[str]:
    errors: list[str] = []
    if not value or not isinstance(value, str):
        errors.append(f"{field_name} is required (non-empty string)")
        return errors
    raw = value.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in raw.split("/"):
        errors.append(f"{field_name} must be a safe relative repository path, got {value!r}")
        return errors
    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"{field_name} must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {value!r}")
    return errors


def validate_opportunity_record(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(record, "opportunity_id", None):
        errors.append("opportunity_id is required")

    # Rule 1.
    if not getattr(record, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(record, "provenance", None):
        errors.append("provenance is required (rule 2)")

    # Rule 3.
    if not getattr(record, "source_candidate_id", None):
        errors.append("source_candidate_id is required -- candidate source must be explicit (rule 3)")
    if not getattr(record, "source_catalog", None):
        errors.append("source_catalog is required -- candidate source must be explicit (rule 3)")

    # Rule 4.
    score_components = getattr(record, "score_components", None) or {}
    total_score = getattr(record, "total_score", None)
    if score_components and total_score is not None:
        computed = round(sum(float(v) for v in score_components.values()), 2)
        if abs(computed - round(float(total_score), 2)) > 1e-6:
            errors.append(
                f"total_score ({total_score}) must equal sum of score_components ({computed}) (rule 4)"
            )

    # Rule 5.
    for action in getattr(record, "recommended_next_actions", None) or []:
        if action not in ALLOWED_RECOMMENDED_NEXT_ACTIONS:
            errors.append(f"recommended_next_actions: '{action}' must be one of {sorted(ALLOWED_RECOMMENDED_NEXT_ACTIONS)} (rule 5)")

    # Rule 6.
    blocked_actions = set(getattr(record, "blocked_actions", None) or [])
    missing_blocked = REQUIRED_BLOCKED_ACTIONS - blocked_actions
    if missing_blocked:
        errors.append(f"blocked_actions is missing required entries: {sorted(missing_blocked)} (rule 6)")

    # Rule 7 (+11 field-level): no claim/evidence promotion field.
    if hasattr(record, "claim_scope") or hasattr(record, "evidence_level") or hasattr(record, "evidence_ready"):
        errors.append("DatasetOpportunityRecordV1 must not carry its own claim_scope/evidence_level/evidence_ready field (rule 7/8)")

    # Rule 12: unknown license/access/size must block execution-oriented actions.
    access_status = getattr(record, "access_status", None)
    license_risk = getattr(record, "license_risk", None)
    size_status = getattr(record, "estimated_size_status", None)
    unknown_signal = access_status in ("unknown", "restricted") or license_risk == "unknown_high" or size_status == "unknown"
    if unknown_signal:
        recommended = set(getattr(record, "recommended_next_actions", None) or [])
        offending = recommended & _EXECUTION_ORIENTED_ACTIONS
        if offending:
            errors.append(
                f"unknown/restricted access, license, or size must not recommend execution-oriented actions: {sorted(offending)} (rule 12)"
            )

    # Rule 11 (+ banned-phrase scan).
    for field_name in ("dataset_name", "provenance"):
        _scan_banned_phrases(getattr(record, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "risk_flags"):
        _scan_banned_phrases(getattr(record, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(record, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_opportunity_batch(batch: Any) -> list[str]:
    errors: list[str] = []

    if not getattr(batch, "batch_id", None):
        errors.append("batch_id is required")

    if not getattr(batch, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(batch, "provenance", None):
        errors.append("provenance is required (rule 2)")

    total_seen = getattr(batch, "total_candidates_seen", None)
    total_ranked = getattr(batch, "total_opportunities_ranked", None)
    ranked = getattr(batch, "ranked_opportunities", None) or []
    rejected = getattr(batch, "rejected_opportunities", None) or []
    if total_ranked is not None and total_ranked != len(ranked):
        errors.append(f"total_opportunities_ranked ({total_ranked}) must equal len(ranked_opportunities) ({len(ranked)})")
    if total_seen is not None and total_seen < len(ranked) + len(rejected):
        errors.append("total_candidates_seen must be >= len(ranked_opportunities) + len(rejected_opportunities)")

    if hasattr(batch, "claim_scope") or hasattr(batch, "evidence_level"):
        errors.append("DatasetOpportunityBatchV1 must not carry its own claim_scope/evidence_level field")

    _scan_banned_phrases(getattr(batch, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(batch, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(batch, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_opportunity_plan(plan: Any) -> list[str]:
    errors: list[str] = []

    if not getattr(plan, "plan_id", None):
        errors.append("plan_id is required")
    if not getattr(plan, "opportunity_batch_id", None):
        errors.append("opportunity_batch_id is required")

    if not getattr(plan, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(plan, "provenance", None):
        errors.append("provenance is required (rule 2)")

    for candidate in getattr(plan, "planned_outreach_candidates", None) or []:
        if isinstance(candidate, dict) and not candidate.get("requires_human_review", True):
            errors.append("every planned_outreach_candidates entry must have requires_human_review=True (rule 9)")

    if hasattr(plan, "claim_scope") or hasattr(plan, "evidence_level"):
        errors.append("DatasetOpportunityPlanV1 must not carry its own claim_scope/evidence_level field")

    _scan_banned_phrases(getattr(plan, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(plan, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(plan, "metadata", None) or {}, "metadata", errors)

    return errors
