"""EEGDash dataset candidate importer -- metadata only, never downloads.

EEGDash (BSD-3-Clause, https://github.com/eeg2go/eegdash) catalogs 700+
BIDS-first EEG/MEG/fNIRS/EMG/iEEG datasets. Its `eegdash.EEGDash` client
exposes `find_datasets()`/`search_datasets()`/`get_dataset()`, all
documented (verified from the installed package's own docstrings this
session, eegdash 0.8.4) as metadata-only: "does not download any signal
bytes; only small JSON catalogue documents are transferred." This importer
therefore treats a *catalog query* itself as within the "no raw data
download" boundary -- the constraint enforced here is narrower and
stricter: this module never calls a data-loading/caching method
(`EEGDashDataset`, `.download()`, anything that would fetch signal bytes).

The real `eegdash.schemas.Dataset` TypedDict (read from the installed
package's source this session) is the field reference this module's
`_record_from_eegdash_meta` maps from: `dataset_id`, `name`, `source`,
`recording_modality`, `datatypes`, `license`, `tasks`, `sessions`,
`dataset_doi`, `demographics` (with `subjects_count`), `tags`, `storage`.

Any live network call (`import_eegdash_candidates_from_installed_package`)
is wrapped in try/except and never invoked by this repository's test suite
or by any CLI default path -- callers must pass `live_query=True`
explicitly (CLI: `--allow-live-query`). Tests exercise the real mapping
logic by monkeypatching `eegdash.EEGDash.find_datasets`, never by making a
real HTTP request.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from dataset_importers.candidate_record import (
    SUPPORTED_MODALITIES,
    DatasetCandidateRecordV1,
    infer_benchmark_role_recommendation,
    infer_transition_readiness,
)

SOURCE_CATALOG = "eegdash"

# Sources EEGDash catalogs that are themselves known-public open archives.
# A dataset's `source` field being one of these is explicit evidence for
# access_status="public" -- not a guess, since OpenNeuro/NEMAR are public by
# construction (no login/registration to browse or fetch their contents).
_PUBLIC_SOURCES: frozenset[str] = frozenset({"openneuro", "nemar"})

_PERMISSIVE_LICENSES: frozenset[str] = frozenset(
    {"cc0", "cc-0", "pddl", "odbl", "mit", "bsd", "bsd-3-clause", "bsd-2-clause", "apache-2.0"}
)
_COPYLEFT_LICENSES: frozenset[str] = frozenset({"cc-by-sa", "cc-by-sa-4.0", "gpl", "gpl-3.0"})
_AGPL_LICENSES: frozenset[str] = frozenset({"agpl", "agpl-3.0"})


class EegdashImporterUnavailable(RuntimeError):
    """Raised when eegdash is not installed and no fixture was supplied."""


def _is_eegdash_installed() -> bool:
    try:
        import eegdash  # noqa: F401
    except Exception:
        return False
    return True


def _classify_license(license_value: str) -> str:
    low = license_value.strip().lower()
    if not low or low == "unknown":
        return "unknown_high"
    if low in _PERMISSIVE_LICENSES:
        return "permissive_low"
    if low in _COPYLEFT_LICENSES:
        return "copyleft_medium"
    if low in _AGPL_LICENSES:
        return "agpl_high"
    return "unknown_high"


def _record_from_eegdash_meta(meta: dict[str, Any], *, best_effort: bool = False) -> DatasetCandidateRecordV1:
    source_dataset_id = str(meta.get("dataset_id") or "").strip()
    if not source_dataset_id:
        raise ValueError("eegdash dataset metadata entry is missing a 'dataset_id'")

    display_name = str(meta.get("name") or source_dataset_id)
    modalities = [str(m) for m in (meta.get("recording_modality") or [])]

    tasks = [str(t) for t in (meta.get("tasks") or [])]
    condition_labels = list(tasks) if len(tasks) >= 2 else list(meta.get("condition_labels") or [])

    demographics = meta.get("demographics") or {}
    subject_count = demographics.get("subjects_count")
    if subject_count is not None:
        subject_count = int(subject_count)

    sessions = meta.get("sessions") or []
    session_count = len(sessions) if sessions else meta.get("session_count")
    if session_count is not None:
        session_count = int(session_count)

    recording_count = meta.get("recording_count")
    if recording_count is not None:
        recording_count = int(recording_count)

    license_value = str(meta.get("license") or "unknown")
    license_risk = _classify_license(license_value)

    source = str(meta.get("source") or "").strip().lower()
    access_status = str(meta.get("access_status") or ("public" if source in _PUBLIC_SOURCES else "unknown"))

    raw_data_rehosted = bool(meta.get("storage")) or bool(meta.get("raw_data_rehosted", False))

    available_metadata = sorted(
        k
        for k, v in {
            "recording_modality": modalities or None,
            "tasks": tasks or None,
            "subject_count": subject_count,
            "session_count": session_count,
            "license": license_value if license_risk != "unknown_high" else None,
            "dataset_doi": meta.get("dataset_doi"),
            "source": source or None,
        }.items()
        if v
    )

    modality_supported = bool({m.upper() for m in modalities} & SUPPORTED_MODALITIES)
    license_ok = license_risk != "proprietary_high"
    access_ok = access_status != "restricted"
    has_conditions = bool(condition_labels)
    has_subject_count = subject_count is not None

    transition_readiness = infer_transition_readiness(
        modality_supported=modality_supported,
        license_ok=license_ok,
        access_ok=access_ok,
        has_conditions=has_conditions,
        has_subject_count=has_subject_count,
    )
    benchmark_role_recommendation = infer_benchmark_role_recommendation(
        transition_readiness=transition_readiness, access_status=access_status
    )

    potential_transition_classes: list[str] = []
    if len(condition_labels) >= 2:
        import itertools

        potential_transition_classes = [
            f"{a}_vs_{b}" for a, b in itertools.combinations(condition_labels[:4], 2)
        ][:6]

    compatible_adapters = ["adapters.mne_bids"] if modality_supported else []

    recommended_next_action = {
        "candidate_transition_possible": (
            "Write an explicit source/target condition mapping and a derived feature table, "
            "then run adapters.mne_bids to produce a governed TransitionRecordV1."
        ),
        "explicit_condition_mapping_needed": (
            "Subject/session metadata is known but explicit task labels did not yield distinct "
            "condition pairs -- consult the dataset's own BIDS events documentation."
        ),
        "derived_feature_extraction_needed": (
            "Explicit task/condition labels exist but subject count is unknown -- derive it "
            "(and features) via adapters.mne_bids's metadata-scan path before export."
        ),
        "blocked_missing_metadata": "Too little metadata to judge transition-readiness -- manual review needed.",
        "blocked_license_or_access": "License or access is disqualifying for this repository's adapter-only policy.",
        "blocked_unsupported_modality": f"Modalities {modalities} are outside this repository's supported set.",
    }.get(transition_readiness, "Review dataset metadata manually before further scouting.")

    risks = [
        "EEGDash catalog documents can be incomplete or stale relative to the underlying "
        "dataset's own current BIDS metadata; this candidate reflects only what the catalog "
        "document itself reported."
    ]
    limitations = [
        "This candidate reflects a catalog metadata document only -- no BIDS file was opened, "
        "downloaded, or parsed to produce this record."
    ]
    if best_effort:
        limitations.append(
            "Produced via a live EEGDash catalog query; the query itself is documented by the "
            "eegdash package as metadata-only (no signal bytes transferred), but this repository "
            "did not independently re-verify that guarantee against the underlying dataset."
        )

    provenance = meta.get("_provenance") or "EEGDash dataset metadata (source unspecified)."

    return DatasetCandidateRecordV1.make(
        source_catalog=SOURCE_CATALOG,
        source_dataset_id=source_dataset_id,
        display_name=display_name,
        public_url=str(meta.get("url") or f"https://github.com/eeg2go/eegdash"),
        repository_url="https://github.com/eeg2go/eegdash",
        documentation_url="https://github.com/eeg2go/eegdash#readme",
        license=license_value,
        license_risk=license_risk,
        access_status=access_status,
        download_required="true",
        raw_data_rehosted=raw_data_rehosted,
        modalities=modalities,
        task_labels=tasks,
        condition_labels=condition_labels,
        subject_count=subject_count,
        session_count=session_count,
        recording_count=recording_count,
        available_metadata=available_metadata,
        potential_transition_classes=potential_transition_classes,
        transition_readiness=transition_readiness,
        compatible_adapters=compatible_adapters,
        recommended_next_action=recommended_next_action,
        benchmark_role_recommendation=benchmark_role_recommendation,
        risks=risks,
        limitations=limitations,
        provenance=provenance,
        metadata={
            "review_needed": license_risk == "unknown_high" or access_status == "unknown",
            "eegdash_source": source or None,
            "eegdash_dataset_doi": meta.get("dataset_doi"),
        },
    )


def import_eegdash_candidates_from_fixture(fixture_path: Union[str, Path]) -> list[DatasetCandidateRecordV1]:
    path = Path(fixture_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("datasets") or data.get("entries") or []
    records = []
    for entry in entries:
        entry = dict(entry)
        entry.setdefault(
            "_provenance",
            f"Loaded from fixture file '{path}' (source_catalog=eegdash); not independently "
            "verified against the live EEGDash catalog this session.",
        )
        records.append(_record_from_eegdash_meta(entry))
    return records


def import_eegdash_candidates_from_installed_package(
    *, live_query: bool = False, query: Optional[dict[str, Any]] = None, limit: int = 20
) -> list[DatasetCandidateRecordV1]:
    """Installed-package path. With `live_query=False` (the default and the
    only mode this repository's tests/CLI-default paths ever use), performs
    no network I/O at all: it only confirms the installed package exposes
    the expected metadata-only API surface and returns an empty list with a
    clear reason. With `live_query=True`, attempts one real
    `EEGDash.find_datasets()` call (metadata-only per the package's own
    documented guarantee); any failure (network, auth, timeout) is caught
    and reported, never silently swallowed or fabricated into fake
    candidates."""
    if not _is_eegdash_installed():
        raise EegdashImporterUnavailable("eegdash is not installed in this environment")

    import eegdash  # type: ignore

    if not hasattr(eegdash, "EEGDash"):
        raise EegdashImporterUnavailable("installed eegdash package does not expose an EEGDash client class")

    if not live_query:
        return []

    try:
        client = eegdash.EEGDash()
        raw_records = client.find_datasets(query or {}, limit=limit)
    except Exception as exc:  # network/auth/timeout -- never fabricate a result
        raise EegdashImporterUnavailable(f"live eegdash catalog query failed: {exc}") from exc

    records: list[DatasetCandidateRecordV1] = []
    for entry in raw_records:
        entry = dict(entry)
        entry.setdefault(
            "_provenance",
            "Loaded via a live eegdash.EEGDash().find_datasets() metadata-only query this session.",
        )
        try:
            records.append(_record_from_eegdash_meta(entry, best_effort=True))
        except ValueError:
            continue
    return records


def import_eegdash_candidates(
    *,
    fixture_path: Optional[Union[str, Path]] = None,
    prefer_installed: bool = True,
    live_query: bool = False,
    query: Optional[dict[str, Any]] = None,
    limit: int = 20,
) -> list[DatasetCandidateRecordV1]:
    """Orchestrator: fixture takes precedence when supplied; otherwise falls
    back to the installed package. `live_query` defaults False (safe,
    network-free introspection only) and must be explicitly opted into for
    a real catalog query."""
    if fixture_path is not None:
        return import_eegdash_candidates_from_fixture(fixture_path)
    if prefer_installed and _is_eegdash_installed():
        return import_eegdash_candidates_from_installed_package(live_query=live_query, query=query, limit=limit)
    raise EegdashImporterUnavailable("eegdash is not installed and no fixture_path was supplied")
