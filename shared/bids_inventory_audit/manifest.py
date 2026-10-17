"""Deterministic digest of a file listing, kept separate from every other concept here.

This is a read-only function over a listing the caller supplies: ``(relative_path, bytes)``
pairs. It never walks a directory and never opens a file. The digest identifies a listing,
not a dataset release, not a registration, and not an analysis cohort. The same listing
gives the same digest regardless of input order.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable

from .findings import make_finding, sort_findings
from .paths import unsafe_reason
from .schema import REGISTRATION_STATUS, SCHEMA

_KIND = "READ_ONLY_FILE_LISTING_DIGEST"
_STATEMENT = (
    "This digest covers the supplied listing only. It does not identify a dataset release, a cohort, "
    "or a registration, and it creates no external timestamp."
)


def file_listing_digest(entries: Iterable[Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    try:
        items = list(entries)
    except TypeError:
        findings.append(make_finding("ENTRIES_NOT_ITERABLE", "error", "entries must be an iterable of pairs"))
        return _result(0, None, findings)

    records: list[tuple[str, bytes]] = []
    counts: Counter[str] = Counter()
    for index, entry in enumerate(items):
        if not (isinstance(entry, tuple) and len(entry) == 2):
            findings.append(make_finding("ENTRY_MALFORMED", "error",
                                         "each entry must be a (relative_path, bytes) pair",
                                         path=f"entry[{index}]"))
            continue
        relpath, content = entry
        reason = unsafe_reason(relpath)
        if reason is not None:
            findings.append(make_finding(reason, "error", "relative path rejected",
                                         path=relpath if isinstance(relpath, str) and reason != "PATH_CONTROL_CHARACTER" else f"entry[{index}]"))
            continue
        if not isinstance(content, (bytes, bytearray)):
            findings.append(make_finding("CONTENT_NOT_BYTES", "error", "content must be bytes", path=relpath))
            continue
        counts[relpath] += 1
        records.append((relpath, bytes(content)))

    for relpath, count in sorted(counts.items()):
        if count > 1:
            findings.append(make_finding("DUPLICATE_PATH", "error",
                                         "a path appears more than once; no digest is produced", path=relpath))

    if any(finding["severity"] == "error" for finding in findings):
        return _result(len(items), None, findings)

    lines = [f"{relpath}\t{hashlib.sha256(content).hexdigest()}\n" for relpath, content in sorted(records)]
    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    return _result(len(items), digest, findings)


def _result(entries_listed: int, digest: Any, findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": _KIND,
        "entries_listed": entries_listed,
        "manifest_sha256": digest,
        "registration_status": REGISTRATION_STATUS,
        "external_timestamp_created": False,
        "dataset_identity_claim": False,
        "statement": _STATEMENT,
        "findings": sort_findings(findings),
    }
