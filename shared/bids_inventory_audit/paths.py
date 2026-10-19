"""BIDS relative-path parsing without identifier-bearing public results.

Parsing operates on caller-supplied strings only. The public parser reports structural
properties but omits the path and subject/session labels. The inventory's private parser
retains those labels only in memory for aggregate cross-checks; it never serializes them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .schema import BACKUP_SUFFIXES, ENTITY_RE, SUBJECT_RE, SUFFIX_RE

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class ParsedPath:
    """Public parse summary. It intentionally contains no raw path or subject label."""

    valid: bool
    is_subject_file: bool
    has_subject: bool = False
    has_session: bool = False
    task: Optional[str] = None
    run: Optional[str] = None
    suffix: Optional[str] = None
    extension: Optional[str] = None
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ParsedPath:
    """Internal parse state; identifier-bearing fields must never leave the audit."""

    relpath: str
    valid: bool
    is_subject_file: bool
    subject: Optional[str] = None
    session: Optional[str] = None
    task: Optional[str] = None
    run: Optional[str] = None
    suffix: Optional[str] = None
    extension: Optional[str] = None
    problems: tuple[str, ...] = ()

    def signature(self) -> tuple[Any, ...]:
        return (self.subject, self.session, self.task, self.run, self.suffix, self.extension)


def unsafe_reason(relpath: Any) -> Optional[str]:
    """Why a relative path is unsafe to treat as a dataset-relative name, or None."""
    if not isinstance(relpath, str):
        return "PATH_NOT_TEXT"
    if relpath == "" or relpath != relpath.strip():
        return "PATH_EMPTY_OR_PADDED"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in relpath):
        return "PATH_CONTROL_CHARACTER"
    if relpath.startswith("/") or _DRIVE_RE.match(relpath) or "\\" in relpath:
        return "PATH_UNSAFE"
    if any(segment in ("", ".", "..") for segment in relpath.split("/")):
        return "PATH_UNSAFE"
    return None


def _parse_bids_relpath(relpath: Any) -> _ParsedPath:
    reason = unsafe_reason(relpath)
    if reason is not None:
        return _ParsedPath(relpath="", valid=False, is_subject_file=False, problems=(reason,))

    segments = relpath.split("/")
    if not segments[0].startswith("sub-") or len(segments) < 2:
        return _ParsedPath(relpath=relpath, valid=True, is_subject_file=False)

    problems: list[str] = []
    subject_dir = segments[0]
    if not SUBJECT_RE.fullmatch(subject_dir):
        problems.append("SUBJECT_DIR_INVALID")

    filename = segments[-1]
    stem, dot, rest = filename.partition(".")
    extension = f".{rest}" if dot and rest else None
    if extension is None:
        problems.append("EXTENSION_MISSING")
    elif rest.rsplit(".", 1)[-1] in BACKUP_SUFFIXES:
        problems.append("EXTENSION_BACKUP_OR_TEMP")

    parts = stem.split("_") if stem else []
    if not stem or not parts:
        problems.append("FILENAME_EMPTY_STEM")
        return _ParsedPath(relpath, valid=False, is_subject_file=True, problems=tuple(problems))

    suffix = parts[-1]
    if not SUFFIX_RE.fullmatch(suffix):
        problems.append("SUFFIX_MALFORMED")
        suffix = None

    entities: dict[str, str] = {}
    entity_parts = parts[:-1]
    if entity_parts and not entity_parts[0].startswith("sub-"):
        problems.append("SUBJECT_ENTITY_NOT_FIRST")
    for part in entity_parts:
        match = ENTITY_RE.fullmatch(part)
        if match is None:
            problems.append("ENTITY_MALFORMED")
            continue
        key, value = match.groups()
        if key in entities:
            problems.append(f"DUPLICATE_ENTITY:{key}")
            continue
        entities[key] = value

    if "sub" not in entities:
        problems.append("SUBJECT_ENTITY_MISSING")
        subject = None
    else:
        subject = f"sub-{entities['sub']}"
        if subject != subject_dir:
            problems.append("PATH_SUBJECT_MISMATCH")

    return _ParsedPath(
        relpath=relpath,
        valid=not problems,
        is_subject_file=True,
        subject=subject,
        session=f"ses-{entities['ses']}" if "ses" in entities else None,
        task=entities.get("task"),
        run=entities.get("run"),
        suffix=suffix,
        extension=extension,
        problems=tuple(problems),
    )


def parse_bids_relpath(relpath: Any) -> ParsedPath:
    """Return only structural facts about a caller-supplied path; omit raw identifiers."""
    parsed = _parse_bids_relpath(relpath)
    return ParsedPath(
        valid=parsed.valid,
        is_subject_file=parsed.is_subject_file,
        has_subject=parsed.subject is not None,
        has_session=parsed.session is not None,
        task=parsed.task,
        run=parsed.run,
        suffix=parsed.suffix,
        extension=parsed.extension,
        problems=parsed.problems,
    )
