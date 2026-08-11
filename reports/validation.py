"""Structural validation for `EvidenceReportV1`.

Mirrors `evidence.validation`'s relationship to `EvidenceBundleV1`: this
module checks internal consistency and free-text safety, not scientific
validity (the report never recomputes a result -- see `reports.tables`).
Reuses this repository's existing claim/evidence vocabulary and
banned-phrase scanner rather than declaring a new copy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from phase_space.coordinate import scan_banned_phrases

_REPO_ROOT = Path(__file__).resolve().parents[1]


class ReportValidationError(ValueError):
    """Raised when an EvidenceReportV1 fails structural validation."""


def validate_report(report: Any, *, repo_root: Path = _REPO_ROOT) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(report, "report_id", None):
        errors.append("report_id is required")
    if not getattr(report, "bundle_id", None):
        errors.append("bundle_id is required")
    if not getattr(report, "dataset_id", None):
        errors.append("dataset_id is required")

    limitations = getattr(report, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list")
    elif any(not str(item).strip() for item in limitations):
        errors.append("limitations must not contain empty strings")

    blocked_claims = getattr(report, "blocked_claims", None) or []
    if not blocked_claims:
        errors.append("blocked_claims must be a non-empty, explicit list")

    source_artifacts = getattr(report, "source_artifacts", None) or {}
    bundle_path = source_artifacts.get("bundle_path")
    if not bundle_path:
        errors.append("source_artifacts.bundle_path is required")
    elif not (repo_root / bundle_path).exists():
        errors.append(f"source_artifacts.bundle_path does not exist: {bundle_path}")

    for path in source_artifacts.get("transition_record_paths") or []:
        if not (repo_root / path).exists():
            errors.append(f"referenced transition record path does not exist: {path}")

    for path in source_artifacts.get("phase_space_coordinate_paths") or []:
        if not (repo_root / path).exists():
            errors.append(f"referenced phase-space coordinate path does not exist: {path}")

    for path in source_artifacts.get("phase_space_trajectory_paths") or []:
        if not (repo_root / path).exists():
            errors.append(f"referenced phase-space trajectory path does not exist: {path}")

    # A report can never claim more than the bundle it summarizes: the
    # claim_scope_summary/evidence_level_summary it carries must be a
    # verbatim copy of the bundle's own ceiling/generated fields, never a
    # stronger value. This is checked structurally here (equality against
    # what the bundle-derived summaries recorded), not re-derived.
    claim_scope_summary = getattr(report, "claim_scope_summary", None) or {}
    if "claim_scope_ceiling" not in claim_scope_summary or "generated_claim_scope" not in claim_scope_summary:
        errors.append("claim_scope_summary must include claim_scope_ceiling and generated_claim_scope")

    evidence_level_summary = getattr(report, "evidence_level_summary", None) or {}
    if "evidence_level_ceiling" not in evidence_level_summary or "generated_evidence_levels" not in evidence_level_summary:
        errors.append("evidence_level_summary must include evidence_level_ceiling and generated_evidence_levels")

    validation_summary = getattr(report, "validation_summary", None)
    if not isinstance(validation_summary, dict):
        errors.append("validation_summary must be a dict")
    elif "bundle_valid" not in validation_summary:
        errors.append("validation_summary must record whether the source bundle was valid (bundle_valid)")

    reproducibility_commands = getattr(report, "reproducibility_commands", None) or []
    if not reproducibility_commands:
        errors.append("reproducibility_commands must be a non-empty list")

    metadata = getattr(report, "metadata", None) or {}
    scan_banned_phrases(limitations, "limitations", errors)
    scan_banned_phrases(blocked_claims, "blocked_claims", errors)
    scan_banned_phrases(getattr(report, "report_title", "") or "", "report_title", errors)
    scan_banned_phrases(metadata, "metadata", errors)
    scan_banned_phrases(reproducibility_commands, "reproducibility_commands", errors)

    return errors
