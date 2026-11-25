"""Strict, fail-closed validation rules for Reviewed Exception records.

Enforces:
- Exact file paths without wildcards or repository-wide scope.
- Exact line number (>0) or exact symbol without wildcards.
- Named owner and independent reviewer (separation of duties; no self-review).
- Mandatory migration issue reference (e.g. GH-123, #123).
- Strict expiry dates (max 90 days lifespan, fail-closed when expired).
- Rejection of any exception attempting to permit forbidden unsafe behaviors:
  * full_dataset_download
  * unbounded_remote_read
  * missing_checksum
  * output_root_escape
  * network_enabled_default
  * fabricated_provenance
"""
from __future__ import annotations

import datetime
from pathlib import Path
import re
from typing import Optional

from tools.data_access.exception_registry.models import (
    DATE_REGEX,
    FORBIDDEN_PERMITTED_BEHAVIORS,
    ISSUE_REF_REGEX,
    MAX_EXCEPTION_LIFESPAN_DAYS,
    REVIEWED_EXCEPTION_SCHEMA,
    ExceptionRecordStatus,
    ExceptionValidationResult,
    RejectionReasonCode,
    ReviewedExceptionRecord,
)

WILDCARD_CHARS = {"*", "?", "[", "]"}
REPOSITORY_WIDE_FILES = {".", "/", "*", "**", "**/*", "all", "any"}
DISALLOWED_OWNERS = {"*", "all", "any", "nobody", "none", "unknown", ""}


def _normalize_string(val: Optional[str]) -> str:
    return str(val or "").strip()


def _is_wildcard(val: str) -> bool:
    return any(c in val for c in WILDCARD_CHARS) or val in {"all", "any"}


def _parse_date(date_str: str) -> Optional[datetime.date]:
    if not DATE_REGEX.match(date_str):
        return None
    try:
        parts = [int(p) for p in date_str.split("-")]
        return datetime.date(parts[0], parts[1], parts[2])
    except (ValueError, IndexError):
        return None


def validate_exception_record(
    record: ReviewedExceptionRecord,
    as_of_date: Optional[str | datetime.date] = None,
) -> ExceptionValidationResult:
    """Validate a ReviewedExceptionRecord against all strict safety and compliance rules.

    Args:
        record: ReviewedExceptionRecord instance.
        as_of_date: Evaluation date (ISO string or datetime.date). Defaults to UTC today.

    Returns:
        ExceptionValidationResult with detailed rejection codes and status.
    """
    rejection_codes: list[str] = []
    rejection_messages: list[str] = []

    # 1. Schema version check
    if record.schema_version != REVIEWED_EXCEPTION_SCHEMA:
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append(
            f"Unsupported schema version '{record.schema_version}', expected '{REVIEWED_EXCEPTION_SCHEMA}'."
        )

    # 2. Exception ID check
    if not _normalize_string(record.exception_id):
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append("exception_id must not be empty.")

    # 3. Exact file checks (no wildcards, no repo-wide scope)
    norm_file = _normalize_string(record.exact_file).replace("\\", "/")
    if not norm_file:
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append("exact_file must not be empty.")
    elif _is_wildcard(norm_file):
        rejection_codes.append(RejectionReasonCode.WILDCARD_FILE.value)
        rejection_messages.append(f"exact_file '{norm_file}' contains wildcards; exact relative file path required.")
    elif norm_file.lower() in REPOSITORY_WIDE_FILES or norm_file.startswith("*"):
        rejection_codes.append(RejectionReasonCode.REPOSITORY_WIDE_SCOPE.value)
        rejection_messages.append(f"exact_file '{norm_file}' is repository-wide; must specify a single file.")
    elif "/" not in norm_file and not Path(norm_file).suffix:
        # Bare directory or unqualified broad token
        rejection_codes.append(RejectionReasonCode.REPOSITORY_WIDE_SCOPE.value)
        rejection_messages.append(f"exact_file '{norm_file}' appears to be a directory or unqualified scope.")

    # 4. Location precision check (exact_line > 0 or exact_symbol without wildcards)
    has_valid_line = record.exact_line is not None and isinstance(record.exact_line, int) and record.exact_line > 0
    norm_symbol = _normalize_string(record.exact_symbol)
    has_valid_symbol = bool(norm_symbol)

    if not has_valid_line and not has_valid_symbol:
        rejection_codes.append(RejectionReasonCode.MISSING_EXACT_LOCATION.value)
        rejection_messages.append("Must specify an exact line (positive integer) or exact symbol name.")

    if has_valid_symbol and _is_wildcard(norm_symbol):
        rejection_codes.append(RejectionReasonCode.WILDCARD_SYMBOL.value)
        rejection_messages.append(f"exact_symbol '{norm_symbol}' contains wildcards; exact symbol required.")

    # 5. Rule identifier checks
    norm_rule = _normalize_string(record.rule_identifier)
    if not norm_rule:
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append("rule_identifier must not be empty.")
    elif _is_wildcard(norm_rule):
        rejection_codes.append(RejectionReasonCode.WILDCARD_RULE.value)
        rejection_messages.append(f"rule_identifier '{norm_rule}' cannot be a wildcard.")

    # 6. Owner check (no ownerless, no wildcard owners)
    norm_owner = _normalize_string(record.owner).lower()
    if norm_owner in DISALLOWED_OWNERS or _is_wildcard(norm_owner):
        rejection_codes.append(RejectionReasonCode.OWNERLESS.value)
        rejection_messages.append(f"Invalid owner '{record.owner}'; must be a named individual or maintainer.")

    # 7. Reviewer check (required, must not be self-reviewed)
    norm_reviewer = _normalize_string(record.reviewer).lower()
    if not norm_reviewer or norm_reviewer in DISALLOWED_OWNERS or _is_wildcard(norm_reviewer):
        rejection_codes.append(RejectionReasonCode.MISSING_REVIEWER.value)
        rejection_messages.append(f"Invalid reviewer '{record.reviewer}'; designated reviewer required.")
    elif norm_reviewer == norm_owner:
        rejection_codes.append(RejectionReasonCode.SELF_REVIEW_PROHIBITED.value)
        rejection_messages.append(f"Owner '{record.owner}' cannot review their own exception (separation of duties).")

    # 8. Migration issue reference check
    norm_issue = _normalize_string(record.migration_issue)
    if not norm_issue:
        rejection_codes.append(RejectionReasonCode.MISSING_MIGRATION_ISSUE.value)
        rejection_messages.append("migration_issue must not be empty; tracking ticket/issue required.")
    elif not ISSUE_REF_REGEX.match(norm_issue):
        rejection_codes.append(RejectionReasonCode.INVALID_MIGRATION_ISSUE.value)
        rejection_messages.append(
            f"migration_issue '{norm_issue}' must match format (e.g., #123, GH-123, issue-123, or URL)."
        )

    # 9. Justification check
    norm_justification = _normalize_string(record.justification)
    if not norm_justification or len(norm_justification) < 10:
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append("justification must provide detailed technical rationale (at least 10 characters).")

    # 10. Date parsing and validation
    created_dt = _parse_date(_normalize_string(record.created_date))
    expiry_dt = _parse_date(_normalize_string(record.expiry_date))

    if not created_dt:
        rejection_codes.append(RejectionReasonCode.INVALID_DATE_FORMAT.value)
        rejection_messages.append(f"created_date '{record.created_date}' is invalid; must be YYYY-MM-DD.")

    if not expiry_dt:
        rejection_codes.append(RejectionReasonCode.PERMANENT_EXCEPTION.value)
        rejection_messages.append(
            f"expiry_date '{record.expiry_date}' is invalid or missing; permanent exceptions are strictly rejected."
        )

    expires_in_days: Optional[int] = None
    if created_dt and expiry_dt:
        if expiry_dt <= created_dt:
            rejection_codes.append(RejectionReasonCode.EXPIRED.value)
            rejection_messages.append(
                f"expiry_date ({expiry_dt}) must be strictly after created_date ({created_dt})."
            )

        lifespan_days = (expiry_dt - created_dt).days
        if lifespan_days > MAX_EXCEPTION_LIFESPAN_DAYS:
            rejection_codes.append(RejectionReasonCode.EXCESSIVE_LIFESPAN.value)
            rejection_messages.append(
                f"Exception lifespan ({lifespan_days} days) exceeds maximum allowed {MAX_EXCEPTION_LIFESPAN_DAYS} days."
            )

        # Fail-closed expiry check against evaluation date
        if as_of_date is None:
            eval_date = datetime.datetime.now(datetime.timezone.utc).date()
        elif isinstance(as_of_date, str):
            parsed_eval = _parse_date(as_of_date)
            eval_date = parsed_eval if parsed_eval else datetime.datetime.now(datetime.timezone.utc).date()
        else:
            eval_date = as_of_date

        expires_in_days = (expiry_dt - eval_date).days
        if eval_date > expiry_dt:
            rejection_codes.append(RejectionReasonCode.EXPIRED.value)
            rejection_messages.append(
                f"Exception expired on {expiry_dt} ({abs(expires_in_days)} days ago as of {eval_date})."
            )

    # 11. Forbidden Unsafe Behavior check (CRITICAL)
    if not record.permitted_behavior or not isinstance(record.permitted_behavior, list):
        rejection_codes.append(RejectionReasonCode.MALFORMED_RECORD.value)
        rejection_messages.append("permitted_behavior must be a non-empty list of specific allowed actions.")
    else:
        for permitted in record.permitted_behavior:
            norm_perm = str(permitted).lower().strip().replace("-", "_").replace(" ", "_")
            for forbidden_category, aliases in FORBIDDEN_PERMITTED_BEHAVIORS.items():
                if any(alias in norm_perm for alias in aliases):
                    rejection_codes.append(RejectionReasonCode.UNSAFE_BEHAVIOR_PERMITTED.value)
                    rejection_messages.append(
                        f"Exception attempts to permit prohibited unsafe behavior '{permitted}' "
                        f"in category '{forbidden_category}'. This is strictly disallowed."
                    )

    # 12. Prohibitions check
    if not record.prohibited_behavior or not isinstance(record.prohibited_behavior, list):
        rejection_codes.append(RejectionReasonCode.MISSING_PROHIBITIONS.value)
        rejection_messages.append("prohibited_behavior must be explicitly declared as a non-empty list.")

    # Determine status
    if not rejection_codes:
        status = ExceptionRecordStatus.ACTIVE.value
        is_valid = True
    elif RejectionReasonCode.MALFORMED_RECORD.value in rejection_codes:
        status = ExceptionRecordStatus.MALFORMED.value
        is_valid = False
    elif RejectionReasonCode.UNSAFE_BEHAVIOR_PERMITTED.value in rejection_codes:
        status = ExceptionRecordStatus.UNSAFE_REJECTED.value
        is_valid = False
    elif RejectionReasonCode.WILDCARD_FILE.value in rejection_codes or RejectionReasonCode.WILDCARD_SYMBOL.value in rejection_codes:
        status = ExceptionRecordStatus.WILDCARD_REJECTED.value
        is_valid = False
    elif RejectionReasonCode.PERMANENT_EXCEPTION.value in rejection_codes or RejectionReasonCode.EXCESSIVE_LIFESPAN.value in rejection_codes:
        status = ExceptionRecordStatus.PERMANENT_REJECTED.value
        is_valid = False
    elif RejectionReasonCode.OWNERLESS.value in rejection_codes:
        status = ExceptionRecordStatus.OWNERLESS_REJECTED.value
        is_valid = False
    elif RejectionReasonCode.EXPIRED.value in rejection_codes:
        status = ExceptionRecordStatus.EXPIRED.value
        is_valid = False
    else:
        status = ExceptionRecordStatus.MALFORMED.value
        is_valid = False

    # Update record status in place
    record.status = status
    record.rejection_reasons = list(rejection_messages)

    return ExceptionValidationResult(
        exception_id=record.exception_id,
        is_valid=is_valid,
        status=status,
        rejection_codes=rejection_codes,
        rejection_messages=rejection_messages,
        expires_in_days=expires_in_days,
        record=record,
    )
