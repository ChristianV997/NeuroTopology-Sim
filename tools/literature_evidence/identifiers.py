"""Identifier format/checksum validation.

The lesson this session has repeatedly learned (first with git commit
hashes, later with DOI/arXiv identity resolution) is that a
well-formed-looking identifier is not the same as a real one. This
module never confirms a DOI/arXiv id actually resolves to a real paper
(that would require a network call, out of scope for this package) --
but it does refuse anything that fails even a basic, checkable
structural test, including a REAL check-digit computation for ISBNs,
which catches a fabricated-but-plausible-looking ISBN the same way a
truncated-then-padded git hash was caught elsewhere in this session.
"""
from __future__ import annotations

import re
from typing import Optional

_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_URL_RE = re.compile(r"^https?://[^\s]+\.[^\s]+$")


def _isbn10_check_digit_valid(digits: str) -> bool:
    if len(digits) != 10:
        return False
    total = 0
    for index, char in enumerate(digits):
        if char == "X" and index == 9:
            value = 10
        elif char.isdigit():
            value = int(char)
        else:
            return False
        total += (10 - index) * value
    return total % 11 == 0


def _isbn13_check_digit_valid(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(digits))
    return total % 10 == 0


def is_valid_isbn(value: str) -> bool:
    cleaned = value.replace("-", "").replace(" ", "").upper()
    if len(cleaned) == 10:
        return _isbn10_check_digit_valid(cleaned)
    if len(cleaned) == 13:
        return _isbn13_check_digit_valid(cleaned)
    return False


def validate_identifier(identifier: Optional[str], identifier_type: str) -> tuple[bool, Optional[str]]:
    """Returns ``(is_valid, reason_if_invalid)``. Never performs a
    network call -- purely structural/checksum validation."""
    if not identifier or not identifier.strip():
        return False, "identifier is missing/empty"

    identifier = identifier.strip()

    if identifier_type == "doi":
        if not _DOI_RE.match(identifier):
            return False, f"{identifier!r} is not a well-formed DOI (expected 10.NNNN/suffix)"
        return True, None

    if identifier_type == "arxiv":
        candidate = identifier.split(":", 1)[-1]  # tolerate an "arXiv:" prefix
        if not _ARXIV_RE.match(candidate):
            return False, f"{identifier!r} is not a well-formed arXiv id (expected YYMM.NNNNN)"
        return True, None

    if identifier_type == "isbn":
        if not is_valid_isbn(identifier):
            return False, f"{identifier!r} fails the ISBN check-digit computation -- a fabricated identifier"
        return True, None

    if identifier_type == "url":
        if not _URL_RE.match(identifier):
            return False, f"{identifier!r} is not a well-formed http(s) URL"
        return True, None

    # identifier_type == "other": only requires non-empty, already checked above.
    return True, None
