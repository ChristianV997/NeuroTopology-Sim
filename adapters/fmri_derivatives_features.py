"""Load and normalize fMRIPrep/Nilearn derived-feature tables, wide
tables, and connectivity/graph-summary JSON documents.

Three on-disk shapes are supported (see docs/fmri_derivatives_adapter.md):

- **long**: one row per (subject, session, source_state, target_state,
  feature), explicit `source_value`/`target_value`/`feature_definition`
  (+ `atlas_or_parcellation`) columns.
- **wide**: one row per subject with paired
  `<state>_<feature>`-style value columns; the mapping's `features` list
  is the *only* thing that ever associates a column with a canonical
  feature -- this module never parses a column name.
- **graph_summary**: a single, self-contained JSON document (no separate
  mapping file) carrying dataset/atlas/state metadata plus subject-level
  paired metrics and/or explicit cohort-level statistics.

All three normalize into the same internal "long row" dict shape, so
`group_rows` has exactly one code path regardless of which shape the user
supplied.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from transitions.features import FeatureNameError, validate_feature_name
from transitions.governance import NULL_CONTROL_STATUSES

from adapters.fmri_derivatives_validation import (
    AdapterMappingError,
    is_graph_feature,
    validate_mapping,
)


class AdapterDataError(ValueError):
    """Raised for feature-table-level problems distinct from mapping validation."""


@dataclass
class TransitionGroup:
    dataset_id: str
    subject_id: Optional[str]
    session_id: Optional[str]
    source_state: str
    target_state: str
    modality: str
    atlas_or_parcellation: str
    record_level: str = "subject"
    subject_count: Optional[int] = None
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (
            self.dataset_id, self.subject_id, self.session_id, self.source_state,
            self.target_state, self.modality, self.atlas_or_parcellation, self.record_level,
        )


def peek_json_format(path: Path) -> Optional[str]:
    """Return the top-level `"format"` key of a JSON file, or None if the
    file is not JSON or has no such key -- used to detect a self-contained
    graph_summary document before deciding whether a separate --mapping is
    required."""
    path = Path(path)
    if path.suffix.lower() != ".json" or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("format") if isinstance(data, dict) else None


def load_mapping(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise AdapterMappingError(f"mapping file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterMappingError(f"mapping file is not valid JSON: {path} ({exc})") from exc
    errors = validate_mapping(data)
    if errors:
        raise AdapterMappingError("; ".join(errors))
    return data


def load_graph_summary(path: Path) -> dict[str, Any]:
    """Load and validate a self-contained `format="graph_summary"` document."""
    path = Path(path)
    if not path.exists():
        raise AdapterMappingError(f"graph summary file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterMappingError(f"graph summary file is not valid JSON: {path} ({exc})") from exc
    errors = validate_mapping(data)
    if errors:
        raise AdapterMappingError("; ".join(errors))
    return data


def load_feature_table(path: Path) -> list[dict[str, Any]]:
    """Read a CSV or JSON feature table into a list of plain dicts."""
    path = Path(path)
    if not path.exists():
        raise AdapterDataError(f"features file does not exist: {path}")

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterDataError(f"features file is not valid JSON: {path} ({exc})") from exc
        rows = data.get("rows") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise AdapterDataError(f"features JSON must be a list of rows or {{'rows': [...]}}: {path}")
        return [dict(r) for r in rows]

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def normalize_wide_rows(rows: list[dict[str, Any]], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one wide-format row per subject into N long-equivalent rows,
    driven entirely by the explicit mapping -- never by column-name parsing."""
    dataset_id = mapping["dataset_id"]
    modality = mapping["modality"]
    source_state = mapping["source_state"]
    target_state = mapping["target_state"]
    atlas = mapping.get("atlas_or_parcellation", "")
    feature_definitions = mapping.get("feature_definitions") or {}
    subject_id_column = mapping.get("subject_id_column", "subject_id")
    session_id_column = mapping.get("session_id_column")
    preprocessing_provenance = mapping.get("preprocessing_provenance")
    confound_policy = mapping.get("confound_policy")
    null_control_status = mapping.get("null_control_status")

    long_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        subject_id = row.get(subject_id_column)
        if not subject_id:
            raise AdapterDataError(f"wide table row {i}: missing subject_id_column '{subject_id_column}'")
        session_id = row.get(session_id_column) if session_id_column else None

        for feature_entry in mapping["features"]:
            canonical_name = feature_entry["canonical_name"]
            source_col = feature_entry["source_column"]
            target_col = feature_entry["target_column"]
            if source_col not in row or target_col not in row:
                raise AdapterDataError(
                    f"wide table row {i} (subject_id={subject_id}): missing column "
                    f"'{source_col}' or '{target_col}' declared by mapping.features"
                )
            long_rows.append({
                "dataset_id": dataset_id, "subject_id": subject_id, "session_id": session_id,
                "source_state": source_state, "target_state": target_state, "modality": modality,
                "atlas_or_parcellation": row.get("atlas_or_parcellation") or atlas,
                "feature_name": canonical_name,
                "source_value": row[source_col], "target_value": row[target_col],
                "feature_definition": feature_definitions.get(canonical_name),
                "preprocessing_provenance": preprocessing_provenance,
                "confound_policy": confound_policy,
                "null_control_status": row.get("null_control_status") or null_control_status,
                "artifact_path": row.get("artifact_path"),
            })
    return long_rows


def expand_graph_summary(summary: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Expand a validated graph_summary document into `(subject_rows,
    cohort_entry)`. `subject_rows` matches the long-row shape
    `cross_validate_rows` expects; `cohort_entry` (if present) is a
    separate, pre-validated dict the orchestrator turns directly into one
    cohort-level TransitionRecordV1 (never routed through the per-row
    subject grouping path)."""
    dataset_id = summary["dataset_id"]
    modality = summary["modality"]
    atlas = summary.get("atlas_or_parcellation", "")
    source_state = summary["source_state"]
    target_state = summary["target_state"]
    feature_definitions = summary.get("feature_definitions") or {}
    preprocessing_provenance = summary.get("preprocessing_provenance")
    confound_policy = summary.get("confound_policy")
    null_control_status = summary.get("null_control_status")

    subject_rows: list[dict[str, Any]] = []
    for i, subj in enumerate(summary.get("subjects") or []):
        subject_id = subj.get("subject_id")
        if not subject_id:
            raise AdapterDataError(f"graph_summary.subjects[{i}]: missing subject_id")
        metrics = subj.get("metrics") or {}
        for feature_name, values in metrics.items():
            if not isinstance(values, dict):
                raise AdapterDataError(f"graph_summary.subjects[{i}].metrics['{feature_name}'] must be an object with source_value/target_value")
            subject_rows.append({
                "dataset_id": dataset_id, "subject_id": subject_id, "session_id": subj.get("session_id"),
                "source_state": source_state, "target_state": target_state, "modality": modality,
                "atlas_or_parcellation": atlas,
                "feature_name": feature_name,
                "source_value": values.get("source_value"), "target_value": values.get("target_value"),
                "feature_definition": feature_definitions.get(feature_name),
                "preprocessing_provenance": preprocessing_provenance,
                "confound_policy": confound_policy,
                "null_control_status": subj.get("null_control_status") or null_control_status,
                "artifact_path": subj.get("artifact_path"),
            })

    cohort_entry: Optional[dict[str, Any]] = None
    cohort = summary.get("cohort")
    if cohort:
        cohort_entry = {
            "dataset_id": dataset_id, "modality": modality, "atlas_or_parcellation": atlas,
            "source_state": source_state, "target_state": target_state,
            "subject_count": cohort["subject_count"],
            "metrics": cohort["metrics"],
            "feature_definitions": feature_definitions,
            "preprocessing_provenance": preprocessing_provenance,
            "confound_policy": confound_policy,
            "null_control_status": cohort.get("null_control_status") or null_control_status,
        }

    return subject_rows, cohort_entry


def _coerce_float(value: Any, *, field_name: str, row_index: int, errors: list[str]) -> Optional[float]:
    if value is None or value == "":
        errors.append(f"row {row_index}: {field_name} is missing")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"row {row_index}: {field_name}='{value}' is not numeric")
        return None


def cross_validate_rows(
    rows: list[dict[str, Any]], mapping: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate and type-coerce each row against the mapping. Returns
    `(valid_rows, errors)`; invalid rows are skipped, not raised on."""
    dataset_id = mapping["dataset_id"]
    modality = mapping["modality"]
    mapping_feature_definitions = mapping.get("feature_definitions") or {}
    mapping_atlas = mapping.get("atlas_or_parcellation")
    valid_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, row in enumerate(rows):
        row_errors: list[str] = []

        row_dataset_id = row.get("dataset_id") or dataset_id
        if row.get("dataset_id") and row["dataset_id"] != dataset_id:
            row_errors.append(f"row {i}: dataset_id '{row['dataset_id']}' does not match mapping.dataset_id '{dataset_id}'")

        subject_id = row.get("subject_id")
        if not subject_id:
            row_errors.append(f"row {i}: subject_id is required")

        source_state = row.get("source_state")
        target_state = row.get("target_state")
        if not source_state:
            row_errors.append(f"row {i}: source_state is required (never inferred)")
        if not target_state:
            row_errors.append(f"row {i}: target_state is required (never inferred)")
        if source_state and target_state and source_state == target_state:
            row_errors.append(f"row {i}: source_state and target_state must differ")

        row_modality = row.get("modality") or modality
        if row.get("modality") and row["modality"] != modality:
            row_errors.append(f"row {i}: modality '{row['modality']}' does not match mapping.modality '{modality}'")

        feature_name = row.get("feature_name")
        if not feature_name:
            row_errors.append(f"row {i}: feature_name is required")
        else:
            try:
                validate_feature_name(feature_name)
            except FeatureNameError as exc:
                row_errors.append(f"row {i}: {exc}")

        row_atlas = row.get("atlas_or_parcellation") or mapping_atlas
        if feature_name and is_graph_feature(feature_name) and not row_atlas:
            row_errors.append(
                f"row {i}: atlas_or_parcellation is required for graph/connectivity feature '{feature_name}' (never inferred)"
            )

        feature_definition = row.get("feature_definition") or mapping_feature_definitions.get(feature_name or "")
        if not feature_definition or not str(feature_definition).strip():
            row_errors.append(f"row {i}: missing feature_definition for feature '{feature_name}' (rejecting undefined feature)")

        source_value = _coerce_float(row.get("source_value"), field_name="source_value", row_index=i, errors=row_errors)
        target_value = _coerce_float(row.get("target_value"), field_name="target_value", row_index=i, errors=row_errors)

        null_control_status = row.get("null_control_status") or mapping.get("null_control_status")
        if null_control_status is not None and null_control_status not in NULL_CONTROL_STATUSES:
            row_errors.append(f"row {i}: null_control_status '{null_control_status}' must be one of {sorted(NULL_CONTROL_STATUSES)}")

        if row_errors:
            errors.extend(row_errors)
            continue

        valid_rows.append({
            "dataset_id": row_dataset_id,
            "subject_id": str(subject_id),
            "session_id": (str(row["session_id"]) if row.get("session_id") else None),
            "source_state": source_state, "target_state": target_state, "modality": row_modality,
            "atlas_or_parcellation": row_atlas or "",
            "feature_name": feature_name,
            "source_value": source_value, "target_value": target_value,
            "feature_definition": str(feature_definition),
            "preprocessing_provenance": row.get("preprocessing_provenance") or mapping.get("preprocessing_provenance"),
            "confound_policy": row.get("confound_policy") or mapping.get("confound_policy"),
            "null_control_status": null_control_status or "not_provided",
            "artifact_path": row.get("artifact_path"),
        })

    return valid_rows, errors


def group_rows(rows: list[dict[str, Any]]) -> tuple[list[TransitionGroup], list[str]]:
    """Group already-cross-validated subject-level rows into one
    TransitionGroup per (dataset_id, subject_id, session_id, source_state,
    target_state, modality, atlas_or_parcellation), rejecting groups with
    a duplicate feature_name."""
    groups: dict[tuple, TransitionGroup] = {}
    errors: list[str] = []

    for row in rows:
        key = (
            row["dataset_id"], row["subject_id"], row["session_id"], row["source_state"],
            row["target_state"], row["modality"], row["atlas_or_parcellation"], "subject",
        )
        group = groups.get(key)
        if group is None:
            group = TransitionGroup(
                dataset_id=row["dataset_id"], subject_id=row["subject_id"], session_id=row["session_id"],
                source_state=row["source_state"], target_state=row["target_state"], modality=row["modality"],
                atlas_or_parcellation=row["atlas_or_parcellation"], record_level="subject",
            )
            groups[key] = group
        group.rows.append(row)

    valid_groups: list[TransitionGroup] = []
    for key, group in groups.items():
        seen_features = [r["feature_name"] for r in group.rows]
        duplicates = {f for f in seen_features if seen_features.count(f) > 1}
        if duplicates:
            errors.append(f"group {key}: duplicate feature_name(s) {sorted(duplicates)} -- refusing to pick one arbitrarily")
            continue
        valid_groups.append(group)

    return valid_groups, errors
