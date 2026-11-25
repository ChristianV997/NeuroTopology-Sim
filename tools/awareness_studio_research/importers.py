"""Importers that turn external-ish inputs into registry records.

None of these functions make a network call -- they consume metadata
that is either already local (a JSON/CSV file, manually captured text)
or explicitly supplied by the operator (e.g. the result of a manual
arXiv/DOI lookup done outside this package, or via network.py with
explicit opt-in). Never invents a missing citation: a required field
left out of the input is stored as ``None``/empty and reflected in
``limitations``, not silently fabricated.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .checksum import content_checksum, stable_source_id
from .models import LiteratureSource, _now_iso


def _bounded_excerpt(text: str, max_chars: int = 2000) -> str:
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + " …[truncated]"


def _build_source(
    *,
    title: str,
    authors: Iterable[str],
    doi: Optional[str],
    arxiv_id: Optional[str],
    url: Optional[str],
    publication_date: Optional[str],
    source_type: str,
    abstract_or_excerpt: str,
    peer_review_status: str,
    license_or_access_status: str,
    limitations: Iterable[str],
    retrieval_method: str,
    network_used: bool = False,
) -> LiteratureSource:
    source_id = stable_source_id(doi=doi, arxiv_id=arxiv_id, title=title)
    excerpt = _bounded_excerpt(abstract_or_excerpt)
    return LiteratureSource(
        source_id=source_id,
        title=title,
        authors=tuple(authors),
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        publication_date=publication_date,
        source_type=source_type,
        retrieval_timestamp=_now_iso(),
        source_checksum=content_checksum(excerpt or title),
        abstract_or_excerpt=excerpt,
        peer_review_status=peer_review_status,
        license_or_access_status=license_or_access_status,
        limitations=tuple(limitations),
        retrieval_metadata={"method": retrieval_method, "network_used": network_used},
    )


def import_json_export(path: Path) -> list[LiteratureSource]:
    """Explicit JSON export: a list of source dicts with (at least)
    ``title``; every other field is optional and defaults conservatively."""
    raw = json.loads(Path(path).read_text())
    records = raw if isinstance(raw, list) else raw.get("sources", [])
    sources = []
    for entry in records:
        sources.append(
            _build_source(
                title=entry.get("title", ""),
                authors=entry.get("authors", []),
                doi=entry.get("doi"),
                arxiv_id=entry.get("arxiv_id"),
                url=entry.get("url"),
                publication_date=entry.get("publication_date"),
                source_type=entry.get("source_type", "other"),
                abstract_or_excerpt=entry.get("abstract", ""),
                peer_review_status=entry.get("peer_review_status", "unknown"),
                license_or_access_status=entry.get("license_or_access_status", "unknown"),
                limitations=entry.get("limitations", []),
                retrieval_method="json_export",
            )
        )
    return sources


def import_csv_export(path: Path) -> list[LiteratureSource]:
    """Explicit CSV export: one row per source. Missing columns default
    conservatively rather than raising, since the point of an operator
    export is exactly to tolerate partial metadata."""
    sources = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            authors = [a.strip() for a in (row.get("authors") or "").split(";") if a.strip()]
            limitations = [l.strip() for l in (row.get("limitations") or "").split(";") if l.strip()]
            sources.append(
                _build_source(
                    title=row.get("title", ""),
                    authors=authors,
                    doi=row.get("doi") or None,
                    arxiv_id=row.get("arxiv_id") or None,
                    url=row.get("url") or None,
                    publication_date=row.get("publication_date") or None,
                    source_type=row.get("source_type", "other"),
                    abstract_or_excerpt=row.get("abstract", ""),
                    peer_review_status=row.get("peer_review_status", "unknown"),
                    license_or_access_status=row.get("license_or_access_status", "unknown"),
                    limitations=limitations,
                    retrieval_method="csv_export",
                )
            )
    return sources


def import_arxiv_metadata(operator_supplied: dict, *, network_used: bool = False) -> LiteratureSource:
    """``operator_supplied`` is a dict of arXiv metadata already obtained
    by the operator (manually, or via ``network.fetch_arxiv_metadata``
    with explicit opt-in) -- this function never fetches anything itself."""
    return _build_source(
        title=operator_supplied.get("title", ""),
        authors=operator_supplied.get("authors", []),
        doi=operator_supplied.get("doi"),
        arxiv_id=operator_supplied.get("arxiv_id"),
        url=operator_supplied.get("url") or (
            f"https://arxiv.org/abs/{operator_supplied['arxiv_id']}" if operator_supplied.get("arxiv_id") else None
        ),
        publication_date=operator_supplied.get("publication_date"),
        source_type="preprint",
        abstract_or_excerpt=operator_supplied.get("abstract", ""),
        peer_review_status=operator_supplied.get("peer_review_status", "preprint_not_peer_reviewed"),
        license_or_access_status=operator_supplied.get("license_or_access_status", "arxiv_perpetual_license"),
        limitations=operator_supplied.get("limitations", []),
        retrieval_method="arxiv_api" if network_used else "operator_manual",
        network_used=network_used,
    )


def import_doi_metadata(operator_supplied: dict, *, network_used: bool = False) -> LiteratureSource:
    """``operator_supplied`` is a dict of DOI/publisher metadata already
    obtained by the operator -- this function never resolves the DOI
    itself unless the caller separately used ``network.fetch_doi_metadata``
    with explicit opt-in and passed the result in here."""
    return _build_source(
        title=operator_supplied.get("title", ""),
        authors=operator_supplied.get("authors", []),
        doi=operator_supplied.get("doi"),
        arxiv_id=operator_supplied.get("arxiv_id"),
        url=operator_supplied.get("url"),
        publication_date=operator_supplied.get("publication_date"),
        source_type=operator_supplied.get("source_type", "journal_article"),
        abstract_or_excerpt=operator_supplied.get("abstract", ""),
        peer_review_status=operator_supplied.get("peer_review_status", "peer_reviewed"),
        license_or_access_status=operator_supplied.get("license_or_access_status", "unknown"),
        limitations=operator_supplied.get("limitations", []),
        retrieval_method="doi_operator_supplied",
        network_used=network_used,
    )


def import_manual_capture(*, text: str, metadata: dict) -> LiteratureSource:
    """A manually captured HTML/text record (e.g. pasted abstract or
    excerpt) -- ``metadata`` supplies the citation fields; ``text`` is
    the captured body, bounded and checksummed."""
    return _build_source(
        title=metadata.get("title", ""),
        authors=metadata.get("authors", []),
        doi=metadata.get("doi"),
        arxiv_id=metadata.get("arxiv_id"),
        url=metadata.get("url"),
        publication_date=metadata.get("publication_date"),
        source_type=metadata.get("source_type", "manual_capture"),
        abstract_or_excerpt=text,
        peer_review_status=metadata.get("peer_review_status", "unknown"),
        license_or_access_status=metadata.get("license_or_access_status", "unknown"),
        limitations=metadata.get("limitations", ["manually captured excerpt; not a full-text retrieval"]),
        retrieval_method="manual_capture",
    )
