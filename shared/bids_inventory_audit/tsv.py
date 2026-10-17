"""Strict reader for a participants table given as text.

The caller supplies the text. Nothing here opens a file. Any row that cannot be trusted is
reported with its line number and excluded. A participant id that appears more than once
is excluded entirely, because the table is ambiguous about it.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .findings import make_finding
from .schema import SUBJECT_RE

_BOM = "﻿"


@dataclass(frozen=True)
class TsvResult:
    participants: tuple[str, ...]
    accepted_rows: int
    rejected_rows: int
    blank_lines: int
    findings: tuple[dict[str, Any], ...]


def _fail_closed(code: str, detail: str, findings: list, rejected: int = 0, blank: int = 0) -> TsvResult:
    findings.append(make_finding(code, "error", detail))
    return TsvResult((), 0, rejected, blank, tuple(findings))


def parse_participants_tsv(text: Any) -> TsvResult:
    findings: list[dict[str, Any]] = []
    if not isinstance(text, str):
        return _fail_closed("TSV_NOT_TEXT", "participants table must be text", findings)
    if text.startswith(_BOM):
        text = text[len(_BOM):]
        findings.append(make_finding("BOM_STRIPPED", "info", "leading byte-order mark removed before parsing"))

    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the newline that ends the last line is not a blank line

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
    duplicated = sorted({column for column in header if header.count(column) > 1})
    if duplicated:
        return _fail_closed("DUPLICATE_HEADER_COLUMN", f"repeated header columns: {duplicated}",
                            findings, blank=blank)
    if "participant_id" not in header:
        return _fail_closed("HEADER_MISSING_PARTICIPANT_ID", "header has no participant_id column",
                            findings, blank=blank)

    id_column = header.index("participant_id")
    candidates: list[tuple[str, int]] = []
    rejected = 0
    for index in range(header_index + 1, len(lines)):
        line_no = index + 1  # 1-based physical line number
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
                "participant_id must match sub-<alphanumeric>", line=line_no))
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
                line=line_no, subject=participant))
            continue
        accepted.append(participant)

    participants = tuple(sorted(accepted))
    return TsvResult(
        participants=participants,
        accepted_rows=len(participants),
        rejected_rows=rejected,
        blank_lines=blank,
        findings=tuple(findings),
    )
