"""DatasetCandidateRecordV1 -- a scouting record for a public neurophysiology
dataset that *might* become a future governed transition/evidence/report
integration.

This is deliberately not `benchmarks.dataset_registry.DatasetRecordV1`: a
candidate is pre-registry. It carries no `allowed_uses` capable of
`transition_export`/`phase_space_export` under any circumstance (see
`dataset_importers.validation`) -- only `benchmarks.export_candidates`'s
benchmark-conversion path (Phase E) can turn a high-quality candidate into a
real, conservative `DatasetRecordV1`/`ArtifactRecordV1`, and even then it
lands in `current_role="exploration"` with the same floor the MNE/BIDS and
fMRIPrep/Nilearn adapters use for their own metadata-scan-only records. See
docs/dataset_candidate_importers.md.

`infer_transition_readiness`/`infer_benchmark_role_recommendation` live here
(not duplicated in each importer module) because both
`dataset_importers.moabb_importer` and `dataset_importers.eegdash_importer`
must derive readiness/role from the same explicit-metadata ladder --
divergent per-importer heuristics would make two datasets with identical
known metadata rank differently for no principled reason.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_importers.validation import validate_candidate_record

_SCHEMA_VERSION = "1"

# Modalities this repository can currently do anything with (via
# `adapters.mne_bids` for electrophysiology, `adapters.fmri_derivatives` for
# fMRI). Case-insensitive match against a candidate's `modalities`. Neither
# MOABB nor EEGDash catalogs fMRI datasets today, but the set stays generic
# rather than importer-specific so a future catalog source does not need a
# parallel list.
SUPPORTED_MODALITIES: frozenset[str] = frozenset({"EEG", "MEG", "IEEG", "FNIRS", "EMG", "FMRI"})

# Fixed floor every candidate record carries regardless of quality --
# candidate status never authorizes transition/phase-space export or any
# terminal claim. See dataset_importers.validation.REQUIRED_FORBIDDEN_USES
# for the structurally-enforced version of this same floor.
_BASE_FORBIDDEN_USES: tuple[str, ...] = (
    "transition_export",
    "phase_space_export",
    "final_claim_confirmation",
    "clinical_claim",
    "mechanistic_causal_claim",
    "prospective_prediction_claim",
)
_BASE_ALLOWED_USES: tuple[str, ...] = ("documentation", "feature_design")


def compute_candidate_id(*, source_catalog: str, source_dataset_id: str) -> str:
    """Stable sha256[:16] over (source_catalog, source_dataset_id) only --
    mirrors `external_tools.adapter_contract.compute_adapter_id`: excludes
    every mutable/free-text field, so re-importing the same catalog entry
    always yields the same candidate_id regardless of when scoring/notes
    were last refreshed."""
    basis = {"source_catalog": source_catalog, "source_dataset_id": source_dataset_id}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def infer_transition_readiness(
    *,
    modality_supported: bool,
    license_ok: bool,
    access_ok: bool,
    has_conditions: bool,
    has_subject_count: bool,
) -> str:
    """Deterministic readiness ladder shared by every importer.

    `license_ok`/`access_ok` mean "not explicitly disqualifying" (proprietary
    license / restricted access), not "confirmed permissive" -- an unknown
    license/access still proceeds through the ladder on its metadata merits;
    `infer_benchmark_role_recommendation` is what keeps unknown/restricted
    access out of `development_candidate` (mission validation rule 6).
    """
    if not modality_supported:
        return "blocked_unsupported_modality"
    if not (license_ok and access_ok):
        return "blocked_license_or_access"
    if not has_conditions and not has_subject_count:
        return "blocked_missing_metadata"
    if has_conditions and has_subject_count:
        return "candidate_transition_possible"
    if has_conditions and not has_subject_count:
        return "derived_feature_extraction_needed"
    return "explicit_condition_mapping_needed"


def infer_benchmark_role_recommendation(*, transition_readiness: str, access_status: str) -> str:
    """Deterministic role recommendation from readiness + access_status.
    Enforces validation rule 6 (restricted/unknown access can never be
    `development_candidate`) at the point of construction, not only at
    validation time."""
    if transition_readiness.startswith("blocked_"):
        return "blocked"
    if transition_readiness == "candidate_transition_possible":
        base = "development_candidate"
    elif transition_readiness in ("explicit_condition_mapping_needed", "derived_feature_extraction_needed"):
        base = "exploration_candidate"
    else:
        base = "documentation_only"
    if base == "development_candidate" and access_status in ("restricted", "unknown"):
        return "review_needed"
    return base


@dataclass
class DatasetCandidateRecordV1:
    schema_version: str = _SCHEMA_VERSION
    candidate_id: str = ""
    source_catalog: str = ""
    source_dataset_id: str = ""
    display_name: str = ""
    public_url: str = ""
    repository_url: str = ""
    documentation_url: str = ""
    license: str = "unknown"
    license_risk: str = "unknown_high"
    access_status: str = "unknown"
    download_required: str = "unknown"
    raw_data_rehosted: bool = False
    modalities: list[str] = field(default_factory=list)
    task_labels: list[str] = field(default_factory=list)
    condition_labels: list[str] = field(default_factory=list)
    subject_count: Optional[int] = None
    session_count: Optional[int] = None
    recording_count: Optional[int] = None
    available_metadata: list[str] = field(default_factory=list)
    potential_transition_classes: list[str] = field(default_factory=list)
    transition_readiness: str = "metadata_only"
    compatible_adapters: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    benchmark_role_recommendation: str = "review_needed"
    allowed_uses: list[str] = field(default_factory=lambda: list(_BASE_ALLOWED_USES))
    forbidden_uses: list[str] = field(default_factory=lambda: list(_BASE_FORBIDDEN_USES))
    risks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, source_catalog: str, source_dataset_id: str, _now: Optional[datetime] = None, **kwargs: Any
    ) -> "DatasetCandidateRecordV1":
        candidate_id = compute_candidate_id(source_catalog=source_catalog, source_dataset_id=source_dataset_id)
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            candidate_id=candidate_id,
            source_catalog=source_catalog,
            source_dataset_id=source_dataset_id,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_candidate_id(source_catalog=self.source_catalog, source_dataset_id=self.source_dataset_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "source_catalog": self.source_catalog,
            "source_dataset_id": self.source_dataset_id,
            "display_name": self.display_name,
            "public_url": self.public_url,
            "repository_url": self.repository_url,
            "documentation_url": self.documentation_url,
            "license": self.license,
            "license_risk": self.license_risk,
            "access_status": self.access_status,
            "download_required": self.download_required,
            "raw_data_rehosted": bool(self.raw_data_rehosted),
            "modalities": list(self.modalities),
            "task_labels": list(self.task_labels),
            "condition_labels": list(self.condition_labels),
            "subject_count": self.subject_count,
            "session_count": self.session_count,
            "recording_count": self.recording_count,
            "available_metadata": list(self.available_metadata),
            "potential_transition_classes": list(self.potential_transition_classes),
            "transition_readiness": self.transition_readiness,
            "compatible_adapters": list(self.compatible_adapters),
            "recommended_next_action": self.recommended_next_action,
            "benchmark_role_recommendation": self.benchmark_role_recommendation,
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetCandidateRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            candidate_id=d.get("candidate_id", ""),
            source_catalog=d.get("source_catalog", ""),
            source_dataset_id=d.get("source_dataset_id", ""),
            display_name=d.get("display_name", ""),
            public_url=d.get("public_url", ""),
            repository_url=d.get("repository_url", ""),
            documentation_url=d.get("documentation_url", ""),
            license=d.get("license", "unknown"),
            license_risk=d.get("license_risk", "unknown_high"),
            access_status=d.get("access_status", "unknown"),
            download_required=d.get("download_required", "unknown"),
            raw_data_rehosted=bool(d.get("raw_data_rehosted", False)),
            modalities=list(d.get("modalities") or []),
            task_labels=list(d.get("task_labels") or []),
            condition_labels=list(d.get("condition_labels") or []),
            subject_count=d.get("subject_count"),
            session_count=d.get("session_count"),
            recording_count=d.get("recording_count"),
            available_metadata=list(d.get("available_metadata") or []),
            potential_transition_classes=list(d.get("potential_transition_classes") or []),
            transition_readiness=d.get("transition_readiness", "metadata_only"),
            compatible_adapters=list(d.get("compatible_adapters") or []),
            recommended_next_action=d.get("recommended_next_action", ""),
            benchmark_role_recommendation=d.get("benchmark_role_recommendation", "review_needed"),
            allowed_uses=list(d.get("allowed_uses") or list(_BASE_ALLOWED_USES)),
            forbidden_uses=list(d.get("forbidden_uses") or list(_BASE_FORBIDDEN_USES)),
            risks=list(d.get("risks") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetCandidateRecordV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_candidate_record(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from dataset_importers.validation import DatasetImporterValidationError

            raise DatasetImporterValidationError("; ".join(errors))
