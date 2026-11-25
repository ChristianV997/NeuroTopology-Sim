"""Deterministic checksums for provenance tracking. Stdlib-only."""
from __future__ import annotations

import hashlib
import re


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace -- used both for checksums and for
    normalized-title dedup so trivial formatting differences don't hide
    (or create) a duplicate."""
    return re.sub(r"\s+", " ", text.strip().lower())


def content_checksum(text: str) -> str:
    """sha256 of the normalized text -- the ``source_checksum`` field."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def stable_source_id(*, doi: str | None, arxiv_id: str | None, title: str) -> str:
    """Deterministic id: prefer doi, then arxiv_id, then normalized title
    -- never a random UUID, so re-ingesting the same source always
    produces the same id and dedup/versioning can key off it directly."""
    if doi:
        basis = f"doi:{normalize_text(doi)}"
    elif arxiv_id:
        basis = f"arxiv:{normalize_text(arxiv_id)}"
    else:
        basis = f"title:{normalize_text(title)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def stable_claim_id(*, source_id: str, claim_text: str) -> str:
    basis = f"{source_id}:{normalize_text(claim_text)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
