"""Discovery-vs-confirmation use policy for benchmark dataset/artifact records.

Core principle (see docs/benchmark_dataset_registry.md): a dataset or
artifact can be used for discovery (exploration, feature design, theory
generation) or for confirmation (locked internal/external validation,
prospective testing, final claim confirmation) of a given claim family, but
never both for the *same* claim. Once a record has been seen by exploratory
code, an LLM, or a theory-generation module, it is marked contaminated, and
this module refuses to treat it as independent confirmatory evidence for
that same claim family again.

This module holds only the *use* decision (can X be used for Y). Structural
field validation lives in `benchmarks.validation`; lock issuance/consumption
lives in `benchmarks.holdout_lock`. Both this module and `validation.py`
operate on `record: Any` (duck-typed on shared attribute names) rather than
importing `DatasetRecordV1`/`ArtifactRecordV1` directly, mirroring how
`transitions.governance.validate_governance` validates
`transitions.record.TransitionRecordV1` objects structurally rather than by
import -- it avoids a circular import and keeps this module usable against
either record type without change.
"""
from __future__ import annotations

from typing import Any, Optional

DATASET_ROLES: frozenset[str] = frozenset(
    {
        "exploration",
        "development",
        "locked_internal_validation",
        "locked_external_validation",
        "prospective",
        "retired",
        "deprecated",
    }
)

CONTAMINATION_STATUSES: frozenset[str] = frozenset(
    {
        "unseen",
        "seen_by_exploration",
        "seen_by_llm",
        "seen_by_theory_generation",
        "seen_by_model_selection",
        "confirmatory_locked",
        "validation_consumed",
        "retired",
    }
)

# Legitimate pipeline actions a dataset/artifact record can be used for.
ALLOWED_USES: frozenset[str] = frozenset(
    {
        "transition_export",
        "phase_space_export",
        "feature_design",
        "theory_generation",
        "model_selection",
        "internal_validation",
        "external_validation",
        "prospective_prediction",
        "visualization",
        "documentation",
    }
)

# Terminal claim types layered on top of the "use" vocabulary above. These
# are what locked_internal_validation/locked_external_validation/prospective
# roles exist to eventually authorize -- they are not automatically granted
# by role alone, only by role + a valid, unconsumed, matching-claim-family
# validation_lock (see _check_lock below).
CONFIRMATORY_CLAIM_USES: frozenset[str] = frozenset(
    {
        "final_claim_confirmation",
        "cross_dataset_replication_claim",
        "prospective_prediction_claim",
    }
)

# Rule 6: always blocked, regardless of role, lock, or a record's own
# allowed_uses/forbidden_uses lists. Defense in depth -- a misconfigured
# seed record can never re-enable these by omission.
ALWAYS_BLOCKED_USES: frozenset[str] = frozenset(
    {
        "clinical_claim",
        "diagnostic_claim",
        "treatment_claim",
        "consciousness_biomarker_claim",
        "spiritual_attainment_claim",
        "mechanistic_causal_claim",
    }
)

KNOWN_USE_VALUES: frozenset[str] = ALLOWED_USES | CONFIRMATORY_CLAIM_USES | ALWAYS_BLOCKED_USES

_VALIDATION_USES: frozenset[str] = frozenset({"internal_validation", "external_validation"})
_LLM_THEORY_CONTAMINATION: frozenset[str] = frozenset({"seen_by_llm", "seen_by_theory_generation"})

_SEEN_KIND_TO_STATUS: dict[str, str] = {
    "exploration": "seen_by_exploration",
    "llm": "seen_by_llm",
    "theory_generation": "seen_by_theory_generation",
    "model_selection": "seen_by_model_selection",
}


class PolicyError(ValueError):
    """Raised by assert_allowed_use when a requested use is not permitted."""


def _role_of(record: Any) -> str:
    return getattr(record, "current_role", "") or ""


def _lock_of(record: Any) -> Optional[dict[str, Any]]:
    return getattr(record, "validation_lock", None)


def _check_lock(record: Any, *, claim_family: Optional[str]) -> tuple[bool, str]:
    lock = _lock_of(record)
    if not lock:
        return False, "record role requires validation_lock metadata, but none is present (rule 3)"
    required_keys = ("locked_at", "locked_by", "reason", "allowed_claim_family")
    missing = [k for k in required_keys if not lock.get(k)]
    if missing:
        return False, f"validation_lock is missing required metadata: {missing} (rule 3)"
    if lock.get("consumed"):
        return False, "validation_lock has already been consumed and cannot be reused as fresh validation"
    if claim_family is None:
        return False, "validation/confirmatory use requires an explicit claim_family to check against the lock"
    if claim_family != lock["allowed_claim_family"]:
        return False, (
            f"claim_family '{claim_family}' does not match this record's locked "
            f"allowed_claim_family '{lock['allowed_claim_family']}'"
        )
    return True, "lock valid"


def _can_use(record: Any, requested_use: str, *, claim_family: Optional[str]) -> tuple[bool, str]:
    # Rule 7: unknown requested uses fail closed.
    if requested_use not in KNOWN_USE_VALUES:
        return False, f"unknown requested use '{requested_use}' fails closed (rule 7)"

    # Rule 6: always blocked regardless of anything else.
    if requested_use in ALWAYS_BLOCKED_USES:
        return False, f"'{requested_use}' is always blocked by this registry (rule 6)"

    role = _role_of(record)
    contamination = getattr(record, "contamination_status", "unseen")
    forbidden = set(getattr(record, "forbidden_uses", None) or [])
    allowed = set(getattr(record, "allowed_uses", None) or [])

    # Rule 5: retired/deprecated records -- documentation/history only. This
    # is a hard ceiling *and* a guarantee: 'documentation' is allowed
    # regardless of whether it happens to be listed in allowed_uses (that
    # list is normally authored for the record's active/discovery phase,
    # not rewritten at retirement time), unless a record explicitly
    # forbids it.
    if role in ("retired", "deprecated") or contamination == "retired":
        if requested_use != "documentation":
            return False, f"record role '{role}' is retired/deprecated; only 'documentation' is permitted (rule 5)"
        if requested_use in forbidden:
            return False, f"'{requested_use}' is explicitly listed in this record's forbidden_uses"
        return True, "allowed (retired/deprecated, documentation only, rule 5)"

    # A record's own forbidden_uses list always wins over its allowed_uses.
    if requested_use in forbidden:
        return False, f"'{requested_use}' is explicitly listed in this record's forbidden_uses"

    if requested_use in CONFIRMATORY_CLAIM_USES:
        # Rule 1: exploration/development records cannot confirm a claim.
        if role in ("exploration", "development"):
            return False, (
                f"role '{role}' is discovery-stage; '{requested_use}' requires a "
                "locked_internal_validation, locked_external_validation, or "
                "prospective record (rule 1)"
            )
        if requested_use == "prospective_prediction_claim" and role != "prospective":
            return False, "prospective_prediction_claim requires role 'prospective' (rule 4)"
        if role == "prospective" and not getattr(record, "prospective_protocol_id", None):
            return False, "role 'prospective' requires an explicit prospective_protocol_id (rule 4)"
        if role in ("locked_internal_validation", "locked_external_validation"):
            ok, reason = _check_lock(record, claim_family=claim_family)
            if not ok:
                return False, reason
        if requested_use not in allowed:
            return False, f"'{requested_use}' is not in this record's allowed_uses"
        return True, "allowed"

    # Rule 2: LLM/theory-generation exposure blocks independent validation.
    if requested_use in _VALIDATION_USES and contamination in _LLM_THEORY_CONTAMINATION:
        return False, (
            f"contamination_status '{contamination}' means this record has already "
            "been seen by an LLM or theory-generation module and cannot serve as "
            "independent validation for the same claim family (rule 2)"
        )

    # Rule 3: locked validation roles require valid, unconsumed lock metadata,
    # and internal_validation/external_validation must match the record's own
    # locked role (an internal lock cannot authorize an external_validation use).
    if requested_use in _VALIDATION_USES:
        expected_role = (
            "locked_internal_validation" if requested_use == "internal_validation"
            else "locked_external_validation"
        )
        if role != expected_role:
            return False, f"'{requested_use}' requires role '{expected_role}', record has role '{role}'"
        ok, reason = _check_lock(record, claim_family=claim_family)
        if not ok:
            return False, reason

    # Rule 4: the prospective_prediction *use* (not the terminal claim) also
    # requires an explicit prospective protocol id once role is prospective.
    if requested_use == "prospective_prediction" and role == "prospective":
        if not getattr(record, "prospective_protocol_id", None):
            return False, "role 'prospective' requires an explicit prospective_protocol_id (rule 4)"

    if requested_use not in allowed:
        return False, f"'{requested_use}' is not in this record's allowed_uses"

    return True, "allowed"


def can_use_dataset(record: Any, requested_use: str, *, claim_family: Optional[str] = None) -> tuple[bool, str]:
    """Return (allowed, reason) for using `record` (a DatasetRecordV1-shaped
    object) for `requested_use`. Never raises."""
    return _can_use(record, requested_use, claim_family=claim_family)


def can_use_artifact(record: Any, requested_use: str, *, claim_family: Optional[str] = None) -> tuple[bool, str]:
    """Return (allowed, reason) for using `record` (an ArtifactRecordV1-shaped
    object) for `requested_use`. Never raises."""
    return _can_use(record, requested_use, claim_family=claim_family)


def assert_allowed_use(record: Any, requested_use: str, *, claim_family: Optional[str] = None) -> None:
    """Raise PolicyError if `requested_use` is not permitted for `record`."""
    allowed, reason = _can_use(record, requested_use, claim_family=claim_family)
    if not allowed:
        raise PolicyError(reason)


def mark_seen(record: Any, *, seen_by: str, note: Optional[str] = None) -> Any:
    """Mark a dataset/artifact record as contaminated by a given consumer kind, in place.

    `seen_by` must be one of 'exploration', 'llm', 'theory_generation', or
    'model_selection'. Refuses to mutate a record already at
    'confirmatory_locked', 'validation_consumed', or 'retired' -- those are
    terminal/managed states handled by `benchmarks.holdout_lock`, not by
    this function.
    """
    if seen_by not in _SEEN_KIND_TO_STATUS:
        raise PolicyError(
            f"unknown seen_by kind '{seen_by}'; choose one of {sorted(_SEEN_KIND_TO_STATUS)}"
        )
    current = getattr(record, "contamination_status", "unseen")
    if current in ("confirmatory_locked", "validation_consumed", "retired"):
        raise PolicyError(
            f"cannot mark_seen: record contamination_status is already '{current}' "
            "(a managed/terminal state, not a discovery-exposure state)"
        )
    record.contamination_status = _SEEN_KIND_TO_STATUS[seen_by]
    entry = seen_by if note is None else f"{seen_by}: {note}"
    seen_list = list(getattr(record, "seen_by", None) or [])
    seen_list.append(entry)
    record.seen_by = seen_list
    return record
