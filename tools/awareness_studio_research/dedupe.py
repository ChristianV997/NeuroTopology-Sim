"""Deduplication signals for literature sources: DOI, arXiv ID,
normalized title, and content checksum. Freshly, independently
implemented for this package."""
from __future__ import annotations

from typing import Iterable, Optional

from .checksum import normalize_text
from .models import LiteratureSource


def duplicate_reasons(candidate: LiteratureSource, existing: LiteratureSource) -> list[str]:
    reasons: list[str] = []
    if candidate.doi and existing.doi and normalize_text(candidate.doi) == normalize_text(existing.doi):
        reasons.append("doi_match")
    if (
        candidate.arxiv_id
        and existing.arxiv_id
        and normalize_text(candidate.arxiv_id) == normalize_text(existing.arxiv_id)
    ):
        reasons.append("arxiv_id_match")
    if normalize_text(candidate.title) == normalize_text(existing.title) and candidate.title:
        reasons.append("normalized_title_match")
    if (
        candidate.source_checksum
        and existing.source_checksum
        and candidate.source_checksum == existing.source_checksum
    ):
        reasons.append("checksum_match")
    return reasons


def find_duplicates(
    candidate: LiteratureSource, existing_sources: Iterable[LiteratureSource]
) -> list[tuple[LiteratureSource, list[str]]]:
    """Return every existing source (other than ``candidate`` itself, by
    id) that shares at least one dedup signal, in deterministic
    (source_id-sorted) order."""
    findings = []
    for existing in sorted(existing_sources, key=lambda s: s.source_id):
        if existing.source_id == candidate.source_id:
            continue
        reasons = duplicate_reasons(candidate, existing)
        if reasons:
            findings.append((existing, reasons))
    return findings
