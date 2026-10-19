"""Aggregate-only parsing of caller-supplied participants-table text.

This module never discovers or opens participant files. It parses text explicitly
provided by the caller. Subject labels are retained only in the private parser result
used by the inventory cross-check; the public result contains counts and safe findings.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .findings import make_finding
from .schema import SUBJECT_RE

_BOM = "\ufeff"


@dataclass(frozen=True)
class TsvResult:
    """Public, aggregate-only parse summary; never contains participant labels."""

    accepted_rows: int
    rejected_rows: int
    blank_lines: int
    findings: tuple[dict[str, Any], ...]


def _result(
    participants: tuple[str, ...],
    rejected_rows: int,
    blank_lines: int,
    findings: list[dict[str, Any]],
) -> tuple[TsvResult, tuple[str, ...]]:
    return (
        TsvResult(len(participants), rejected_rows, blank_lines, tuple(findings)),
        participants,
    )


def _fail_closed(
    code: str,
    detail: str,
    findings: list[dict[str, Any]],
    rejected: int = 0,
    blank: int = 0,
) -> tuple[TsvResult, tuple[str, ...]]:
    findings.append(make_finding(code, "error", detail))
    return _result((), rejected, blank, findings)


def _parse_participants_tsv(text: Any) -> tuple[TsvResult, tuple[str, ...]]:
    """Parse caller text for internal cross-checks and a separately safe summary."""
    findings: list[dict[str, Any]] = []
    if not isinstance(text, str):
        return _fail_closed("TSV_NOT_TEXT", "participants table must be text", findings)
    if text.startswith(_BOM):
        text = text[len(_BOM):]
        findings.append(make_finding("BOM_STRIPPED", "info", "leading byte-order mark removed before parsing"))

    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    blank = 0
    header_index = None
    for index, line in enumerate(lines):
        if line.strip() == "":
            blank += 1
            continue
        header_index = index
        break
    if header_index is None:
        return _fail_closed("EMPTY_TSV", "participants table has no header", findings, blank=blank)

    header = lines[header_index].split("\t")
    duplicated = {column for column in header if header.count(column) > 1}
    if duplicated:
        return _fail_closed("DUPLICATE_HEADER_COLUMN", "header contains repeated columns",
                            findings, blank=blank)
    if "participant_id" not in header:
        return _fail_closed("HEADER_MISSING_PARTICIPANT_ID", "header has no participant_id column",
                            findings, blank=blank)

    id_column = header.index("participant_id")
    candidates: list[tuple[str, int]] = []
    rejected = 0
    for index in range(header_index + 1, len(lines)):
        line_no = index + 1
        raw = lines[index]
        if raw.strip() == "":
            blank += 1
            findings.append(make_finding("BLANK_LINE", "info", "blank line skipped", line=line_no))
            continue
        cells = raw.split("\t")
        if len(cells) != len(header):
            rejected += 1
            findings.append(make_finding(
                "MALFORMED_ROW", "error",
                f"row has {len(cells)} cells; header has {len(header)}", line=line_no))
            continue
        participant = cells[id_column]
        if not SUBJECT_RE.fullmatch(participant):
            rejected += 1
            findings.append(make_finding(
                "INVALID_PARTICIPANT_ID", "error",
                "participant identifier does not match the required format", line=line_no))
            continue
        candidates.append((participant, line_no))

    counts = Counter(participant for participant, _ in candidates)
    accepted: list[str] = []
    for participant, line_no in candidates:
        if counts[participant] > 1:
            rejected += 1
            findings.append(make_finding(
                "DUPLICATE_PARTICIPANT", "error",
                "participant_id appears more than once; every occurrence is excluded",
                line=line_no))
            continue
        accepted.append(participant)

    participants = tuple(sorted(accepted))
    return _result(participants, rejected, blank, findings)


def parse_participants_tsv(text: Any) -> TsvResult:
    """Return an aggregate-only summary of explicitly supplied table text.

    Raw labels are not returned by this public function. ``audit_inventory`` uses the
    private parser result only transiently for in-memory cross-checks.
    """
    result, _ = _parse_participants_tsv(text)
    return result
