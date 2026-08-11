"""Structural validation and shared vocabulary for
`dataset_importers.candidate_record.DatasetCandidateRecordV1`.

Reuses this repository's existing banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`, itself the union of
`sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES` and
`transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES`) plus
`external_tools.validation.ALLOWED_LICENSE_RISK`, mirroring how every other
validation module in this repository reuses the shared vocabulary rather
than declaring a new copy. Adds one small, additive phrase list of its own
(`DATASET_IMPORTER_EXTRA_BANNED_PHRASES`) for overclaim language specific to
*candidate scouting* -- treating a candidate as if it were already evidence.
"""
from __future__ import annotations

from typing import Any

from external_tools.validation import ALLOWED_LICENSE_RISK
from phase_space.coordinate import scan_banned_phrases

ALLOWED_SOURCE_CATALOGS: frozenset[str] = frozenset(
    {"moabb", "eegdash", "openneuro_manual", "nemar_manual", "repo_manual", "synthetic_fixture"}
)

ALLOWED_TRANSITION_READINESS: frozenset[str] = frozenset(
    {
        "metadata_only",
        "candidate_transition_possible",
        "explicit_condition_mapping_needed",
        "derived_feature_extraction_needed",
        "blocked_missing_metadata",
        "blocked_license_or_access",
        "blocked_unsupported_modality",
    }
)

ALLOWED_ACCESS_STATUS: frozenset[str] = frozenset(
    {"public", "public_requires_download", "requires_registration", "restricted", "unknown"}
)

ALLOWED_BENCHMARK_ROLE_RECOMMENDATION: frozenset[str] = frozenset(
    {"exploration_candidate", "development_candidate", "documentation_only", "blocked", "review_needed"}
)

ALLOWED_DOWNLOAD_REQUIRED: frozenset[str] = frozenset({"true", "false", "unknown"})

_BLOCKED_TRANSITION_READINESS: frozenset[str] = frozenset(
    {"blocked_missing_metadata", "blocked_license_or_access", "blocked_unsupported_modality"}
)

_RESTRICTED_OR_UNKNOWN_ACCESS: frozenset[str] = frozenset({"restricted", "unknown"})

# Rule 9 fixed floor -- mirrors
# `external_tools.validation.REQUIRED_FORBIDDEN_OUTPUTS`: a candidate record
# may forbid more than this, never less.
REQUIRED_FORBIDDEN_USES: frozenset[str] = frozenset(
    {
        "final_claim_confirmation",
        "clinical_claim",
        "mechanistic_causal_claim",
        "prospective_prediction_claim",
    }
)

# Candidate status is not validation (mission core principle) -- these two
# uses are the actual authority to build governed artifacts from a dataset;
# a *candidate* record must never carry them in forbidden_uses' complement,
# regardless of how promising its metadata looks. Enforced together with
# REQUIRED_FORBIDDEN_USES by rule 7/8 below.
_EVIDENCE_AUTHORITY_USES: frozenset[str] = frozenset({"transition_export", "phase_space_export"})

DATASET_IMPORTER_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "candidate is evidence",
    "candidate proves",
    "metadata proves",
    "guaranteed transition-ready",
    "guaranteed transition ready",
    "validated public dataset",
    "confirmed transition dataset",
)


class DatasetImporterValidationError(ValueError):
    """Raised when a `DatasetCandidateRecordV1` fails structural validation."""


def _scan_extra_phrases(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        low = value.lower()
        for phrase in DATASET_IMPORTER_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_extra_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_extra_phrases(item, f"{path}[{idx}]", errors)


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    _scan_extra_phrases(value, path, errors)


def validate_candidate_record(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    source_catalog = getattr(record, "source_catalog", None)
    # Rule 11: source_catalog must be explicit.
    if not source_catalog:
        errors.append("source_catalog is required (rule 11)")
    elif source_catalog not in ALLOWED_SOURCE_CATALOGS:
        errors.append(f"source_catalog '{source_catalog}' must be one of {sorted(ALLOWED_SOURCE_CATALOGS)} (rule 11)")

    source_dataset_id = getattr(record, "source_dataset_id", None)
    if not source_dataset_id:
        errors.append("source_dataset_id is required")

    # Rule 1: candidate_id deterministic from source_catalog + source_dataset_id.
    if source_catalog and source_dataset_id:
        from dataset_importers.candidate_record import compute_candidate_id

        expected_id = compute_candidate_id(source_catalog=source_catalog, source_dataset_id=source_dataset_id)
        candidate_id = getattr(record, "candidate_id", None)
        if candidate_id != expected_id:
            errors.append(
                f"candidate_id '{candidate_id}' does not match deterministic id '{expected_id}' "
                "for (source_catalog, source_dataset_id) (rule 1)"
            )

    license_risk = getattr(record, "license_risk", None)
    if license_risk not in ALLOWED_LICENSE_RISK:
        errors.append(f"license_risk '{license_risk}' must be one of {sorted(ALLOWED_LICENSE_RISK)}")

    access_status = getattr(record, "access_status", None)
    if access_status not in ALLOWED_ACCESS_STATUS:
        errors.append(f"access_status '{access_status}' must be one of {sorted(ALLOWED_ACCESS_STATUS)}")

    transition_readiness = getattr(record, "transition_readiness", None)
    if transition_readiness not in ALLOWED_TRANSITION_READINESS:
        errors.append(
            f"transition_readiness '{transition_readiness}' must be one of {sorted(ALLOWED_TRANSITION_READINESS)}"
        )

    benchmark_role_recommendation = getattr(record, "benchmark_role_recommendation", None)
    if benchmark_role_recommendation not in ALLOWED_BENCHMARK_ROLE_RECOMMENDATION:
        errors.append(
            f"benchmark_role_recommendation '{benchmark_role_recommendation}' must be one of "
            f"{sorted(ALLOWED_BENCHMARK_ROLE_RECOMMENDATION)}"
        )

    # Rule 12: download_required must be true/false/unknown, not omitted.
    download_required = getattr(record, "download_required", None)
    if download_required not in ALLOWED_DOWNLOAD_REQUIRED:
        errors.append(
            f"download_required '{download_required}' must be one of {sorted(ALLOWED_DOWNLOAD_REQUIRED)} (rule 12)"
        )

    # Rule 3 (mission numbering): risks non-empty.
    risks = getattr(record, "risks", None) or []
    if not risks:
        errors.append("risks must be a non-empty list (rule 3)")

    # Rule 2: limitations non-empty.
    limitations = getattr(record, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list (rule 2)")

    # Rule 4: provenance non-empty.
    if not getattr(record, "provenance", None):
        errors.append("provenance is required (rule 4)")

    license_value = getattr(record, "license", None)
    # Rule 5: unknown license becomes unknown_high.
    if not license_value or str(license_value).strip().lower() == "unknown":
        if license_risk != "unknown_high":
            errors.append("license 'unknown' requires license_risk='unknown_high' (rule 5)")

    allowed_uses = set(getattr(record, "allowed_uses", None) or [])
    forbidden_uses = set(getattr(record, "forbidden_uses", None) or [])

    # Rule 6: restricted/unknown access cannot be recommended as development_candidate.
    if access_status in _RESTRICTED_OR_UNKNOWN_ACCESS and benchmark_role_recommendation == "development_candidate":
        errors.append(
            "access_status "
            f"'{access_status}' cannot be paired with benchmark_role_recommendation='development_candidate' (rule 6)"
        )

    # Rule 7: blocked_license_or_access must forbid transition_export and phase_space_export.
    if transition_readiness == "blocked_license_or_access" and not _EVIDENCE_AUTHORITY_USES.issubset(forbidden_uses):
        errors.append(
            "transition_readiness='blocked_license_or_access' requires forbidden_uses to include "
            f"{sorted(_EVIDENCE_AUTHORITY_USES)} (rule 7)"
        )

    # Rule 8: metadata_only cannot be treated as evidence -- and, more
    # generally, no candidate record (any readiness) may itself carry the
    # authority to export a transition/phase-space artifact; that authority
    # belongs only to a real DatasetRecordV1 built later with an explicit
    # mapping. Candidate status is not validation (core principle).
    if allowed_uses & _EVIDENCE_AUTHORITY_USES:
        errors.append(
            f"allowed_uses must never contain {sorted(_EVIDENCE_AUTHORITY_USES)} on a candidate record (rule 8)"
        )
    if not _EVIDENCE_AUTHORITY_USES.issubset(forbidden_uses):
        errors.append(f"forbidden_uses must always include {sorted(_EVIDENCE_AUTHORITY_USES)} (rule 8)")

    # Rule 9: no candidate can allow final_claim_confirmation, clinical_claim,
    # mechanistic_causal_claim, or prospective_prediction_claim.
    if allowed_uses & REQUIRED_FORBIDDEN_USES:
        errors.append(f"allowed_uses must never contain {sorted(REQUIRED_FORBIDDEN_USES)} (rule 9)")
    missing_forbidden = REQUIRED_FORBIDDEN_USES - forbidden_uses
    if missing_forbidden:
        errors.append(f"forbidden_uses is missing required entries: {sorted(missing_forbidden)} (rule 9)")

    for count_field in ("subject_count", "session_count", "recording_count"):
        value = getattr(record, count_field, None)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            errors.append(f"{count_field} must be a non-negative integer or None, got {value!r}")

    # Rule 10: no forbidden overclaim language.
    for field_name in ("display_name", "recommended_next_action", "provenance"):
        _scan_banned_phrases(getattr(record, field_name, None) or "", field_name, errors)
    for field_name in (
        "risks",
        "limitations",
        "allowed_uses",
        "forbidden_uses",
        "task_labels",
        "condition_labels",
        "potential_transition_classes",
        "available_metadata",
    ):
        _scan_banned_phrases(getattr(record, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(record, "metadata", None) or {}, "metadata", errors)

    return errors
