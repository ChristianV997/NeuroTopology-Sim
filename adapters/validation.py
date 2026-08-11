"""Structural validation for MNE/BIDS derived-feature mapping files.

A "mapping" is the small, explicit, human-authored JSON document that
tells `adapters.mne_bids` how to turn a derived feature table into
`TransitionRecordV1` artifacts: which column(s) hold which canonical
feature, what `source_state`/`target_state`/`modality` this export
represents, and what each feature actually means. This module enforces
that every one of those facts is explicit -- never inferred from a column
name, a file name, or a table shape -- fail closed on anything ambiguous
or missing.

Reuses this repository's existing claim/evidence vocabulary and
banned-phrase scanner rather than declaring new copies, mirroring
`benchmarks.validation`/`reports.validation`/`external_tools.validation`.
"""
from __future__ import annotations

from typing import Any

from phase_space.coordinate import scan_banned_phrases
from transitions.features import FeatureNameError, validate_feature_name
from transitions.governance import NULL_CONTROL_STATUSES

ALLOWED_FORMATS: frozenset[str] = frozenset({"long", "wide"})

# EEG/MEG/iEEG/fNIRS -- the modalities this adapter's mission scope names
# explicitly. Not the full ALLOWED_NAMESPACES/general modality universe;
# a mapping declaring anything else fails closed rather than being guessed
# into one of these.
ALLOWED_MODALITIES: frozenset[str] = frozenset({"EEG", "MEG", "iEEG", "fNIRS"})


class AdapterMappingError(ValueError):
    """Raised when a derived-feature mapping file fails structural validation."""


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)


def validate_feature_definitions(feature_definitions: Any) -> list[str]:
    """Every canonical feature name must be namespace-valid and carry a
    non-empty, explicit definition string. Returns error strings, never
    raises."""
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


def validate_mapping(mapping: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises.

    Structural validation only -- does not know about the actual feature
    table's rows (that cross-check happens in
    `adapters.mne_bids_features.cross_validate_rows`, since it needs the
    loaded table).
    """
    errors: list[str] = []
    if not isinstance(mapping, dict):
        return ["mapping must be a JSON object"]

    fmt = mapping.get("format")
    if fmt not in ALLOWED_FORMATS:
        errors.append(f"mapping.format '{fmt}' must be one of {sorted(ALLOWED_FORMATS)}")

    dataset_id = mapping.get("dataset_id")
    if not dataset_id or not isinstance(dataset_id, str):
        errors.append("mapping.dataset_id is required (non-empty string)")

    modality = mapping.get("modality")
    if modality not in ALLOWED_MODALITIES:
        errors.append(f"mapping.modality '{modality}' must be one of {sorted(ALLOWED_MODALITIES)}")

    # feature_definitions is required at the mapping level for format='wide'
    # (a wide table has no room for a per-row definition column). For
    # format='long', each row carries its own explicit feature_definition
    # column instead (see adapters.mne_bids_features.cross_validate_rows);
    # mapping.feature_definitions is optional supplementary context there.
    feature_definitions = mapping.get("feature_definitions")
    if fmt == "wide" or feature_definitions is not None:
        errors.extend(validate_feature_definitions(feature_definitions))

    preprocessing_provenance = mapping.get("preprocessing_provenance")
    if not isinstance(preprocessing_provenance, dict) or not preprocessing_provenance:
        errors.append("mapping.preprocessing_provenance is required (non-empty object) -- explicit provenance, never omitted")

    null_control_status = mapping.get("null_control_status")
    if null_control_status is not None and null_control_status not in NULL_CONTROL_STATUSES:
        errors.append(
            f"mapping.null_control_status '{null_control_status}' must be one of {sorted(NULL_CONTROL_STATUSES)}"
        )

    if fmt == "wide":
        source_state = mapping.get("source_state")
        target_state = mapping.get("target_state")
        if not source_state or not isinstance(source_state, str):
            errors.append("mapping.source_state is required for format='wide' (non-empty string)")
        if not target_state or not isinstance(target_state, str):
            errors.append("mapping.target_state is required for format='wide' (non-empty string)")
        if source_state and target_state and source_state == target_state:
            errors.append("mapping.source_state and mapping.target_state must differ")

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

    _scan_banned_phrases(mapping.get("dataset_id"), "mapping.dataset_id", errors)
    _scan_banned_phrases(mapping.get("source_state"), "mapping.source_state", errors)
    _scan_banned_phrases(mapping.get("target_state"), "mapping.target_state", errors)
    _scan_banned_phrases(feature_definitions, "mapping.feature_definitions", errors)
    _scan_banned_phrases(preprocessing_provenance, "mapping.preprocessing_provenance", errors)

    return errors


def validate_mapping_or_raise(mapping: Any) -> None:
    errors = validate_mapping(mapping)
    if errors:
        raise AdapterMappingError("; ".join(errors))
