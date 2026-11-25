"""Compares an operator/prompt-claimed source description against an
independently confirmed metadata record, and produces an explicit list
of disagreements. Never assumes the claimed metadata is correct; a
field that could not be independently confirmed is reported as
"unconfirmed", not silently accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .checksum import normalize_text
from .models import EVIDENCE_TIERS, VERIFICATION_STATUSES


@dataclass(frozen=True)
class VerificationResult:
    verification_status: str  # "verified" | "unverified" | "disputed"
    evidence_tier: str
    disagreements: tuple[str, ...]


def verify_source_claim(
    *,
    claimed_title: str,
    claimed_doi: Optional[str],
    claimed_arxiv_id: Optional[str],
    confirmed: Optional[dict],
) -> VerificationResult:
    """``confirmed`` is an operator-supplied dict of independently
    obtained facts (e.g. from a manual literature search), or ``None`` if
    no independent confirmation was attempted/possible. Expected keys
    when present: ``title``, ``doi``, ``arxiv_id``, ``exists`` (bool).
    """
    if confirmed is None:
        return VerificationResult(
            verification_status="unverified",
            evidence_tier="T3_unverified_claimed",
            disagreements=("no independent verification was attempted for this source",),
        )

    disagreements: list[str] = []

    if confirmed.get("exists") is False:
        disagreements.append(
            f"claimed identifier (doi={claimed_doi!r}, arxiv_id={claimed_arxiv_id!r}) "
            "could not be found in independent verification -- treated as unconfirmed, not assumed correct"
        )
        return VerificationResult(
            verification_status="disputed",
            evidence_tier="T4_disputed",
            disagreements=tuple(disagreements),
        )

    confirmed_title = confirmed.get("title")
    if confirmed_title and normalize_text(confirmed_title) != normalize_text(claimed_title):
        disagreements.append(
            f"claimed title {claimed_title!r} does not match independently confirmed title {confirmed_title!r}"
        )

    confirmed_doi = confirmed.get("doi")
    if claimed_doi and confirmed_doi and normalize_text(claimed_doi) != normalize_text(confirmed_doi):
        disagreements.append(
            f"claimed DOI {claimed_doi!r} does not match independently confirmed DOI {confirmed_doi!r}"
        )

    confirmed_arxiv = confirmed.get("arxiv_id")
    if claimed_arxiv_id and confirmed_arxiv and normalize_text(claimed_arxiv_id) != normalize_text(confirmed_arxiv):
        disagreements.append(
            f"claimed arXiv id {claimed_arxiv_id!r} does not match independently confirmed id {confirmed_arxiv!r}"
        )

    if disagreements:
        return VerificationResult(
            verification_status="disputed",
            evidence_tier="T4_disputed",
            disagreements=tuple(disagreements),
        )

    return VerificationResult(
        verification_status="verified",
        evidence_tier=confirmed.get("evidence_tier", "T1_verified_primary"),
        disagreements=(),
    )


assert VERIFICATION_STATUSES == {"verified", "unverified", "disputed"}
assert "T4_disputed" in EVIDENCE_TIERS
