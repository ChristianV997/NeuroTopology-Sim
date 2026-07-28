"""Candidate-only discovery of public EEG datasets through EEGDash.

This module deliberately has no downloader, BIDS runner, or subprocess usage.
Every returned record is a candidate that needs a separate human verification
step before it can enter a pipeline run.

Field names verified against installed eegdash==0.8.4 (2026-07-28) via
`inspect.signature(EEGDash.search_datasets)` and `eegdash.schemas`, NOT a live
HTTP response -- this sandbox's outbound proxy blocks `data.eegdash.org`
(403 at the proxy tunnel), so no live call could confirm the exact response
shape at runtime.

Confirmed real:
  - `EEGDash()` takes no required constructor args.
  - `search_datasets(*, modality=None, task=None, clinical_group=None,
    source=None, n_subjects_min=None, license=None, limit=100)` -- this
    module's call (`modality=..., limit=...`) matches the real keyword-only
    signature.
  - Two candidate response shapes exist in `eegdash.schemas`: the slim
    Mongo-persistence `DatasetModel` (`dataset_id, source, recording_modality,
    ingestion_fingerprint, senior_author, contact_info, timestamps, storage,
    bids_validator_status, n_validator_errors, top_issue_code` -- no `name`,
    `task`, `n_subjects`, or `clinical_group`), and the richer `Dataset`
    TypedDict (`dataset_id, name, source, recording_modality, tasks` (plural,
    list), `dataset_doi, demographics.subjects_count, tags.pathology,
    clinical.purpose, study_domain`, ...). `clinical_group` never exists as a
    field name in either shape -- it was a guess in the original version of
    this module.

This version reads fields defensively across both shapes (`recording_modality`
before `modality`, `tasks`/`task` for the BIDS task entity, nested
`demographics.subjects_count` before a top-level `n_subjects`, `study_domain`/
`clinical.purpose`/`tags.pathology` in place of the fictional `clinical_group`)
so a real response in either shape still scores correctly, without claiming a
live-verified field list this environment could not obtain.
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


def _text(row: dict[str, Any], key: str) -> str:
    """Read `key`, coercing a list (e.g. `tasks`, `recording_modality`) to a
    joined string and `None`/missing to ''."""
    value = row.get(key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def _subject_count(row: dict[str, Any]) -> Any:
    """`demographics.subjects_count` (the `Dataset` shape) before a top-level
    `n_subjects` (defensive; not a real field name in either confirmed schema,
    kept only in case a future/alternate response shape uses it)."""
    demographics = row.get("demographics") or {}
    if isinstance(demographics, dict) and demographics.get("subjects_count") is not None:
        return demographics["subjects_count"]
    return row.get("n_subjects")


def _clinical_group_text(row: dict[str, Any]) -> str:
    """No field literally named `clinical_group` exists in either confirmed
    eegdash response shape. `study_domain`, `clinical.purpose`, and
    `tags.pathology` are the real fields that carry the same kind of
    information a `clinical_group` filter term (e.g. "anesthesia",
    "consciousness") would match against."""
    clinical = row.get("clinical") or {}
    tags = row.get("tags") or {}
    parts = [
        str(row.get("study_domain") or ""),
        str(clinical.get("purpose") or "") if isinstance(clinical, dict) else "",
        _text(tags if isinstance(tags, dict) else {}, "pathology"),
    ]
    return " ".join(p for p in parts if p)


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
        # "task" here covers both the plural `tasks` (real `Dataset` field) and
        # a hypothetical singular `task`; "clinical_group" never exists as a
        # literal field in either confirmed shape, so it is derived, not read.
        haystack = " ".join([
            _text(row, "name"),
            _text(row, "tasks"),
            _text(row, "task"),
            _clinical_group_text(row),
            _text(row, "source"),
        ]).lower()
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
            "participant_count": _subject_count(row),
            "modality": row.get("recording_modality") or row.get("modality") or "eeg",
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
            "task": row.get("tasks") or row.get("task") or "",
            "dataset_doi": row.get("dataset_doi", ""),
        })
        if len(candidates) >= int(max_results):
            break
    return candidates
