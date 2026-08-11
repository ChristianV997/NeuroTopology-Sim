"""Structural validation and shared vocabulary for
`DatasetAcquisitionPlanV1`/`DatasetAcquisitionManifestV1`.

Reuses this repository's shared banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`) plus
`external_tools.validation.ALLOWED_LICENSE_RISK`, mirroring
`dataset_importers.validation`'s own reuse pattern rather than declaring
new copies.
"""
from __future__ import annotations

from typing import Any

from external_tools.validation import ALLOWED_LICENSE_RISK
from phase_space.coordinate import scan_banned_phrases

ALLOWED_REQUESTED_ACTIONS: frozenset[str] = frozenset(
    {"metadata_only", "plan_download", "execute_download", "scan_existing_local", "verify_existing_local"}
)

ALLOWED_ACQUISITION_MODES: frozenset[str] = frozenset(
    {
        "no_download_metadata_only",
        "eegdash_metadata_query",
        "moabb_planned_fetch",
        "openneuro_external_cli_plan",
        "datalad_external_cli_plan",
        "local_bids_scan",
        "manual_url_manifest",
        "fixture_only",
    }
)

ALLOWED_EXECUTION_STATUS: frozenset[str] = frozenset(
    {"planned_only", "blocked", "skipped", "acquired", "verified_existing", "failed"}
)

# Acquisition modes for which v1 has no implemented remote-fetch execution
# path -- only scan_existing_local/verify_existing_local ever touch a real
# local filesystem in this milestone. Reused by both the planner (to
# pre-populate blocked_reasons) and the executor (as a second, independent
# fail-closed gate).
_UNIMPLEMENTED_REMOTE_MODES: frozenset[str] = frozenset(
    {
        "eegdash_metadata_query",
        "moabb_planned_fetch",
        "openneuro_external_cli_plan",
        "datalad_external_cli_plan",
        "manual_url_manifest",
    }
)

_DISQUALIFYING_LICENSE_RISK: frozenset[str] = frozenset({"unknown_high", "proprietary_high"})
_DISQUALIFYING_ACCESS_STATUS: frozenset[str] = frozenset({"restricted", "unknown"})

# Rule 15 defense-in-depth: neither a plan nor a manifest may carry a
# metadata key implying it is itself evidence or validation-ready.
_FORBIDDEN_METADATA_TRUE_KEYS: frozenset[str] = frozenset(
    {"final_claim_confirmation", "evidence", "validation_ready", "clinical_claim"}
)

DATASET_ACQUISITION_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "manifest is evidence",
    "plan is evidence",
    "acquisition proves",
    "download confirms",
    "guaranteed safe download",
)


class DatasetAcquisitionValidationError(ValueError):
    """Raised when a plan or manifest fails structural validation."""


def _scan_extra_phrases(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        low = value.lower()
        for phrase in DATASET_ACQUISITION_EXTRA_BANNED_PHRASES:
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


def _check_forbidden_metadata_keys(metadata: dict[str, Any], errors: list[str]) -> None:
    for key in _FORBIDDEN_METADATA_TRUE_KEYS:
        if metadata.get(key):
            errors.append(f"metadata.{key} must never be truthy (rule 15)")


def validate_plan(plan: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    candidate_id = getattr(plan, "candidate_id", None)
    if not candidate_id:
        errors.append("candidate_id is required")

    requested_action = getattr(plan, "requested_action", None)
    if requested_action not in ALLOWED_REQUESTED_ACTIONS:
        errors.append(f"requested_action '{requested_action}' must be one of {sorted(ALLOWED_REQUESTED_ACTIONS)}")

    acquisition_mode = getattr(plan, "acquisition_mode", None)
    if acquisition_mode not in ALLOWED_ACQUISITION_MODES:
        errors.append(f"acquisition_mode '{acquisition_mode}' must be one of {sorted(ALLOWED_ACQUISITION_MODES)}")

    target_root = getattr(plan, "target_root", None) or ""
    disk_limit_bytes = getattr(plan, "disk_limit_bytes", None)

    # Rule 1: plan_id deterministic from identity fields.
    if candidate_id and requested_action and acquisition_mode:
        from dataset_acquisition.acquisition_plan import compute_plan_id

        expected_id = compute_plan_id(
            candidate_id=candidate_id,
            requested_action=requested_action,
            acquisition_mode=acquisition_mode,
            target_root=target_root,
            disk_limit_bytes=disk_limit_bytes,
        )
        plan_id = getattr(plan, "plan_id", None)
        if plan_id != expected_id:
            errors.append(f"plan_id '{plan_id}' does not match deterministic id '{expected_id}' (rule 1)")

    # Rules 3/4/5.
    if not getattr(plan, "risks", None):
        errors.append("risks must be a non-empty list (rule 4)")
    if not getattr(plan, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 3)")
    if not getattr(plan, "provenance", None):
        errors.append("provenance is required (rule 5)")

    license_risk = getattr(plan, "license_risk", None)
    if license_risk not in ALLOWED_LICENSE_RISK:
        errors.append(f"license_risk '{license_risk}' must be one of {sorted(ALLOWED_LICENSE_RISK)}")

    dry_run = bool(getattr(plan, "dry_run", True))
    allow_network = bool(getattr(plan, "allow_network", False))
    allow_raw_data = bool(getattr(plan, "allow_raw_data", False))
    access_status = getattr(plan, "access_status", None)
    estimated_size_bytes = getattr(plan, "estimated_size_bytes", None)
    metadata = getattr(plan, "metadata", None) or {}
    blocked_reasons = getattr(plan, "blocked_reasons", None) or []

    # Rule 6: dry_run must be true unless requested_action=execute_download.
    if not dry_run and requested_action != "execute_download":
        errors.append("dry_run=False is only permitted when requested_action='execute_download' (rule 6)")

    if requested_action == "execute_download":
        # Rule 9: an *unblocked* execute_download plan (blocked_reasons
        # empty) must have allow_network, allow_raw_data,
        # disk_limit_bytes, and an explicit execute confirmation already
        # satisfied -- that is what "unblocked" means. A *blocked* plan is
        # explicitly allowed to represent any flag state, since recording
        # why a request is blocked (missing flags among the reasons) is
        # exactly this object's job; only an unblocked plan must be clean.
        if not blocked_reasons:
            if not allow_network:
                errors.append("an unblocked execute_download plan requires allow_network=True (rule 9)")
            if not allow_raw_data:
                errors.append("an unblocked execute_download plan requires allow_raw_data=True (rule 9)")
            if disk_limit_bytes is None:
                errors.append("an unblocked execute_download plan requires disk_limit_bytes to be set (rule 9)")
            if not metadata.get("explicit_execute_confirmed"):
                errors.append(
                    "an unblocked execute_download plan requires metadata.explicit_execute_confirmed=True (rule 9)"
                )

        # Rule 10: unknown license or restricted/unknown access blocks
        # execute_download -- an unblocked (blocked_reasons empty) plan may
        # never carry a disqualifying license/access.
        if not blocked_reasons:
            if license_risk in _DISQUALIFYING_LICENSE_RISK:
                errors.append(
                    f"license_risk='{license_risk}' must block execute_download (blocked_reasons must be non-empty) (rule 10)"
                )
            if access_status in _DISQUALIFYING_ACCESS_STATUS:
                errors.append(
                    f"access_status='{access_status}' must block execute_download (blocked_reasons must be non-empty) (rule 10)"
                )

            # Rule 11: estimated_size_bytes > disk_limit_bytes blocks execute_download.
            if (
                estimated_size_bytes is not None
                and disk_limit_bytes is not None
                and estimated_size_bytes > disk_limit_bytes
            ):
                errors.append(
                    "estimated_size_bytes exceeds disk_limit_bytes; this must block execute_download (rule 11)"
                )

            # Rule 12: unknown size blocks execute_download unless override supplied.
            if estimated_size_bytes is None and not metadata.get("force_unknown_size"):
                errors.append(
                    "estimated_size_bytes is unknown; this must block execute_download unless "
                    "metadata.force_unknown_size=True (rule 12)"
                )

        # A clean (unblocked) execute_download plan must still be a mode v1
        # actually knows how to execute.
        if not blocked_reasons and acquisition_mode in _UNIMPLEMENTED_REMOTE_MODES:
            errors.append(
                f"acquisition_mode='{acquisition_mode}' has no implemented remote-fetch execution path in v1; "
                "an unblocked execute_download plan must use scan_existing_local/verify_existing_local"
            )

    # Rules 13/14: target_root must be a safe, contained local path.
    if target_root:
        from dataset_acquisition.store import TargetRootError, validate_target_root

        try:
            validate_target_root(target_root)
        except TargetRootError as exc:
            errors.append(f"target_root: {exc} (rule 13/14)")
    else:
        errors.append("target_root is required (rule 13/14)")

    # Rule 15.
    _check_forbidden_metadata_keys(metadata, errors)

    # Rule 16.
    for field_name in ("display_name", "source_url", "source_repository", "provenance"):
        _scan_banned_phrases(getattr(plan, field_name, None) or "", field_name, errors)
    for field_name in ("planned_steps", "blocked_reasons", "risks", "limitations", "execution_required_flags"):
        _scan_banned_phrases(getattr(plan, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)

    return errors


def validate_manifest(manifest: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(manifest, "plan_id", None):
        errors.append("plan_id is required")
    if not getattr(manifest, "candidate_id", None):
        errors.append("candidate_id is required")

    execution_status = getattr(manifest, "execution_status", None)
    if execution_status not in ALLOWED_EXECUTION_STATUS:
        errors.append(f"execution_status '{execution_status}' must be one of {sorted(ALLOWED_EXECUTION_STATUS)}")

    if not getattr(manifest, "risks", None):
        errors.append("risks must be a non-empty list")
    if not getattr(manifest, "limitations", None):
        errors.append("limitations must be a non-empty list")
    if not getattr(manifest, "provenance", None):
        errors.append("provenance is required")

    acquired_paths = getattr(manifest, "acquired_paths", None) or []
    acquired_file_count = getattr(manifest, "acquired_file_count", 0)
    acquired_size_bytes = getattr(manifest, "acquired_size_bytes", 0)

    if execution_status in ("planned_only", "blocked"):
        if acquired_paths:
            errors.append(f"execution_status='{execution_status}' must not have acquired_paths")
        if acquired_file_count:
            errors.append(f"execution_status='{execution_status}' must have acquired_file_count=0")
        if acquired_size_bytes:
            errors.append(f"execution_status='{execution_status}' must have acquired_size_bytes=0")

    metadata = getattr(manifest, "metadata", None) or {}
    _check_forbidden_metadata_keys(metadata, errors)

    for field_name in ("provenance", "repo_commit"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or "", field_name, errors)
    for field_name in ("risks", "limitations", "errors", "skipped_files", "acquired_paths", "dataset_record_paths", "artifact_record_paths"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)
    bids_summary = getattr(manifest, "bids_metadata_summary", None)
    if bids_summary:
        _scan_banned_phrases(bids_summary, "bids_metadata_summary", errors)

    return errors
