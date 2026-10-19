"""Deterministic digest of a file listing, kept separate from every other concept here.

This is a read-only function over a listing the caller supplies: ``(relative_path, bytes)``
pairs. It never walks a directory and never opens a file. The digest identifies a listing,
not a dataset release, not a registration, and not an analysis cohort. The same listing
gives the same digest regardless of input order.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable, Optional

from .findings import make_finding, sort_findings
from .paths import unsafe_reason
from .schema import PAYLOAD_ACCESS, REGISTRATION_STATUS, SCHEMA, external_registration_block

_KIND = "READ_ONLY_FILE_LISTING_DIGEST"
_STATEMENT = (
    "This digest covers the supplied listing only. It does not identify a dataset release, a cohort, "
    "or a registration, and it creates no external timestamp. The deterministic unsalted digest may "
    "be linkable or guessable from known paths and content; it is pseudonymous, not anonymization."
)


def file_listing_digest(entries: Iterable[Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    try:
        items = list(entries)
    except Exception:
        findings.append(make_finding(
            "ENTRIES_NOT_ITERABLE", "error",
            "the supplied entries iterable could not be consumed; no entry values were retained"))
        return _result(None, None, findings)

    records: list[tuple[str, bytes]] = []
    counts: Counter[str] = Counter()
    for index, entry in enumerate(items):
        if not (isinstance(entry, tuple) and len(entry) == 2):
            findings.append(make_finding("ENTRY_MALFORMED", "error",
                                         "each entry must be a (relative_path, bytes) pair",
                                         entry_index=index))
            continue
        relpath, content = entry
        reason = unsafe_reason(relpath)
        if reason is not None:
            findings.append(make_finding(reason, "error", "relative path rejected",
                                         entry_index=index))
            continue
        if not isinstance(content, (bytes, bytearray)):
            findings.append(make_finding("CONTENT_NOT_BYTES", "error", "content must be bytes",
                                         entry_index=index))
            continue
        if len(content) == 0:
            # An empty payload is never a valid analysis input, so it is refused rather than hashed.
            findings.append(make_finding("PAYLOAD_EMPTY", "error",
                                         "empty payload rejected; no digest is produced", entry_index=index))
            continue
        counts[relpath] += 1
        records.append((relpath, bytes(content)))

    for relpath, count in sorted(counts.items()):
        if count > 1:
            findings.append(make_finding("DUPLICATE_PATH", "error",
                                         "a relative path appears more than once; no digest is produced",
                                         affected_count=1))

    if any(finding["severity"] == "error" for finding in findings):
        return _result(len(items), None, findings)

    lines = [f"{relpath}\t{hashlib.sha256(content).hexdigest()}\n" for relpath, content in sorted(records)]
    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    return _result(len(items), digest, findings)


def _result(entries_listed: Optional[int], digest: Any, findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": _KIND,
        "entries_listed": entries_listed,
        "manifest_sha256": digest,
        "registration_status": REGISTRATION_STATUS,
        "external_registration": external_registration_block(),
        "external_timestamp_created": False,
        "dataset_identity_claim": False,
        "payload_access": PAYLOAD_ACCESS,
        "statement": _STATEMENT,
        "findings": sort_findings(findings),
    }
