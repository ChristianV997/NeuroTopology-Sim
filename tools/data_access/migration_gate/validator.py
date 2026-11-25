"""Validation rules enforcing fail-closed gating on migration inventory and exceptions."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .types import (
    PERMANENT_EXPIRATION_TOKENS,
    PROHIBITED_EXCEPTION_CATEGORIES,
    PROHIBITED_EXCEPTION_RULES,
    MigrationEntry,
    MigrationStatus,
)

_WILDCARD_PATTERN = re.compile(r"[\*\?\[\]]")
_DATE_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class EntryValidationResult:
    """Result of validating a single MigrationEntry."""

    is_valid: bool
    status: MigrationStatus
    errors: tuple[str, ...]
    is_prohibited_exception: bool = False
    is_stale: bool = False
    is_wildcard: bool = False
    is_permanent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status": self.status.value,
            "errors": list(self.errors),
            "is_prohibited_exception": self.is_prohibited_exception,
            "is_stale": self.is_stale,
            "is_wildcard": self.is_wildcard,
            "is_permanent": self.is_permanent,
        }


def is_wildcard_string(text: str | None) -> bool:
    """Check whether a string contains wildcards or glob patterns."""
    if not text:
        return False
    return bool(_WILDCARD_PATTERN.search(text))


def is_permanent_expiration(expires_at: str | None) -> bool:
    """Check if an expiration specification indicates a permanent or indefinite exception."""
    if expires_at is None:
        return True
    cleaned = str(expires_at).strip().lower()
    return cleaned in PERMANENT_EXPIRATION_TOKENS


def parse_iso_date(date_str: str | None) -> datetime.date | None:
    """Parse a strict YYYY-MM-DD ISO date string."""
    if not date_str or not isinstance(date_str, str):
        return None
    if not _DATE_ISO_PATTERN.match(date_str.strip()):
        return None
    try:
        return datetime.date.fromisoformat(date_str.strip())
    except ValueError:
        return None


def is_stale_expiration(expires_at: str | None, current_date: datetime.date | str | None = None) -> bool:
    """Check if an expiration date has passed relative to the evaluation date."""
    if expires_at is None:
        return True
    parsed_expiry = parse_iso_date(expires_at)
    if parsed_expiry is None:
        return True  # Malformed or unparseable expiration is treated as stale/invalid

    if current_date is None:
        cur = datetime.date.today()
    elif isinstance(current_date, datetime.date):
        cur = current_date
    elif isinstance(current_date, str):
        parsed_cur = parse_iso_date(current_date)
        cur = parsed_cur if parsed_cur is not None else datetime.date.today()
    else:
        cur = datetime.date.today()

    return parsed_expiry < cur


def is_prohibited_exception_rule(rule: str | None, category: str | None = None) -> tuple[bool, str]:
    """Determine if a rule or category is strictly prohibited from receiving exceptions."""
    rule_str = (rule or "").strip()
    cat_str = (category or "").strip().lower()

    if rule_str in PROHIBITED_EXCEPTION_RULES:
        return True, f"Rule '{rule_str}' belongs to prohibited exception class; exceptions are rejected."
    if cat_str in PROHIBITED_EXCEPTION_CATEGORIES:
        return True, f"Category '{cat_str}' belongs to prohibited exception categories; exceptions are rejected."
    return False, ""


def validate_migration_entry(
    entry: MigrationEntry | Mapping[str, Any],
    *,
    current_date: datetime.date | str | None = None,
) -> EntryValidationResult:
    """Strictly validate a migration entry against fail-closed requirements.

    Requirements:
    1. Exact file, symbol/line, owner, migration reference, and status.
    2. Rejects wildcards in file, symbol/line, or rule.
    3. Rejects permanent or unbounded exceptions.
    4. Rejects exceptions for full-dataset downloads, unbounded reads, missing checksums,
       output escapes, or network defaults.
    5. Rejects expired / stale exceptions.
    """
    errors: list[str] = []
    is_prohibited = False
    is_stale = False
    is_wildcard = False
    is_permanent = False

    # Extract fields safely
    if isinstance(entry, MigrationEntry):
        file_val = entry.file
        sym_val = entry.symbol_or_line
        rule_val = entry.rule
        owner_val = entry.owner
        ref_val = entry.migration_reference
        status_val = entry.status
        reviewer_val = entry.reviewer
        expires_val = entry.expires_at
        just_val = entry.justification
    elif isinstance(entry, Mapping):
        file_val = str(entry.get("file", ""))
        sym_val = str(entry.get("symbol_or_line", ""))
        rule_val = str(entry.get("rule", ""))
        owner_val = str(entry.get("owner", ""))
        ref_val = str(entry.get("migration_reference", ""))
        raw_status = entry.get("status")
        try:
            status_val = MigrationStatus(raw_status) if raw_status else MigrationStatus.UNABLE_TO_ASSESS
        except ValueError:
            status_val = MigrationStatus.UNABLE_TO_ASSESS
            errors.append(f"Invalid status value '{raw_status}'.")
        reviewer_val = entry.get("reviewer")
        expires_val = entry.get("expires_at")
        just_val = entry.get("justification")
    else:
        return EntryValidationResult(
            is_valid=False,
            status=MigrationStatus.UNABLE_TO_ASSESS,
            errors=("Entry must be MigrationEntry or Mapping.",),
        )

    # 1. Require exact, non-empty fields
    if not file_val or not file_val.strip():
        errors.append("Field 'file' is required and cannot be empty.")
    if not sym_val or not str(sym_val).strip():
        errors.append("Field 'symbol_or_line' is required and cannot be empty.")
    if not rule_val or not rule_val.strip():
        errors.append("Field 'rule' is required and cannot be empty.")
    if not owner_val or not owner_val.strip():
        errors.append("Field 'owner' is required and cannot be empty.")
    if not ref_val or not ref_val.strip():
        errors.append("Field 'migration_reference' is required and cannot be empty.")

    # 2. Reject wildcards
    if is_wildcard_string(file_val):
        is_wildcard = True
        errors.append(f"Wildcard in 'file' ('{file_val}') is strictly prohibited.")
    if is_wildcard_string(str(sym_val)):
        is_wildcard = True
        errors.append(f"Wildcard in 'symbol_or_line' ('{sym_val}') is strictly prohibited.")
    if is_wildcard_string(rule_val):
        is_wildcard = True
        errors.append(f"Wildcard in 'rule' ('{rule_val}') is strictly prohibited.")

    # 3. Reviewed Temporary Exception validations
    if status_val == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION:
        # Check prohibited rules
        prohibited, reason = is_prohibited_exception_rule(rule_val)
        if prohibited:
            is_prohibited = True
            errors.append(f"Prohibited exception rule: {reason}")

        # Check reviewer
        if not reviewer_val or not str(reviewer_val).strip():
            errors.append("Reviewed temporary exception requires a named 'reviewer'.")

        # Check justification
        if not just_val or not str(just_val).strip():
            errors.append("Reviewed temporary exception requires a non-empty 'justification'.")

        # Check permanent tokens
        if is_permanent_expiration(expires_val):
            is_permanent = True
            errors.append("Permanent or unbounded exceptions are strictly prohibited.")

        # Check date format and staleness
        parsed_expiry = parse_iso_date(expires_val)
        if parsed_expiry is None and not is_permanent:
            errors.append(f"Invalid expiration date format '{expires_val}'; must be YYYY-MM-DD.")
        elif parsed_expiry is not None:
            if is_stale_expiration(expires_val, current_date=current_date):
                is_stale = True
                errors.append(f"Exception expired on '{expires_val}'; stale exceptions are rejected.")

    # 4. Not Applicable validations
    elif status_val == MigrationStatus.NOT_APPLICABLE:
        if not just_val or not str(just_val).strip():
            errors.append("Status 'not applicable' requires a non-empty 'justification'.")

    # Determine resulting classification state
    final_status = status_val
    if is_prohibited or is_permanent or (status_val == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION and (is_stale or is_wildcard)):
        final_status = MigrationStatus.UNSAFE_BLOCKED
    elif errors and status_val != MigrationStatus.UNSAFE_BLOCKED:
        final_status = MigrationStatus.UNABLE_TO_ASSESS

    return EntryValidationResult(
        is_valid=len(errors) == 0,
        status=final_status,
        errors=tuple(errors),
        is_prohibited_exception=is_prohibited,
        is_stale=is_stale,
        is_wildcard=is_wildcard,
        is_permanent=is_permanent,
    )
