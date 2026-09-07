"""Deterministic, in-memory query packs over claims/sources.

Each pack is a fixed keyword set (not a live model call, not fuzzy) so
that results are exactly reproducible across runs -- required for the
"deterministic queries" test scenario. Matching is case-insensitive
substring matching against claim_text + tags + supporting_excerpt.
"""
from __future__ import annotations

from typing import Iterable

from .checksum import normalize_text
from .models import ExtractedClaim

QUERY_PACKS: dict[str, tuple[str, ...]] = {
    "triadic_connectivity": ("triadic", "triad", "high-order functional connectivity", "three-way interaction"),
    "higher_order_spectra": ("higher-order spectra", "trispectrum", "bispectrum", "higher order spectra"),
    "respiration_autonomic": (
        "respiration", "breathing", "slow breathing", "autonomic", "parasympathetic", "vagal", "inter-organ",
    ),
    "discernment": ("discernment", "wise evaluative judgment", "evaluative judgment"),
    "nonattachment": ("nonattachment", "non-attachment", "letting go", "renunciation"),
    "decentering": ("decentering", "de-centering", "metacognitive distancing"),
    "hypergraph_forecasting": ("hypergraph", "hyperedge", "higher-order network forecasting"),
    "null_model_methodology": ("null model", "surrogate", "permutation test", "randomization control"),
}


def available_query_packs() -> tuple[str, ...]:
    return tuple(sorted(QUERY_PACKS))


def _matches(claim: ExtractedClaim, keywords: tuple[str, ...]) -> bool:
    haystack = normalize_text(
        " ".join([claim.claim_text, claim.supporting_excerpt, " ".join(claim.tags)])
    )
    return any(normalize_text(keyword) in haystack for keyword in keywords)


def run_query_pack(claims: Iterable[ExtractedClaim], pack_name: str) -> list[ExtractedClaim]:
    if pack_name not in QUERY_PACKS:
        raise KeyError(f"unknown query pack: {pack_name!r}; available: {available_query_packs()}")
    keywords = QUERY_PACKS[pack_name]
    matched = [claim for claim in claims if _matches(claim, keywords)]
    return sorted(matched, key=lambda c: c.claim_id)
