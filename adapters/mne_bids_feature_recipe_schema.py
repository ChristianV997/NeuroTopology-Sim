"""FeatureRecipeSpecV1 / DerivedFeatureRecipeManifestV1 -- the schema for
`adapters.mne_bids_feature_recipe`'s bounded, explicit derived-feature
extraction recipe.

A `FeatureRecipeSpecV1` is not a download, not raw preprocessing, and not
evidence -- it is a bounded, explicit request ("extract these five
conservative features from up to N subjects/epochs of this already-local
BIDS-like root, using this explicit rest-vs-task mapping"). The recipe's
own output (`derived_features.csv`/`mapping.json`) only becomes evidence
once passed through the already-governed `adapters.mne_bids` chain -- see
docs/mne_bids_feature_recipe.md.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from adapters.mne_bids_feature_recipe_validation import validate_manifest, validate_recipe_spec

_SCHEMA_VERSION = "1"


def compute_recipe_id(
    *,
    dataset_id: str,
    feature_set_id: str,
    source_state: str,
    target_state: str,
    requested_features: list[str],
    max_subjects: Optional[int],
    max_runs: Optional[int],
    max_epochs_per_state: Optional[int],
    max_total_epochs: Optional[int],
) -> str:
    """Stable sha256[:16] over the recipe's identity fields only --
    mirrors `dataset_acquisition.acquisition_plan.compute_plan_id`:
    excludes `created_at`, `limitations`, `provenance`, and every other
    mutable/free-text field, so re-specifying the same request always
    yields the same recipe_id."""
    basis = {
        "dataset_id": dataset_id,
        "feature_set_id": feature_set_id,
        "source_state": source_state,
        "target_state": target_state,
        "requested_features": sorted(requested_features),
        "max_subjects": max_subjects,
        "max_runs": max_runs,
        "max_epochs_per_state": max_epochs_per_state,
        "max_total_epochs": max_total_epochs,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class FeatureRecipeSpecV1:
    schema_version: str = _SCHEMA_VERSION
    recipe_id: str = ""
    recipe_name: str = ""
    input_kind: str = "epoch_table"
    bids_root: str = ""
    dataset_id: str = ""
    subject_filter: list[str] = field(default_factory=list)
    session_filter: list[str] = field(default_factory=list)
    task_filter: list[str] = field(default_factory=list)
    run_filter: list[str] = field(default_factory=list)
    event_state_mapping: dict[str, str] = field(default_factory=dict)
    source_state: str = ""
    target_state: str = ""
    modality: str = "EEG"
    feature_set_id: str = ""
    feature_definitions: dict[str, str] = field(default_factory=dict)
    requested_features: list[str] = field(default_factory=list)
    epoch_window: dict[str, Any] = field(default_factory=lambda: {"length_seconds": 2.0, "overlap_seconds": 0.0})
    frequency_bands: dict[str, list[float]] = field(
        default_factory=lambda: {
            "delta": [1.0, 4.0], "theta": [4.0, 8.0], "alpha": [8.0, 13.0], "beta": [13.0, 30.0], "gamma": [30.0, 45.0],
        }
    )
    channel_policy: dict[str, Any] = field(default_factory=lambda: {"picks": ["all"]})
    reference_policy: str = "as_recorded"
    filter_policy: dict[str, Any] = field(default_factory=lambda: {"l_freq": None, "h_freq": None})
    artifact_policy: str = "none"
    max_subjects: Optional[int] = None
    max_runs: Optional[int] = None
    max_epochs_per_state: Optional[int] = None
    max_total_epochs: Optional[int] = None
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
        requested_features: Optional[list[str]] = None,
        max_subjects: Optional[int] = None,
        max_runs: Optional[int] = None,
        max_epochs_per_state: Optional[int] = None,
        max_total_epochs: Optional[int] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "FeatureRecipeSpecV1":
        requested_features = list(requested_features or [])
        recipe_id = compute_recipe_id(
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            source_state=source_state,
            target_state=target_state,
            requested_features=requested_features,
            max_subjects=max_subjects,
            max_runs=max_runs,
            max_epochs_per_state=max_epochs_per_state,
            max_total_epochs=max_total_epochs,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            recipe_id=recipe_id,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            source_state=source_state,
            target_state=target_state,
            requested_features=requested_features,
            max_subjects=max_subjects,
            max_runs=max_runs,
            max_epochs_per_state=max_epochs_per_state,
            max_total_epochs=max_total_epochs,
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
            max_subjects=self.max_subjects,
            max_runs=self.max_runs,
            max_epochs_per_state=self.max_epochs_per_state,
            max_total_epochs=self.max_total_epochs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe_name,
            "input_kind": self.input_kind,
            "bids_root": self.bids_root,
            "dataset_id": self.dataset_id,
            "subject_filter": list(self.subject_filter),
            "session_filter": list(self.session_filter),
            "task_filter": list(self.task_filter),
            "run_filter": list(self.run_filter),
            "event_state_mapping": dict(self.event_state_mapping or {}),
            "source_state": self.source_state,
            "target_state": self.target_state,
            "modality": self.modality,
            "feature_set_id": self.feature_set_id,
            "feature_definitions": dict(self.feature_definitions or {}),
            "requested_features": list(self.requested_features),
            "epoch_window": dict(self.epoch_window or {}),
            "frequency_bands": {k: list(v) for k, v in (self.frequency_bands or {}).items()},
            "channel_policy": dict(self.channel_policy or {}),
            "reference_policy": self.reference_policy,
            "filter_policy": dict(self.filter_policy or {}),
            "artifact_policy": self.artifact_policy,
            "max_subjects": self.max_subjects,
            "max_runs": self.max_runs,
            "max_epochs_per_state": self.max_epochs_per_state,
            "max_total_epochs": self.max_total_epochs,
            "output_format": self.output_format,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeatureRecipeSpecV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            recipe_id=d.get("recipe_id", ""),
            recipe_name=d.get("recipe_name", ""),
            input_kind=d.get("input_kind", "epoch_table"),
            bids_root=d.get("bids_root", ""),
            dataset_id=d.get("dataset_id", ""),
            subject_filter=list(d.get("subject_filter") or []),
            session_filter=list(d.get("session_filter") or []),
            task_filter=list(d.get("task_filter") or []),
            run_filter=list(d.get("run_filter") or []),
            event_state_mapping=dict(d.get("event_state_mapping") or {}),
            source_state=d.get("source_state", ""),
            target_state=d.get("target_state", ""),
            modality=d.get("modality", "EEG"),
            feature_set_id=d.get("feature_set_id", ""),
            feature_definitions=dict(d.get("feature_definitions") or {}),
            requested_features=list(d.get("requested_features") or []),
            epoch_window=dict(d.get("epoch_window") or {}),
            frequency_bands={k: list(v) for k, v in (d.get("frequency_bands") or {}).items()},
            channel_policy=dict(d.get("channel_policy") or {}),
            reference_policy=d.get("reference_policy", "as_recorded"),
            filter_policy=dict(d.get("filter_policy") or {}),
            artifact_policy=d.get("artifact_policy", "none"),
            max_subjects=d.get("max_subjects"),
            max_runs=d.get("max_runs"),
            max_epochs_per_state=d.get("max_epochs_per_state"),
            max_total_epochs=d.get("max_total_epochs"),
            output_format=d.get("output_format", "long"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "FeatureRecipeSpecV1":
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
            from adapters.mne_bids_feature_recipe_validation import FeatureRecipeValidationError

            raise FeatureRecipeValidationError("; ".join(errors))


def compute_manifest_id(*, recipe_id: str, features_written: int, created_at: str) -> str:
    basis = {"recipe_id": recipe_id, "features_written": features_written, "created_at": created_at}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DerivedFeatureRecipeManifestV1:
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
    skipped_subjects: list[dict[str, Any]] = field(default_factory=list)
    skipped_runs: list[dict[str, Any]] = field(default_factory=list)
    skipped_events: list[dict[str, Any]] = field(default_factory=list)
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
    ) -> "DerivedFeatureRecipeManifestV1":
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
            "skipped_subjects": list(self.skipped_subjects),
            "skipped_runs": list(self.skipped_runs),
            "skipped_events": list(self.skipped_events),
            "errors": list(self.errors),
            "qc_summary": dict(self.qc_summary or {}),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DerivedFeatureRecipeManifestV1":
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
            skipped_subjects=list(d.get("skipped_subjects") or []),
            skipped_runs=list(d.get("skipped_runs") or []),
            skipped_events=list(d.get("skipped_events") or []),
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
    def from_json(cls, text: str) -> "DerivedFeatureRecipeManifestV1":
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
            from adapters.mne_bids_feature_recipe_validation import FeatureRecipeValidationError

            raise FeatureRecipeValidationError("; ".join(errors))
