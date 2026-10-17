"""Read-only BIDS relative-path parsing.

Pure string handling. Nothing here touches the filesystem, so a path can be classified
without being opened. The grammar is the BIDS entity pattern, deliberately narrow:
``sub-<label>[_<key>-<value>]*_<suffix>.<extension>``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .schema import BACKUP_SUFFIXES, ENTITY_RE, SUBJECT_RE, SUFFIX_RE

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class ParsedPath:
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
        """Entity identity used to detect two files that claim the same BIDS slot."""
        return (self.subject, self.session, self.task, self.run, self.suffix, self.extension)


def unsafe_reason(relpath: Any) -> Optional[str]:
    """Why a relative path is unsafe to treat as a dataset-relative name, or None."""
    if not isinstance(relpath, str):
        return "PATH_NOT_TEXT"
    if relpath == "" or relpath != relpath.strip():
        return "PATH_EMPTY_OR_PADDED"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in relpath):
        return "PATH_CONTROL_CHARACTER"  # tabs and newlines would corrupt a line-based listing
    if relpath.startswith("/") or _DRIVE_RE.match(relpath) or "\\" in relpath:
        return "PATH_UNSAFE"
    if any(segment in ("", ".", "..") for segment in relpath.split("/")):
        return "PATH_UNSAFE"
    return None


def parse_bids_relpath(relpath: Any) -> ParsedPath:
    reason = unsafe_reason(relpath)
    if reason is not None:
        return ParsedPath(relpath=relpath if isinstance(relpath, str) else "", valid=False,
                          is_subject_file=False, problems=(reason,))

    segments = relpath.split("/")
    if not segments[0].startswith("sub-") or len(segments) < 2:
        # Root-level or non-subject files (participants.tsv, dataset_description.json, code/).
        return ParsedPath(relpath=relpath, valid=True, is_subject_file=False)

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
        return ParsedPath(relpath, valid=False, is_subject_file=True, problems=tuple(problems))

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

    return ParsedPath(
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
