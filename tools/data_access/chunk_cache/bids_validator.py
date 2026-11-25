"""Validation and parsing for OpenNeuro/BIDS paths with traversal prevention.

Enforces BIDS specification structure and protects against malicious path
components or escapes outside the cache directory.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from tools.data_access.chunk_cache.types import BIDSPathComponents

# BIDS naming patterns
_SUB_PATTERN = re.compile(r"^sub-[a-zA-Z0-9]+$")
_SES_PATTERN = re.compile(r"^ses-[a-zA-Z0-9]+$")
_ALLOWED_DATATYPES = {
    "eeg", "ieeg", "meg", "anat", "func", "dwi", "fmap", "beh", "perf", "pet", "micr"
}
_TOP_LEVEL_FILES = {
    "participants.tsv",
    "participants.json",
    "dataset_description.json",
    "README",
    "CHANGES",
    "LICENSE",
    "task-*.json",
}


class BIDSValidationError(ValueError):
    """Raised when a BIDS path is invalid or violates security constraints."""


def normalize_bids_relative_path(path_str: str | Path) -> str:
    """Normalize path to POSIX relative form and reject any traversal attempts."""
    raw = str(path_str).replace("\\", "/")
    if not raw or "\x00" in raw:
        raise BIDSValidationError("BIDS path must be a non-empty string without null bytes")

    # Reject absolute paths or Windows drive letters
    if raw.startswith("/") or re.match(r"^[a-zA-Z]:", raw):
        raise BIDSValidationError(f"Absolute paths are forbidden: {raw}")

    # Reject parent traversal
    posix_path = PurePosixPath(raw)
    parts = [p for p in posix_path.parts if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise BIDSValidationError(f"Directory traversal ('..') is strictly forbidden: {raw}")

    # Reject dangerous characters
    for part in parts:
        if any(c in part for c in '<>:"|?*'):
            raise BIDSValidationError(f"Illegal characters detected in path component: {part}")

    return "/".join(parts)


def validate_bids_path(dataset_id: str, relative_path: str | Path) -> BIDSPathComponents:
    """Validate a BIDS relative path and extract structural entities.

    Args:
        dataset_id: OpenNeuro dataset identifier (e.g. 'ds005620').
        relative_path: Relative path within dataset (e.g. 'sub-01/eeg/sub-01_task-rest_eeg.edf').

    Returns:
        BIDSPathComponents containing parsed tokens.

    Raises:
        BIDSValidationError: If path is structurally malformed or escapes containment.
    """
    clean_ds = dataset_id.strip()
    if not re.fullmatch(r"ds[0-9]{6}", clean_ds, re.IGNORECASE):
        # Also allow test or custom datasets matching general alphanumeric
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", clean_ds):
            raise BIDSValidationError(f"Invalid dataset ID: {dataset_id}")

    norm_path = normalize_bids_relative_path(relative_path)
    parts = norm_path.split("/")

    # Top-level dataset files
    if len(parts) == 1:
        fname = parts[0]
        ext = "".join(Path(fname).suffixes)
        suffix = fname[:-len(ext)] if ext else fname
        return BIDSPathComponents(
            dataset_id=clean_ds,
            subject="",
            session=None,
            datatype=None,
            task=None,
            run=None,
            acquisition=None,
            suffix=suffix,
            extension=ext,
            relative_path=norm_path,
        )

    # Subject level: sub-<id>/[ses-<id>/]<datatype>/filename
    sub_part = parts[0]
    if not _SUB_PATTERN.match(sub_part):
        raise BIDSValidationError(f"First directory component must be 'sub-<label>', got: {sub_part}")

    session: str | None = None
    datatype: str | None = None
    filename: str

    if len(parts) == 3:
        # sub-<id>/<datatype>/<filename>
        datatype = parts[1].lower()
        filename = parts[2]
    elif len(parts) == 4:
        # sub-<id>/ses-<id>/<datatype>/<filename>
        ses_part = parts[1]
        if not _SES_PATTERN.match(ses_part):
            raise BIDSValidationError(f"Second directory component must be 'ses-<label>', got: {ses_part}")
        session = ses_part
        datatype = parts[2].lower()
        filename = parts[3]
    else:
        raise BIDSValidationError(f"Unexpected BIDS directory depth ({len(parts)} levels) for: {norm_path}")

    # Validate filename components
    ext = "".join(Path(filename).suffixes)
    stem = filename[:-len(ext)] if ext else filename
    tokens = stem.split("_")

    if not tokens[0].startswith("sub-"):
        raise BIDSValidationError(f"BIDS filename must start with subject prefix: {filename}")

    task: str | None = None
    run: str | None = None
    acq: str | None = None
    suffix = tokens[-1]

    for tok in tokens[1:-1]:
        if tok.startswith("task-"):
            task = tok[5:]
        elif tok.startswith("run-"):
            run = tok[4:]
        elif tok.startswith("acq-"):
            acq = tok[4:]

    return BIDSPathComponents(
        dataset_id=clean_ds,
        subject=sub_part,
        session=session,
        datatype=datatype,
        task=task,
        run=run,
        acquisition=acq,
        suffix=suffix,
        extension=ext,
        relative_path=norm_path,
    )
