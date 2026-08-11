"""MOABB dataset candidate importer -- metadata only, never downloads.

MOABB (Mother of All BCI Benchmarks, BSD-3-Clause,
https://github.com/NeuroTechX/moabb) exposes each dataset as a
`moabb.datasets.base.BaseDataset` subclass. Per MOABB's own design,
instantiating a dataset class does not download anything -- raw signal
retrieval only happens inside `.get_data()`, which this module never calls.
Per-dataset license/access terms are *not* exposed as object attributes by
MOABB's Python API (confirmed via `moabb/datasets/base.py` on GitHub this
session: the constructor accepts `subjects, sessions_per_subject, events,
code, interval, paradigm, doi, ...` -- no license/access field). This
importer therefore always marks `license`/`access_status` as unknown unless
a fixture explicitly supplies them, rather than guessing.

`moabb` is not installed in every environment this repository runs in (it is
not currently declared in requirements.txt). The installed-package path is
best-effort: if the import fails, callers get a clear
`MoabbImporterUnavailable` rather than a stack trace, and the fixture path
remains fully usable without it.
"""
from __future__ import annotations

import inspect
import itertools
import json
from pathlib import Path
from typing import Any, Optional, Union

from dataset_importers.candidate_record import (
    SUPPORTED_MODALITIES,
    DatasetCandidateRecordV1,
    infer_benchmark_role_recommendation,
    infer_transition_readiness,
)

SOURCE_CATALOG = "moabb"

# MOABB's own scope is EEG-based BCI paradigms (motor imagery, P300, SSVEP,
# ...) -- true of every dataset the catalog exposes, not a per-dataset guess.
_MOABB_DEFAULT_MODALITY = "EEG"


class MoabbImporterUnavailable(RuntimeError):
    """Raised when moabb is not installed and no fixture was supplied, or
    when installed-package introspection cannot proceed safely."""


def _is_moabb_installed() -> bool:
    try:
        import moabb  # noqa: F401
    except Exception:
        return False
    return True


def _record_from_moabb_meta(meta: dict[str, Any], *, best_effort: bool = False) -> DatasetCandidateRecordV1:
    source_dataset_id = str(meta.get("code") or meta.get("dataset_id") or "").strip()
    if not source_dataset_id:
        raise ValueError("moabb dataset metadata entry is missing a 'code'/'dataset_id'")

    display_name = str(meta.get("name") or source_dataset_id)
    modalities = list(meta.get("modalities") or [_MOABB_DEFAULT_MODALITY])

    condition_labels: list[str] = []
    event_id = meta.get("event_id")
    if isinstance(event_id, dict) and event_id:
        condition_labels = sorted(str(k) for k in event_id.keys())
    elif meta.get("condition_labels"):
        condition_labels = [str(c) for c in meta["condition_labels"]]

    task_labels: list[str] = []
    if meta.get("paradigm"):
        task_labels = [str(meta["paradigm"])]

    subject_count = meta.get("subject_count")
    if subject_count is not None:
        subject_count = int(subject_count)
    session_count = meta.get("n_sessions")
    if session_count is not None:
        session_count = int(session_count)

    license_value = str(meta.get("license") or "unknown")
    license_known = license_value.strip().lower() != "unknown"
    license_risk = str(meta.get("license_risk") or ("permissive_low" if license_known and meta.get("_license_permissive") else "unknown_high"))
    if not license_known:
        license_risk = "unknown_high"

    access_status = str(meta.get("access_status") or "unknown")

    available_metadata = sorted(
        k
        for k, v in {
            "subject_count": subject_count,
            "session_count": session_count,
            "paradigm": meta.get("paradigm"),
            "condition_labels": condition_labels or None,
            "license": license_value if license_known else None,
            "doi": meta.get("doi"),
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
            "Subject/session metadata is known but explicit condition/event labels were not "
            "found -- consult the dataset's own event/paradigm documentation before proceeding."
        ),
        "derived_feature_extraction_needed": (
            "Explicit condition labels exist but subject count is unknown -- derive it (and "
            "features) via adapters.mne_bids's metadata-scan path before export."
        ),
        "blocked_missing_metadata": "Too little metadata to judge transition-readiness -- manual review needed.",
        "blocked_license_or_access": "License or access is disqualifying for this repository's adapter-only policy.",
        "blocked_unsupported_modality": f"Modalities {modalities} are outside this repository's supported set.",
    }.get(transition_readiness, "Review dataset metadata manually before further scouting.")

    risks = [
        "MOABB's Python API does not expose per-dataset license/access terms as object "
        "attributes; this candidate's license/access were not independently verified beyond "
        "what was explicitly supplied."
    ]
    limitations = [
        "This candidate reflects catalog/class-level metadata only -- no raw signal file was "
        "opened, downloaded, or parsed to produce this record."
    ]
    if best_effort:
        limitations.append(
            "Produced via best-effort introspection of an installed moabb package; some fields "
            "may be unavailable if the dataset class could not be safely instantiated with "
            "default arguments."
        )

    provenance = meta.get("_provenance") or "MOABB dataset metadata (source unspecified)."

    return DatasetCandidateRecordV1.make(
        source_catalog=SOURCE_CATALOG,
        source_dataset_id=source_dataset_id,
        display_name=display_name,
        public_url=str(meta.get("url") or "https://moabb.neurotechx.com/docs/"),
        repository_url=str(meta.get("repository_url") or "https://github.com/NeuroTechX/moabb"),
        documentation_url=str(meta.get("docs_url") or "https://moabb.neurotechx.com/docs/"),
        license=license_value,
        license_risk=license_risk,
        access_status=access_status,
        download_required="true",
        raw_data_rehosted=bool(meta.get("raw_data_rehosted", False)),
        modalities=modalities,
        task_labels=task_labels,
        condition_labels=condition_labels,
        subject_count=subject_count,
        session_count=session_count,
        recording_count=None,
        available_metadata=available_metadata,
        potential_transition_classes=potential_transition_classes,
        transition_readiness=transition_readiness,
        compatible_adapters=compatible_adapters,
        recommended_next_action=recommended_next_action,
        benchmark_role_recommendation=benchmark_role_recommendation,
        risks=risks,
        limitations=limitations,
        provenance=provenance,
        metadata={"review_needed": not (license_known and access_status != "unknown"), "moabb_doi": meta.get("doi")},
    )


def import_moabb_candidates_from_fixture(fixture_path: Union[str, Path]) -> list[DatasetCandidateRecordV1]:
    path = Path(fixture_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("datasets") or data.get("entries") or []
    records = []
    for entry in entries:
        entry = dict(entry)
        entry.setdefault(
            "_provenance",
            f"Loaded from fixture file '{path}' (source_catalog=moabb); not independently "
            "verified against the live MOABB catalog this session.",
        )
        records.append(_record_from_moabb_meta(entry))
    return records


def import_moabb_candidates_from_installed_package(*, limit: Optional[int] = None) -> list[DatasetCandidateRecordV1]:
    """Best-effort introspection of an installed `moabb` package. Never
    calls `.get_data()`/`.download()`. Skips (does not fabricate metadata
    for) any dataset class that cannot be safely instantiated with its
    default constructor arguments."""
    if not _is_moabb_installed():
        raise MoabbImporterUnavailable("moabb is not installed in this environment")

    import moabb.datasets as moabb_datasets  # type: ignore
    from moabb.datasets.base import BaseDataset  # type: ignore

    records: list[DatasetCandidateRecordV1] = []
    classes = [
        obj
        for _, obj in inspect.getmembers(moabb_datasets, inspect.isclass)
        if issubclass(obj, BaseDataset) and obj is not BaseDataset
    ]
    for cls in classes:
        try:
            inst = cls()
        except Exception:
            # Cannot safely instantiate without dataset-specific constructor
            # args -- skip rather than guess at its metadata.
            continue
        meta: dict[str, Any] = {
            "code": getattr(inst, "code", cls.__name__),
            "paradigm": getattr(inst, "paradigm", None),
            "doi": getattr(inst, "doi", None),
            "_provenance": (
                f"Introspected from installed moabb package via `inspect.getmembers` this "
                f"session (class {cls.__module__}.{cls.__name__})."
            ),
        }
        subject_list = getattr(inst, "subject_list", None)
        if subject_list:
            meta["subject_count"] = len(subject_list)
        n_sessions = getattr(inst, "n_sessions", None)
        if n_sessions is not None:
            meta["n_sessions"] = n_sessions
        event_id = getattr(inst, "event_id", None)
        if isinstance(event_id, dict) and event_id:
            meta["event_id"] = event_id
        try:
            records.append(_record_from_moabb_meta(meta, best_effort=True))
        except ValueError:
            continue
        if limit and len(records) >= limit:
            break
    return records


def import_moabb_candidates(
    *, fixture_path: Optional[Union[str, Path]] = None, prefer_installed: bool = True, limit: Optional[int] = None
) -> list[DatasetCandidateRecordV1]:
    """Orchestrator: fixture takes precedence when supplied; otherwise falls
    back to the installed package (best-effort). Raises
    `MoabbImporterUnavailable` with a clear reason if neither is usable."""
    if fixture_path is not None:
        return import_moabb_candidates_from_fixture(fixture_path)
    if prefer_installed and _is_moabb_installed():
        return import_moabb_candidates_from_installed_package(limit=limit)
    raise MoabbImporterUnavailable("moabb is not installed and no fixture_path was supplied")
