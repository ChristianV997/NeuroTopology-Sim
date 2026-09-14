"""Record-level validation: rejects fabricated identifiers, missing
identity, invalid checksums, and unsupported publication status
(requirement 5). Priority order (first match wins), documented here so
it's clear which check "owns" a given rejection when a record fails
more than one:

1. rejected_missing_identity   -- identifier absent entirely
2. rejected_fabricated_identifier -- identifier present but structurally/
   checksum-invalid for its declared type
3. rejected_invalid_checksum   -- a declared content checksum is
   malformed, or does not match the actual local snapshot file's content
4. rejected_unsupported_publication_status -- publication_type or
   review_status is not a recognized value
5. valid                        -- every check above passed
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .checksum import file_checksum, is_well_formed_sha256
from .identifiers import validate_identifier
from .models import (
    LiteratureRecord,
    PUBLICATION_TYPES,
    REVIEW_STATUSES,
    SourceSnapshot,
    ValidationResult,
)


def validate_record(
    record: LiteratureRecord, snapshot: Optional[SourceSnapshot] = None
) -> ValidationResult:
    errors: list[str] = []

    if not record.identifier or not record.identifier.strip():
        return ValidationResult(state="rejected_missing_identity", errors=("identifier is missing/empty",))

    is_valid_identifier, reason = validate_identifier(record.identifier, record.identifier_type)
    if not is_valid_identifier:
        return ValidationResult(state="rejected_fabricated_identifier", errors=(reason,))

    if record.content_checksum is not None and not is_well_formed_sha256(record.content_checksum):
        return ValidationResult(
            state="rejected_invalid_checksum",
            errors=(f"content_checksum {record.content_checksum!r} is not a well-formed sha256 hex digest",),
        )
    if record.excerpt_hash is not None and not is_well_formed_sha256(record.excerpt_hash):
        return ValidationResult(
            state="rejected_invalid_checksum",
            errors=(f"excerpt_hash {record.excerpt_hash!r} is not a well-formed sha256 hex digest",),
        )

    if snapshot is not None and snapshot.source_id != record.source_id:
        return ValidationResult(state="rejected_invalid_checksum", errors=("snapshot source_id does not match literature source",))

    if snapshot is not None and snapshot.kind == "full_local_snapshot":
        if not snapshot.local_path:
            return ValidationResult(
                state="rejected_invalid_checksum",
                errors=("snapshot kind=full_local_snapshot but no local_path was provided",),
            )
        path = Path(snapshot.local_path)
        if not path.is_file():
            return ValidationResult(
                state="rejected_invalid_checksum",
                errors=(f"snapshot local_path {snapshot.local_path!r} does not exist -- cannot verify checksum",),
            )
        try:
            actual = file_checksum(path)
        except OSError as exc:
            return ValidationResult(state="rejected_invalid_checksum", errors=(f"cannot read local snapshot: {exc}",))
        if record.content_checksum and record.content_checksum != actual:
            return ValidationResult(state="rejected_invalid_checksum", errors=("literature content_checksum does not match local snapshot bytes",))
        if snapshot.content_checksum and snapshot.content_checksum != actual:
            return ValidationResult(
                state="rejected_invalid_checksum",
                errors=(
                    f"snapshot declared content_checksum={snapshot.content_checksum!r} "
                    f"does not match the actual file checksum={actual!r}",
                ),
            )

    if record.publication_type not in PUBLICATION_TYPES:
        return ValidationResult(
            state="rejected_unsupported_publication_status",
            errors=(f"publication_type={record.publication_type!r} is not one of {sorted(PUBLICATION_TYPES)}",),
        )
    if record.review_status not in REVIEW_STATUSES:
        return ValidationResult(
            state="rejected_unsupported_publication_status",
            errors=(f"review_status={record.review_status!r} is not one of {sorted(REVIEW_STATUSES)}",),
        )

    return ValidationResult(state="valid", errors=())
