"""Candidate-only discovery of public EEG datasets through EEGDash.

This module deliberately has no downloader, BIDS runner, or subprocess usage.
Every returned record is a candidate that needs a separate human verification
step before it can enter a pipeline run.
"""
from __future__ import annotations

from typing import Any


_QUERY_HINTS = {
    "anesthesia": ("anesthesia", "sedation", "propofol", "anaesthesia"),
    "consciousness": ("consciousness", "coma", "sleep", "wakefulness"),
    "meditation": ("meditation", "mindfulness"),
    "traveling_wave": ("traveling wave", "travelling wave", "wave dynamics", "oscillation"),
}


def _intent_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = [term for values in _QUERY_HINTS.values() for term in values if term in lowered]
    return terms or [token for token in lowered.split() if len(token) > 2]


def _as_records(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict(orient="records"))
    return list(frame or [])


def search_dataset_candidates(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Return EEGDash catalogue candidates, never executable dataset jobs."""
    if not query or not query.strip():
        return []
    if not 1 <= int(max_results) <= 25:
        raise ValueError("max_results must be between 1 and 25")

    try:
        from eegdash import EEGDash
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("EEGDash is not installed in this Awareness Studio environment") from exc

    client = EEGDash()
    # EEGDash dataset search is structured, not a semantic search endpoint.
    # Fetch a small EEG catalogue slice, then rank catalogue metadata locally.
    records = _as_records(client.search_datasets(modality="eeg", limit=100))
    terms = _intent_terms(query)

    def score(row: dict[str, Any]) -> int:
        haystack = " ".join(str(row.get(key, "")) for key in ("name", "task", "clinical_group", "source"))
        haystack = haystack.lower()
        return sum(term in haystack for term in terms)

    ranked = sorted(records, key=lambda row: (-score(row), str(row.get("dataset_id", ""))))
    candidates = []
    for row in ranked:
        if score(row) <= 0:
            continue
        accession = str(row.get("dataset_id") or row.get("dataset") or "").strip()
        if not accession:
            continue
        source = str(row.get("source") or "eegdash")
        candidates.append({
            "accession": accession,
            "participant_count": row.get("n_subjects"),
            "modality": row.get("modality") or "eeg",
            "bids_compliance_flag": "candidate_to_verify",
            "candidate_to_verify": True,
            "execution_allowed": False,
            "verification_required": [
                "confirm accession and current OpenNeuro/NEMAR availability",
                "inspect BIDS validation and licensing",
                "obtain operator approval before any data download or pipeline execution",
            ],
            "source": source,
            "name": row.get("name", ""),
            "task": row.get("task", ""),
            "dataset_doi": row.get("dataset_doi", ""),
        })
        if len(candidates) >= int(max_results):
            break
    return candidates
