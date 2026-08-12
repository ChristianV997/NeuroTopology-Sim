"""FmriFeatureRecipeSpecV1 / FmriDerivedFeatureRecipeManifestV1 -- the
schema for `adapters.fmri_derivatives_feature_recipe`'s bounded, explicit
derived-feature extraction recipe.

A `FmriFeatureRecipeSpecV1` is not a download, not raw BOLD preprocessing,
not fMRIPrep execution, and not evidence -- it is a bounded, explicit
request ("extract these conservative connectivity/graph/QC features from
up to N subjects of this already-local fMRIPrep/Nilearn-style derivative
table or fixture, using this explicit state mapping"). The recipe's own
output (`derived_features.csv`/`mapping.json`) only becomes evidence once
passed through the already-governed `adapters.fmri_derivatives` chain --
see docs/fmri_derivatives_feature_recipe.md.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from adapters.fmri_derivatives_feature_recipe_validation import validate_manifest, validate_recipe_spec

_SCHEMA_VERSION = "1"


def compute_recipe_id(
    *,
    dataset_id: str,
    feature_set_id: str,
    source_state: str,
    target_state: str,
    requested_features: list[str],
    atlas_or_parcellation: str,
    max_subjects: Optional[int],
    max_runs: Optional[int],
    max_timepoints_per_state: Optional[int],
    max_total_timepoints: Optional[int],
) -> str:
    """Stable sha256[:16] over the recipe's identity fields only --
    mirrors `adapters.mne_bids_feature_recipe.compute_recipe_id`, but also
    includes `atlas_or_parcellation` in the identity basis: two fMRI
    recipes that differ only in atlas/parcellation are extracting a
    different scientific quantity, not re-specifying the same request.
    Excludes `created_at`, `recipe_name`, `limitations`, `provenance`, and
    every other mutable/free-text field."""
    basis = {
        "dataset_id": dataset_id,
        "feature_set_id": feature_set_id,
        "source_state": source_state,
        "target_state": target_state,
        "requested_features": sorted(requested_features),
        "atlas_or_parcellation": atlas_or_parcellation,
        "max_subjects": max_subjects,
        "max_runs": max_runs,
        "max_timepoints_per_state": max_timepoints_per_state,
        "max_total_timepoints": max_total_timepoints,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class FmriFeatureRecipeSpecV1:
    schema_version: str = _SCHEMA_VERSION
    recipe_id: str = ""
    recipe_name: str = ""
    input_kind: str = "timeseries_table"
    derivatives_root: str = ""
    dataset_id: str = ""
    subject_filter: list[str] = field(default_factory=list)
    session_filter: list[str] = field(default_factory=list)
    task_filter: list[str] = field(default_factory=list)
    run_filter: list[str] = field(default_factory=list)
    state_mapping: dict[str, str] = field(default_factory=dict)
    source_state: str = ""
    target_state: str = ""
    modality: str = "fMRI"
    atlas_or_parcellation: str = ""
    confound_policy: dict[str, Any] = field(default_factory=dict)
    feature_set_id: str = ""
    feature_definitions: dict[str, str] = field(default_factory=dict)
    requested_features: list[str] = field(default_factory=list)
    connectivity_policy: dict[str, Any] = field(default_factory=lambda: {"method": "pearson_correlation"})
    graph_policy: dict[str, Any] = field(default_factory=dict)
    qc_policy: dict[str, Any] = field(default_factory=lambda: {"confounds_source": "none"})
    max_subjects: Optional[int] = None
    max_runs: Optional[int] = None
    max_timepoints_per_state: Optional[int] = None
    max_total_timepoints: Optional[int] = None
    output_format: str = "long"
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        dataset_id: str,
        feature_set_id: str,
        source_state: str,
        target_state: str,
        atlas_or_parcellation: str = "",
        requested_features: Optional[list[str]] = None,
        max_subjects: Optional[int] = None,
        max_runs: Optional[int] = None,
        max_timepoints_per_state: Optional[int] = None,
        max_total_timepoints: Optional[int] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "FmriFeatureRecipeSpecV1":
        requested_features = list(requested_features or [])
        recipe_id = compute_recipe_id(
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            source_state=source_state,
            target_state=target_state,
            requested_features=requested_features,
            atlas_or_parcellation=atlas_or_parcellation,
            max_subjects=max_subjects,
            max_runs=max_runs,
            max_timepoints_per_state=max_timepoints_per_state,
            max_total_timepoints=max_total_timepoints,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            recipe_id=recipe_id,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            source_state=source_state,
            target_state=target_state,
            atlas_or_parcellation=atlas_or_parcellation,
            requested_features=requested_features,
            max_subjects=max_subjects,
            max_runs=max_runs,
            max_timepoints_per_state=max_timepoints_per_state,
            max_total_timepoints=max_total_timepoints,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_recipe_id(
            dataset_id=self.dataset_id,
            feature_set_id=self.feature_set_id,
            source_state=self.source_state,
            target_state=self.target_state,
            requested_features=self.requested_features,
            atlas_or_parcellation=self.atlas_or_parcellation,
            max_subjects=self.max_subjects,
            max_runs=self.max_runs,
            max_timepoints_per_state=self.max_timepoints_per_state,
            max_total_timepoints=self.max_total_timepoints,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe_name,
            "input_kind": self.input_kind,
            "derivatives_root": self.derivatives_root,
            "dataset_id": self.dataset_id,
            "subject_filter": list(self.subject_filter),
            "session_filter": list(self.session_filter),
            "task_filter": list(self.task_filter),
            "run_filter": list(self.run_filter),
            "state_mapping": dict(self.state_mapping or {}),
            "source_state": self.source_state,
            "target_state": self.target_state,
            "modality": self.modality,
            "atlas_or_parcellation": self.atlas_or_parcellation,
            "confound_policy": dict(self.confound_policy or {}),
            "feature_set_id": self.feature_set_id,
            "feature_definitions": dict(self.feature_definitions or {}),
            "requested_features": list(self.requested_features),
            "connectivity_policy": dict(self.connectivity_policy or {}),
            "graph_policy": dict(self.graph_policy or {}),
            "qc_policy": dict(self.qc_policy or {}),
            "max_subjects": self.max_subjects,
            "max_runs": self.max_runs,
            "max_timepoints_per_state": self.max_timepoints_per_state,
            "max_total_timepoints": self.max_total_timepoints,
            "output_format": self.output_format,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FmriFeatureRecipeSpecV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            recipe_id=d.get("recipe_id", ""),
            recipe_name=d.get("recipe_name", ""),
            input_kind=d.get("input_kind", "timeseries_table"),
            derivatives_root=d.get("derivatives_root", ""),
            dataset_id=d.get("dataset_id", ""),
            subject_filter=list(d.get("subject_filter") or []),
            session_filter=list(d.get("session_filter") or []),
            task_filter=list(d.get("task_filter") or []),
            run_filter=list(d.get("run_filter") or []),
            state_mapping=dict(d.get("state_mapping") or {}),
            source_state=d.get("source_state", ""),
            target_state=d.get("target_state", ""),
            modality=d.get("modality", "fMRI"),
            atlas_or_parcellation=d.get("atlas_or_parcellation", ""),
            confound_policy=dict(d.get("confound_policy") or {}),
            feature_set_id=d.get("feature_set_id", ""),
            feature_definitions=dict(d.get("feature_definitions") or {}),
            requested_features=list(d.get("requested_features") or []),
            connectivity_policy=dict(d.get("connectivity_policy") or {"method": "pearson_correlation"}),
            graph_policy=dict(d.get("graph_policy") or {}),
            qc_policy=dict(d.get("qc_policy") or {"confounds_source": "none"}),
            max_subjects=d.get("max_subjects"),
            max_runs=d.get("max_runs"),
            max_timepoints_per_state=d.get("max_timepoints_per_state"),
            max_total_timepoints=d.get("max_total_timepoints"),
            output_format=d.get("output_format", "long"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "FmriFeatureRecipeSpecV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_recipe_spec(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from adapters.fmri_derivatives_feature_recipe_validation import FmriFeatureRecipeValidationError

            raise FmriFeatureRecipeValidationError("; ".join(errors))


def compute_manifest_id(*, recipe_id: str, features_written: int, created_at: str) -> str:
    basis = {"recipe_id": recipe_id, "features_written": features_written, "created_at": created_at}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class FmriDerivedFeatureRecipeManifestV1:
    schema_version: str = _SCHEMA_VERSION
    manifest_id: str = ""
    recipe_id: str = ""
    dataset_id: str = ""
    input_root: str = ""
    output_features_path: str = ""
    output_mapping_path: str = ""
    output_summary_path: str = ""
    subjects_seen: list[str] = field(default_factory=list)
    subjects_used: list[str] = field(default_factory=list)
    sessions_used: list[str] = field(default_factory=list)
    runs_used: list[str] = field(default_factory=list)
    states_observed: list[str] = field(default_factory=list)
    transitions_exportable: int = 0
    features_written: int = 0
    skipped_inputs: list[dict[str, Any]] = field(default_factory=list)
    skipped_subjects: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    qc_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    repo_commit: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, recipe_id: str, dataset_id: str, features_written: int = 0, _now: Optional[datetime] = None, **kwargs: Any
    ) -> "FmriDerivedFeatureRecipeManifestV1":
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        manifest_id = compute_manifest_id(recipe_id=recipe_id, features_written=features_written, created_at=ts)
        return cls(
            manifest_id=manifest_id,
            recipe_id=recipe_id,
            dataset_id=dataset_id,
            features_written=features_written,
            created_at=ts,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "recipe_id": self.recipe_id,
            "dataset_id": self.dataset_id,
            "input_root": self.input_root,
            "output_features_path": self.output_features_path,
            "output_mapping_path": self.output_mapping_path,
            "output_summary_path": self.output_summary_path,
            "subjects_seen": list(self.subjects_seen),
            "subjects_used": list(self.subjects_used),
            "sessions_used": list(self.sessions_used),
            "runs_used": list(self.runs_used),
            "states_observed": list(self.states_observed),
            "transitions_exportable": self.transitions_exportable,
            "features_written": self.features_written,
            "skipped_inputs": list(self.skipped_inputs),
            "skipped_subjects": list(self.skipped_subjects),
            "errors": list(self.errors),
            "qc_summary": dict(self.qc_summary or {}),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FmriDerivedFeatureRecipeManifestV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            manifest_id=d.get("manifest_id", ""),
            recipe_id=d.get("recipe_id", ""),
            dataset_id=d.get("dataset_id", ""),
            input_root=d.get("input_root", ""),
            output_features_path=d.get("output_features_path", ""),
            output_mapping_path=d.get("output_mapping_path", ""),
            output_summary_path=d.get("output_summary_path", ""),
            subjects_seen=list(d.get("subjects_seen") or []),
            subjects_used=list(d.get("subjects_used") or []),
            sessions_used=list(d.get("sessions_used") or []),
            runs_used=list(d.get("runs_used") or []),
            states_observed=list(d.get("states_observed") or []),
            transitions_exportable=int(d.get("transitions_exportable") or 0),
            features_written=int(d.get("features_written") or 0),
            skipped_inputs=list(d.get("skipped_inputs") or []),
            skipped_subjects=list(d.get("skipped_subjects") or []),
            errors=list(d.get("errors") or []),
            qc_summary=dict(d.get("qc_summary") or {}),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "FmriDerivedFeatureRecipeManifestV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_manifest(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from adapters.fmri_derivatives_feature_recipe_validation import FmriFeatureRecipeValidationError

            raise FmriFeatureRecipeValidationError("; ".join(errors))
