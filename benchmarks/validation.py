"""Structural validation for benchmark dataset/artifact records.

Field-level and governance checks only: "is this record well-formed and
non-overclaiming," not "may this specific use proceed" (that's
`benchmarks.split_policy`) and not "is this validation lock still fresh"
(that's `benchmarks.holdout_lock`). Reuses this repository's existing claim/
evidence vocabulary and banned-phrase scanner rather than declaring new
copies, mirroring how `transitions.governance` reuses
`sciencer_d.btc_icft.report_guardrails` instead of a fifth phrase list.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import (
    ALLOWED_CLAIM_SCOPES,
    ALLOWED_EVIDENCE_LEVELS,
    TRANSITION_EXTRA_BANNED_PHRASES,
)

from benchmarks.split_policy import (
    ALLOWED_USES,
    ALWAYS_BLOCKED_USES,
    CONFIRMATORY_CLAIM_USES,
    CONTAMINATION_STATUSES,
    DATASET_ROLES,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

RECORD_KINDS: frozenset[str] = frozenset({"committed_artifact", "candidate_unstructured"})

_KNOWN_RECORD_USE_VALUES = ALLOWED_USES | CONFIRMATORY_CLAIM_USES | ALWAYS_BLOCKED_USES


class RegistryValidationError(ValueError):
    """Raised when a benchmark dataset/artifact record fails structural validation."""


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
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


def _validate_common(record: Any, *, errors: list[str]) -> None:
    role = getattr(record, "current_role", None)
    if role not in DATASET_ROLES:
        errors.append(f"current_role '{role}' must be one of {sorted(DATASET_ROLES)}")

    contamination = getattr(record, "contamination_status", None)
    if contamination not in CONTAMINATION_STATUSES:
        errors.append(
            f"contamination_status '{contamination}' must be one of {sorted(CONTAMINATION_STATUSES)}"
        )

    allowed_uses = getattr(record, "allowed_uses", None) or []
    forbidden_uses = getattr(record, "forbidden_uses", None) or []

    for use in allowed_uses:
        if use not in _KNOWN_RECORD_USE_VALUES:
            errors.append(f"allowed_uses contains unknown use '{use}'")
        if use in ALWAYS_BLOCKED_USES:
            errors.append(f"allowed_uses must never contain always-blocked use '{use}' (rule 6)")
    for use in forbidden_uses:
        if use not in _KNOWN_RECORD_USE_VALUES:
            errors.append(f"forbidden_uses contains unknown use '{use}'")

    overlap = set(allowed_uses) & set(forbidden_uses)
    if overlap:
        errors.append(f"allowed_uses and forbidden_uses overlap: {sorted(overlap)}")

    claim_scope_ceiling = getattr(record, "claim_scope_ceiling", None)
    if claim_scope_ceiling not in ALLOWED_CLAIM_SCOPES:
        errors.append(
            f"claim_scope_ceiling '{claim_scope_ceiling}' must be one of {sorted(ALLOWED_CLAIM_SCOPES)}"
        )
    evidence_level_ceiling = getattr(record, "evidence_level_ceiling", None)
    if evidence_level_ceiling not in ALLOWED_EVIDENCE_LEVELS:
        errors.append(
            f"evidence_level_ceiling '{evidence_level_ceiling}' must be one of {sorted(ALLOWED_EVIDENCE_LEVELS)}"
        )

    # Rule 8: missing limitations fail validation.
    limitations = getattr(record, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list (rule 8)")
    elif any(not str(item).strip() for item in limitations):
        errors.append("limitations must not contain empty strings")

    lock = getattr(record, "validation_lock", None)
    if role in ("locked_internal_validation", "locked_external_validation"):
        if not lock:
            errors.append(
                f"role '{role}' requires validation_lock metadata (locked_at, locked_by, "
                "reason, allowed_claim_family) (rule 3)"
            )
        else:
            missing = [k for k in ("locked_at", "locked_by", "reason", "allowed_claim_family") if not lock.get(k)]
            if missing:
                errors.append(f"validation_lock is missing required keys: {missing} (rule 3)")

    if role == "prospective" and not getattr(record, "prospective_protocol_id", None):
        errors.append("role 'prospective' requires an explicit prospective_protocol_id (rule 4)")

    _scan_banned_phrases(limitations, "limitations", errors)
    _scan_banned_phrases(getattr(record, "metadata", None) or {}, "metadata", errors)
    label = getattr(record, "display_name", None) or getattr(record, "artifact_kind", None) or ""
    _scan_banned_phrases(label, "display_name_or_artifact_kind", errors)


def validate_dataset_record(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(record, "dataset_id", None):
        errors.append("dataset_id is required")
    if not getattr(record, "display_name", None):
        errors.append("display_name is required")
    if not getattr(record, "modalities", None):
        errors.append("modalities must be a non-empty list")

    # Rule 9: missing provenance fails validation. Every dataset in this
    # registry is a real, already-discussed dataset -- provenance is always
    # required, never optional, at the dataset level.
    if not getattr(record, "provenance", None):
        errors.append("provenance is required (rule 9)")

    _validate_common(record, errors=errors)
    return errors


def validate_artifact_record(record: Any, *, repo_root: Path = _REPO_ROOT) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(record, "artifact_id", None):
        errors.append("artifact_id is required")
    if not getattr(record, "dataset_id", None):
        errors.append("dataset_id is required")
    if not getattr(record, "path", None):
        errors.append("path is required")
    if not getattr(record, "artifact_kind", None):
        errors.append("artifact_kind is required")

    record_kind = getattr(record, "record_kind", None)
    if record_kind not in RECORD_KINDS:
        errors.append(f"record_kind '{record_kind}' must be one of {sorted(RECORD_KINDS)}")

    external = bool(getattr(record, "external", False))
    path_value = getattr(record, "path", None)
    if path_value:
        if not external and Path(path_value).is_absolute():
            errors.append(
                f"path '{path_value}' must be a relative repository path unless external=True (rule 10)"
            )
        # Rule 10: existence required for committed artifacts only, and only
        # when the path is not explicitly external.
        if record_kind == "committed_artifact" and not external:
            candidate = repo_root / path_value
            if not candidate.exists():
                errors.append(f"path '{path_value}' does not exist under {repo_root} (rule 10)")

    # Rule 9: missing provenance (produced_by) fails validation for committed artifacts.
    if record_kind == "committed_artifact" and not getattr(record, "produced_by", None):
        errors.append("produced_by is required for committed_artifact records (rule 9)")

    _validate_common(record, errors=errors)
    return errors
