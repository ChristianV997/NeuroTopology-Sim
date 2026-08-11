"""Structural validation for `EvidenceBundleV1`.

Field-level, cross-reference, and governance checks only: "is this bundle
internally consistent and non-overclaiming," not "should this dataset be
used this way" (that's `benchmarks.split_policy`, already enforced by the
exporters before a bundle is ever built). Reuses this repository's existing
claim/evidence vocabulary and banned-phrase scanner rather than declaring a
new copy, mirroring `benchmarks.validation` and `transitions.governance`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.split_policy import ALWAYS_BLOCKED_USES, KNOWN_USE_VALUES
from phase_space.coordinate import CLAIM_SCOPE_ORDER, scan_banned_phrases
from transitions.governance import ALLOWED_CLAIM_SCOPES, ALLOWED_EVIDENCE_LEVELS

_REPO_ROOT = Path(__file__).resolve().parents[1]

# No existing module ranks evidence levels (transitions.governance only
# exposes a frozenset of allowed values); phase_space.coordinate had the
# same gap for claim scopes and resolved it with its own local
# CLAIM_SCOPE_ORDER tuple, which this module imports and reuses rather than
# re-declaring. Evidence levels get the analogous local ordering here,
# weakest first, matching the L0-L4 naming's own implied ladder.
EVIDENCE_LEVEL_ORDER: tuple[str, ...] = (
    "L0_computational_artifact",
    "L1_synthetic_validation",
    "L2_single_subject_real_signal",
    "L3_dataset_specific_effect",
    "L4_cross_subject_dataset_specific",
)

NULL_CONTROL_STATUSES: frozenset[str] = frozenset(
    {"not_provided", "not_applicable", "failed", "passed", "mixed"}
)

PHASE_SPACE_STATUSES: frozenset[str] = frozenset(
    {"not_requested", "estimated", "insufficient_data_only", "failed"}
)


class BundleValidationError(ValueError):
    """Raised when an EvidenceBundleV1 fails structural validation."""


def claim_scope_rank(scope: str) -> int:
    return CLAIM_SCOPE_ORDER.index(scope) if scope in CLAIM_SCOPE_ORDER else -1


def evidence_level_rank(level: str) -> int:
    return EVIDENCE_LEVEL_ORDER.index(level) if level in EVIDENCE_LEVEL_ORDER else -1


def validate_bundle(bundle: Any, *, repo_root: Path = _REPO_ROOT) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(bundle, "bundle_id", None):
        errors.append("bundle_id is required")
    if not getattr(bundle, "dataset_id", None):
        errors.append("dataset_id is required")

    limitations = getattr(bundle, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list")
    elif any(not str(item).strip() for item in limitations):
        errors.append("limitations must not contain empty strings")

    requested_use = getattr(bundle, "requested_use", None)
    if requested_use in ALWAYS_BLOCKED_USES:
        errors.append(f"requested_use '{requested_use}' is always blocked (rule 6) and must never appear on a bundle")
    elif requested_use not in KNOWN_USE_VALUES:
        errors.append(f"requested_use '{requested_use}' is not a recognized use")

    claim_scope_ceiling = getattr(bundle, "claim_scope_ceiling", None)
    if claim_scope_ceiling not in ALLOWED_CLAIM_SCOPES:
        errors.append(f"claim_scope_ceiling '{claim_scope_ceiling}' must be one of {sorted(ALLOWED_CLAIM_SCOPES)}")

    evidence_level_ceiling = getattr(bundle, "evidence_level_ceiling", None)
    if evidence_level_ceiling not in ALLOWED_EVIDENCE_LEVELS:
        errors.append(f"evidence_level_ceiling '{evidence_level_ceiling}' must be one of {sorted(ALLOWED_EVIDENCE_LEVELS)}")

    generated_claim_scope = getattr(bundle, "generated_claim_scope", None)
    if generated_claim_scope is not None:
        if generated_claim_scope not in ALLOWED_CLAIM_SCOPES:
            errors.append(f"generated_claim_scope '{generated_claim_scope}' is not recognized")
        elif claim_scope_ceiling in ALLOWED_CLAIM_SCOPES and claim_scope_rank(generated_claim_scope) > claim_scope_rank(claim_scope_ceiling):
            errors.append(
                f"generated_claim_scope '{generated_claim_scope}' exceeds claim_scope_ceiling "
                f"'{claim_scope_ceiling}' -- a bundle may never claim more than its ceiling"
            )

    generated_evidence_levels = getattr(bundle, "generated_evidence_levels", None) or []
    for level in generated_evidence_levels:
        if level not in ALLOWED_EVIDENCE_LEVELS:
            errors.append(f"generated_evidence_levels contains unrecognized level '{level}'")
        elif evidence_level_ceiling in ALLOWED_EVIDENCE_LEVELS and evidence_level_rank(level) > evidence_level_rank(evidence_level_ceiling):
            errors.append(
                f"generated_evidence_levels contains '{level}', which exceeds "
                f"evidence_level_ceiling '{evidence_level_ceiling}'"
            )

    # Transition record cross-references: paths exist, IDs match parallel lists.
    transition_record_ids = getattr(bundle, "transition_record_ids", None) or []
    transition_record_paths = getattr(bundle, "transition_record_paths", None) or []
    if len(transition_record_ids) != len(transition_record_paths):
        errors.append(
            f"transition_record_ids ({len(transition_record_ids)}) and "
            f"transition_record_paths ({len(transition_record_paths)}) must be parallel lists of equal length"
        )
    else:
        for expected_id, rel_path in zip(transition_record_ids, transition_record_paths):
            candidate = repo_root / rel_path
            if not candidate.exists():
                errors.append(f"transition record path does not exist: {rel_path}")
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"transition record path unreadable: {rel_path} ({exc})")
                continue
            actual_id = payload.get("transition_id")
            if actual_id != expected_id:
                errors.append(
                    f"transition_record_ids lists '{expected_id}' but {rel_path} contains "
                    f"transition_id '{actual_id}'"
                )

    # Phase-space coordinate cross-references: paths exist, every listed
    # coordinate_id is actually present in one of the coordinate files
    # (files are one-per-transition and hold a *list* of coordinates, so
    # this is a membership check, not a 1:1 positional one).
    coordinate_ids = set(getattr(bundle, "phase_space_coordinate_ids", None) or [])
    coordinate_paths = getattr(bundle, "phase_space_coordinate_paths", None) or []
    found_coordinate_ids: set[str] = set()
    for rel_path in coordinate_paths:
        candidate = repo_root / rel_path
        if not candidate.exists():
            errors.append(f"phase-space coordinate path does not exist: {rel_path}")
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"phase-space coordinate path unreadable: {rel_path} ({exc})")
            continue
        for coord in payload.get("coordinates", []):
            found_coordinate_ids.add(coord.get("coordinate_id"))
    missing_ids = coordinate_ids - found_coordinate_ids
    if missing_ids:
        errors.append(
            f"phase_space_coordinate_ids lists {sorted(missing_ids)} but no coordinate file "
            "contains them"
        )

    for rel_path in getattr(bundle, "phase_space_trajectory_paths", None) or []:
        if not (repo_root / rel_path).exists():
            errors.append(f"phase-space trajectory path does not exist: {rel_path}")

    # Phase-space request/outcome coherence: never silently drop a requested
    # but empty phase-space result.
    metadata = getattr(bundle, "metadata", None) or {}
    if metadata.get("include_phase_space"):
        phase_space_status = metadata.get("phase_space_status")
        if phase_space_status not in PHASE_SPACE_STATUSES:
            errors.append(
                f"metadata.phase_space_status '{phase_space_status}' must be one of "
                f"{sorted(PHASE_SPACE_STATUSES)} when metadata.include_phase_space is true"
            )
        elif phase_space_status == "estimated" and not coordinate_ids:
            errors.append(
                "metadata.phase_space_status is 'estimated' but phase_space_coordinate_ids is empty"
            )
        elif phase_space_status in ("insufficient_data_only", "failed") and coordinate_ids:
            errors.append(
                f"metadata.phase_space_status is '{phase_space_status}' but "
                "phase_space_coordinate_ids is non-empty"
            )

    # Null-control honesty: 'passed' must be backed by at least one real
    # per-transition 'passed' entry; a bundle whose sources are all
    # not_provided/failed must never report a blanket 'passed'.
    null_control_summary = getattr(bundle, "null_control_summary", None)
    if not isinstance(null_control_summary, dict) or "status" not in null_control_summary:
        errors.append("null_control_summary must be an explicit dict with a 'status' key")
    else:
        status = null_control_summary["status"]
        if status not in NULL_CONTROL_STATUSES:
            errors.append(f"null_control_summary.status '{status}' must be one of {sorted(NULL_CONTROL_STATUSES)}")
        per_transition = null_control_summary.get("per_transition") or {}
        if status == "passed":
            if not any(v == "passed" for v in per_transition.values()):
                errors.append(
                    "null_control_summary.status is 'passed' but no per_transition entry "
                    "reports 'passed' -- refusing to let an absent null silently become a pass"
                )
        if per_transition and all(v == "not_provided" for v in per_transition.values()) and status != "not_provided":
            errors.append(
                f"every per_transition null-control entry is 'not_provided' but the bundle "
                f"status is '{status}', not 'not_provided'"
            )

    # Registry decisions: a bundle whose registry_path is set must have
    # recorded at least one decision, and no recorded decision may be an
    # unexplained denial (a denial should have aborted the build).
    registry_path = getattr(bundle, "registry_path", None)
    registry_decisions = getattr(bundle, "registry_decisions", None) or []
    if registry_path and not registry_decisions:
        errors.append("registry_path is set but registry_decisions is empty")
    for decision in registry_decisions:
        if not decision.get("allowed", True):
            errors.append(
                f"registry_decisions contains a denied decision ({decision}) -- a bundle must "
                "never be built past a denial"
            )

    validation_summary = getattr(bundle, "validation_summary", None)
    if not isinstance(validation_summary, dict):
        errors.append("validation_summary must be a dict")

    scan_banned_phrases(limitations, "limitations", errors)
    scan_banned_phrases(metadata, "metadata", errors)
    scan_banned_phrases(null_control_summary, "null_control_summary", errors)
    scan_banned_phrases(validation_summary, "validation_summary", errors)

    return errors
