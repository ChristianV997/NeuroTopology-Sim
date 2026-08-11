"""Structural validation for fMRIPrep/Nilearn derived-feature mapping and
graph-summary files.

Mirrors `adapters.validation` (the MNE/BIDS adapter's mapping validator)
with the fMRI-specific facts this domain requires to stay explicit:
`modality` is always exactly `"fMRI"`, `atlas_or_parcellation` is required
whenever a connectivity/topology (graph) feature is involved, and
`confound_policy` is always required alongside `preprocessing_provenance`
-- an fMRI feature table with no stated confound-regression policy is
exactly the kind of ambiguity this adapter must fail closed on rather than
silently accept.
"""
from __future__ import annotations

from typing import Any

from phase_space.coordinate import scan_banned_phrases
from transitions.features import FeatureNameError, validate_feature_name
from transitions.governance import NULL_CONTROL_STATUSES

ALLOWED_FORMATS: frozenset[str] = frozenset({"long", "wide", "graph_summary"})

# fMRI only -- this adapter is scoped to fMRI derivatives; a mapping
# declaring anything else fails closed rather than being guessed into fMRI.
REQUIRED_MODALITY: str = "fMRI"

# Feature namespaces that describe a graph/connectivity metric computed
# over a parcellation -- atlas_or_parcellation is required whenever any
# declared/observed feature falls in one of these.
GRAPH_FEATURE_NAMESPACES: frozenset[str] = frozenset({"connectivity", "topology"})


class AdapterMappingError(ValueError):
    """Raised when a derived-feature mapping or graph-summary file fails
    structural validation."""


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)


def is_graph_feature(feature_name: str) -> bool:
    if not feature_name or "." not in feature_name:
        return False
    return feature_name.split(".", 1)[0] in GRAPH_FEATURE_NAMESPACES


def validate_feature_definitions(feature_definitions: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(feature_definitions, dict) or not feature_definitions:
        errors.append("feature_definitions must be a non-empty object mapping canonical feature name -> definition")
        return errors
    for name, definition in feature_definitions.items():
        try:
            validate_feature_name(name)
        except FeatureNameError as exc:
            errors.append(f"feature_definitions: {exc}")
        if not isinstance(definition, str) or not definition.strip():
            errors.append(f"feature_definitions['{name}'] must be a non-empty definition string")
    return errors


def _validate_common_mapping_fields(mapping: dict, errors: list[str]) -> None:
    dataset_id = mapping.get("dataset_id")
    if not dataset_id or not isinstance(dataset_id, str):
        errors.append("mapping.dataset_id is required (non-empty string)")

    modality = mapping.get("modality")
    if modality != REQUIRED_MODALITY:
        errors.append(f"mapping.modality '{modality}' must be exactly '{REQUIRED_MODALITY}'")

    preprocessing_provenance = mapping.get("preprocessing_provenance")
    if not isinstance(preprocessing_provenance, dict) or not preprocessing_provenance:
        errors.append("mapping.preprocessing_provenance is required (non-empty object) -- explicit provenance, never omitted")

    confound_policy = mapping.get("confound_policy")
    if not confound_policy or not isinstance(confound_policy, str) or not confound_policy.strip():
        errors.append(
            "mapping.confound_policy is required (non-empty string, e.g. '24-param + aCompCor') -- "
            "an fMRI feature table with no stated confound-regression policy is ambiguous"
        )

    null_control_status = mapping.get("null_control_status")
    if null_control_status is not None and null_control_status not in NULL_CONTROL_STATUSES:
        errors.append(f"mapping.null_control_status '{null_control_status}' must be one of {sorted(NULL_CONTROL_STATUSES)}")

    _scan_banned_phrases(dataset_id, "mapping.dataset_id", errors)
    _scan_banned_phrases(mapping.get("source_state"), "mapping.source_state", errors)
    _scan_banned_phrases(mapping.get("target_state"), "mapping.target_state", errors)
    _scan_banned_phrases(preprocessing_provenance, "mapping.preprocessing_provenance", errors)
    _scan_banned_phrases(confound_policy, "mapping.confound_policy", errors)


def validate_mapping(mapping: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises.

    Structural validation only. For `format="long"`, `atlas_or_parcellation`
    is not required at the mapping level (rows may carry their own, or the
    format may involve no graph/connectivity feature at all) -- that check
    happens per-row in `adapters.fmri_derivatives_features.cross_validate_rows`.
    For `format="wide"`/`"graph_summary"`, every declared feature is known
    up front, so `atlas_or_parcellation` is required in the mapping
    whenever any declared feature is a graph/connectivity feature.
    """
    errors: list[str] = []
    if not isinstance(mapping, dict):
        return ["mapping must be a JSON object"]

    fmt = mapping.get("format")
    if fmt not in ALLOWED_FORMATS:
        errors.append(f"mapping.format '{fmt}' must be one of {sorted(ALLOWED_FORMATS)}")

    _validate_common_mapping_fields(mapping, errors)

    feature_definitions = mapping.get("feature_definitions")
    if fmt in ("wide", "graph_summary") or feature_definitions is not None:
        errors.extend(validate_feature_definitions(feature_definitions))

    if fmt in ("wide", "graph_summary"):
        source_state = mapping.get("source_state")
        target_state = mapping.get("target_state")
        if not source_state or not isinstance(source_state, str):
            errors.append(f"mapping.source_state is required for format='{fmt}' (non-empty string)")
        if not target_state or not isinstance(target_state, str):
            errors.append(f"mapping.target_state is required for format='{fmt}' (non-empty string)")
        if source_state and target_state and source_state == target_state:
            errors.append("mapping.source_state and mapping.target_state must differ")

        defined_names = set((feature_definitions or {}).keys())
        graph_features_present = any(is_graph_feature(n) for n in defined_names)
        atlas = mapping.get("atlas_or_parcellation")
        if graph_features_present and (not atlas or not isinstance(atlas, str) or not atlas.strip()):
            errors.append(
                "mapping.atlas_or_parcellation is required (non-empty string) because a "
                "connectivity/topology (graph) feature is declared in feature_definitions"
            )

    if fmt == "wide":
        features = mapping.get("features")
        if not isinstance(features, list) or not features:
            errors.append("mapping.features is required for format='wide' (non-empty list)")
        else:
            defined_names = set((feature_definitions or {}).keys())
            seen_columns: set[str] = set()
            for i, entry in enumerate(features):
                if not isinstance(entry, dict):
                    errors.append(f"mapping.features[{i}] must be an object")
                    continue
                canonical_name = entry.get("canonical_name")
                source_column = entry.get("source_column")
                target_column = entry.get("target_column")
                if not canonical_name or canonical_name not in defined_names:
                    errors.append(
                        f"mapping.features[{i}].canonical_name '{canonical_name}' must be a key "
                        "present in mapping.feature_definitions"
                    )
                if not source_column or not isinstance(source_column, str):
                    errors.append(f"mapping.features[{i}].source_column is required (non-empty string)")
                if not target_column or not isinstance(target_column, str):
                    errors.append(f"mapping.features[{i}].target_column is required (non-empty string)")
                if source_column and source_column == target_column:
                    errors.append(f"mapping.features[{i}]: source_column and target_column must differ")
                for col in (source_column, target_column):
                    if col:
                        if col in seen_columns:
                            errors.append(f"mapping.features: column '{col}' referenced by more than one feature")
                        seen_columns.add(col)

        subject_id_column = mapping.get("subject_id_column", "subject_id")
        if not isinstance(subject_id_column, str) or not subject_id_column:
            errors.append("mapping.subject_id_column must be a non-empty string when given")

    if fmt == "graph_summary":
        subjects = mapping.get("subjects")
        cohort = mapping.get("cohort")
        if not subjects and not cohort:
            errors.append("graph_summary requires at least one of 'subjects' (list) or 'cohort' (object)")
        if subjects is not None and not isinstance(subjects, list):
            errors.append("graph_summary.subjects must be a list when given")
        if cohort is not None:
            if not isinstance(cohort, dict):
                errors.append("graph_summary.cohort must be an object when given")
            else:
                subject_count = cohort.get("subject_count")
                if not isinstance(subject_count, int) or subject_count < 2:
                    errors.append("graph_summary.cohort.subject_count must be an integer >= 2 (rule: cohort output requires explicit subject_count)")
                metrics = cohort.get("metrics")
                if not isinstance(metrics, dict) or not metrics:
                    errors.append("graph_summary.cohort.metrics must be a non-empty object")

    return errors


def validate_mapping_or_raise(mapping: Any) -> None:
    errors = validate_mapping(mapping)
    if errors:
        raise AdapterMappingError("; ".join(errors))
