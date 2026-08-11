"""Validation holdout locks for benchmark dataset/artifact records.

Mirrors `research_runtime.stage_policy.StageLock`'s issue/consume-once
pattern, not duplicated wholesale: that lock is keyed to a protocol_hash +
stage for a single run envelope, while this one is keyed to a claim_family
+ dataset/artifact record and is stored inside the record's own
`validation_lock` field so it travels with the record in the registry JSON
rather than living in a separate envelope directory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional


class HoldoutLockError(ValueError):
    """Raised when a validation-lock operation is invalid."""


@dataclass
class ValidationLock:
    locked_at: str
    locked_by: str
    reason: str
    allowed_claim_family: str
    consumed: bool = False
    consumed_at: Optional[str] = None
    consumed_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ValidationLock":
        return cls(
            locked_at=d.get("locked_at", ""),
            locked_by=d.get("locked_by", ""),
            reason=d.get("reason", ""),
            allowed_claim_family=d.get("allowed_claim_family", ""),
            consumed=bool(d.get("consumed", False)),
            consumed_at=d.get("consumed_at"),
            consumed_by=d.get("consumed_by"),
        )


def lock_for_validation(
    record: Any,
    *,
    locked_by: str,
    reason: str,
    claim_family: str,
    _now: Optional[datetime] = None,
) -> Any:
    """Attach a fresh ValidationLock to `record`, in place. Returns `record`.

    Requires the record's current_role to already be
    'locked_internal_validation' or 'locked_external_validation' -- this
    function records the lock, it does not itself decide whether the record
    should be promoted to a locked role (that is a human/governance
    decision reflected by setting current_role before calling this).
    """
    role = getattr(record, "current_role", None)
    if role not in ("locked_internal_validation", "locked_external_validation"):
        raise HoldoutLockError(
            "lock_for_validation requires current_role to already be "
            f"'locked_internal_validation' or 'locked_external_validation', got '{role}'"
        )
    if not locked_by or not reason or not claim_family:
        raise HoldoutLockError("lock_for_validation requires locked_by, reason, and claim_family")

    existing = getattr(record, "validation_lock", None)
    if existing and not existing.get("consumed"):
        raise HoldoutLockError(
            "record already carries an unconsumed validation_lock; consume or "
            "clear it before issuing a new one"
        )

    lock = ValidationLock(
        locked_at=(_now or datetime.now(timezone.utc)).isoformat(),
        locked_by=locked_by,
        reason=reason,
        allowed_claim_family=claim_family,
    )
    record.validation_lock = lock.to_dict()
    record.contamination_status = "confirmatory_locked"
    return record


def consume_validation_lock(
    record: Any,
    *,
    claim_family: str,
    consumed_by: str,
    _now: Optional[datetime] = None,
) -> Any:
    """Mark `record`'s validation_lock as consumed, in place. Returns `record`."""
    lock_dict = getattr(record, "validation_lock", None)
    if not lock_dict:
        raise HoldoutLockError("record has no validation_lock to consume")
    lock = ValidationLock.from_dict(lock_dict)
    if lock.consumed:
        raise HoldoutLockError(
            f"validation_lock was already consumed at {lock.consumed_at} by "
            f"{lock.consumed_by}; a consumed lock cannot be reused as fresh validation"
        )
    if claim_family != lock.allowed_claim_family:
        raise HoldoutLockError(
            f"claim_family '{claim_family}' does not match this lock's "
            f"allowed_claim_family '{lock.allowed_claim_family}'"
        )
    if not consumed_by:
        raise HoldoutLockError("consume_validation_lock requires consumed_by")

    lock.consumed = True
    lock.consumed_at = (_now or datetime.now(timezone.utc)).isoformat()
    lock.consumed_by = consumed_by
    record.validation_lock = lock.to_dict()
    record.contamination_status = "validation_consumed"
    return record
