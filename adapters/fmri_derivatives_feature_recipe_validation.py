"""Structural validation and shared vocabulary for
`FmriFeatureRecipeSpecV1`/`FmriDerivedFeatureRecipeManifestV1`.

Reuses this repository's shared banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`) and
`transitions.features.validate_feature_name` (the same namespace check
`adapters.fmri_derivatives_features.cross_validate_rows` already uses) --
mirroring `adapters.mne_bids_feature_recipe_validation` and every other
validation module in this repository, which reuse shared checks rather
than declaring new copies. Output-path safety
(`dataset_acquisition.store.validate_target_root`) is enforced at
write-time in `adapters.fmri_derivatives_feature_recipe`, not here.
"""
from __future__ import annotations

from typing import Any

from phase_space.coordinate import scan_banned_phrases
from transitions.features import FeatureNameError, validate_feature_name

ALLOWED_INPUT_KINDS: frozenset[str] = frozenset({"timeseries_table", "connectivity_matrix", "graph_summary"})
ALLOWED_MODALITIES: frozenset[str] = frozenset({"fMRI"})
ALLOWED_OUTPUT_FORMATS: frozenset[str] = frozenset({"long"})

# Mission Phase D: kept deliberately small. Every name here must also be
# namespace-valid per transitions.features.validate_feature_name -- this
# set is a *subset* of what that function would accept, not a superset.
SUPPORTED_CONNECTIVITY_FEATURES: frozenset[str] = frozenset(
    {
        "connectivity.mean_connectivity",
        "connectivity.global_efficiency",
        "connectivity.modularity",
        "connectivity.degree",
        "connectivity.small_worldness",
    }
)
SUPPORTED_QC_FEATURES: frozenset[str] = frozenset(
    {"qc.valid_timepoints", "qc.mean_fd", "qc.motion_outlier_fraction", "qc.missing_value_fraction"}
)
# Never computed by this recipe -- only usable as a pass-through from an
# already-computed graph_summary input (see docs/fmri_derivatives_feature_recipe.md).
SUPPORTED_TOPOLOGY_FEATURES: frozenset[str] = frozenset(
    {"topology.fmri_graph_betti0", "topology.fmri_graph_betti1", "topology.fmri_graph_total_persistence_h1"}
)
SUPPORTED_FEATURES: frozenset[str] = SUPPORTED_CONNECTIVITY_FEATURES | SUPPORTED_QC_FEATURES | SUPPORTED_TOPOLOGY_FEATURES

# Features that require a thresholded graph to be built from a
# connectivity matrix -- irrelevant in input_kind='graph_summary' mode,
# where these values are a pure pass-through of already-computed numbers.
GRAPH_REQUIRING_FEATURES: frozenset[str] = frozenset(
    {"connectivity.global_efficiency", "connectivity.modularity", "connectivity.degree", "connectivity.small_worldness"}
)

_REQUIRED_BOUNDS_FIELDS: tuple[str, ...] = ("max_subjects", "max_runs", "max_timepoints_per_state", "max_total_timepoints")

FMRI_FEATURE_RECIPE_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "recipe output is evidence",
    "features prove",
    "extraction confirms",
    "guaranteed real signal",
    "validated atlas",
)


class FmriFeatureRecipeValidationError(ValueError):
    """Raised when a recipe spec or manifest fails structural validation."""


def _scan_extra_phrases(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        low = value.lower()
        for phrase in FMRI_FEATURE_RECIPE_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_extra_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_extra_phrases(item, f"{path}[{idx}]", errors)


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    _scan_extra_phrases(value, path, errors)


def validate_recipe_spec(spec: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    dataset_id = getattr(spec, "dataset_id", None)
    if not dataset_id:
        errors.append("dataset_id is required (rule 2)")

    feature_set_id = getattr(spec, "feature_set_id", None)
    if not feature_set_id:
        errors.append("feature_set_id is required (rule 2)")

    input_kind = getattr(spec, "input_kind", None)
    if input_kind not in ALLOWED_INPUT_KINDS:
        errors.append(f"input_kind '{input_kind}' must be one of {sorted(ALLOWED_INPUT_KINDS)} (rule 12)")

    atlas_or_parcellation = getattr(spec, "atlas_or_parcellation", None)
    source_state = getattr(spec, "source_state", None)
    target_state = getattr(spec, "target_state", None)

    # Rule 1: recipe_id deterministic from identity fields.
    if dataset_id and feature_set_id and source_state and target_state and atlas_or_parcellation:
        from adapters.fmri_derivatives_feature_recipe_schema import compute_recipe_id

        expected_id = compute_recipe_id(
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            source_state=source_state,
            target_state=target_state,
            requested_features=list(getattr(spec, "requested_features", None) or []),
            atlas_or_parcellation=atlas_or_parcellation,
            max_subjects=getattr(spec, "max_subjects", None),
            max_runs=getattr(spec, "max_runs", None),
            max_timepoints_per_state=getattr(spec, "max_timepoints_per_state", None),
            max_total_timepoints=getattr(spec, "max_total_timepoints", None),
        )
        recipe_id = getattr(spec, "recipe_id", None)
        if recipe_id != expected_id:
            errors.append(f"recipe_id '{recipe_id}' does not match deterministic id '{expected_id}' (rule 1)")

    # Rule 3.
    if not getattr(spec, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 3)")

    # Rule 4.
    if not getattr(spec, "provenance", None):
        errors.append("provenance is required (rule 4)")

    # Rule 5: state_mapping required, no implicit state inference.
    state_mapping = getattr(spec, "state_mapping", None) or {}
    if not state_mapping:
        errors.append("state_mapping is required and must be non-empty (rule 5) -- states are never inferred")

    # Rule 6: source_state/target_state required and must both appear as
    # values in state_mapping.
    if not source_state:
        errors.append("source_state is required (rule 6)")
    if not target_state:
        errors.append("target_state is required (rule 6)")
    if source_state and target_state and source_state == target_state:
        errors.append("source_state and target_state must differ (rule 6)")
    mapped_states = set(state_mapping.values())
    if source_state and state_mapping and source_state not in mapped_states:
        errors.append(f"source_state '{source_state}' does not appear as a value in state_mapping (rule 6)")
    if target_state and state_mapping and target_state not in mapped_states:
        errors.append(f"target_state '{target_state}' does not appear as a value in state_mapping (rule 6)")

    # Rule 7: modality must be fMRI for v1.
    modality = getattr(spec, "modality", None)
    if modality not in ALLOWED_MODALITIES:
        errors.append(f"modality '{modality}' must be one of {sorted(ALLOWED_MODALITIES)} for v1 (rule 7)")

    # Rule 8: atlas_or_parcellation required.
    if not atlas_or_parcellation or not isinstance(atlas_or_parcellation, str) or not atlas_or_parcellation.strip():
        errors.append("atlas_or_parcellation is required (non-empty string) (rule 8)")

    # Rule 9: confound_policy dict required with non-empty description.
    confound_policy = getattr(spec, "confound_policy", None)
    if not isinstance(confound_policy, dict) or not confound_policy:
        errors.append("confound_policy is required (non-empty object) (rule 9)")
    else:
        description = confound_policy.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append("confound_policy.description is required (non-empty string) (rule 9)")

    # Rule 10: requested_features must map to transitions feature
    # namespaces AND be within this recipe's deliberately small supported
    # set. Topology features are pass-through-only (never computed here).
    requested_features = getattr(spec, "requested_features", None) or []
    if not requested_features:
        errors.append("requested_features must be a non-empty list (rule 10)")
    for feature_name in requested_features:
        try:
            validate_feature_name(feature_name)
        except FeatureNameError as exc:
            errors.append(f"requested_features: {exc} (rule 10)")
        if feature_name not in SUPPORTED_FEATURES:
            errors.append(
                f"requested_features: '{feature_name}' is not in this recipe's supported feature set "
                f"{sorted(SUPPORTED_FEATURES)} (rule 10)"
            )
        if feature_name not in (getattr(spec, "feature_definitions", None) or {}):
            errors.append(f"requested_features: '{feature_name}' has no entry in feature_definitions (rule 10)")
        if feature_name in SUPPORTED_TOPOLOGY_FEATURES and input_kind != "graph_summary":
            errors.append(
                f"requested_features: '{feature_name}' is a topology feature -- this recipe never computes "
                "persistent homology, so it is only usable with input_kind='graph_summary' (rule 10)"
            )

    # Rule 13: an explicit graph threshold policy is required whenever a
    # graph-requiring feature is requested AND this recipe would actually
    # need to build a graph itself (never required for input_kind=
    # 'graph_summary', which is a pure pass-through of already-computed
    # values and never builds a graph).
    graph_policy = getattr(spec, "graph_policy", None) or {}
    if input_kind != "graph_summary" and any(f in GRAPH_REQUIRING_FEATURES for f in requested_features):
        if graph_policy.get("threshold") is None:
            errors.append(
                f"graph_policy.threshold is required (non-null number) because a graph-requiring feature "
                f"({sorted(f for f in requested_features if f in GRAPH_REQUIRING_FEATURES)}) was requested (rule 13)"
            )
        if not graph_policy.get("threshold_method"):
            errors.append("graph_policy.threshold_method is required when graph-requiring features are requested (rule 13)")

    # Rule 11: resource bounds required.
    for bound_field in _REQUIRED_BOUNDS_FIELDS:
        value = getattr(spec, bound_field, None)
        if value is None:
            errors.append(f"{bound_field} is required (rule 11)")
        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"{bound_field} must be a positive integer, got {value!r} (rule 11)")

    output_format = getattr(spec, "output_format", None)
    if output_format not in ALLOWED_OUTPUT_FORMATS:
        errors.append(f"output_format '{output_format}' must be one of {sorted(ALLOWED_OUTPUT_FORMATS)}")

    # Rule 14: banned overclaim language.
    for field_name in ("recipe_name", "provenance"):
        _scan_banned_phrases(getattr(spec, field_name, None) or "", field_name, errors)
    for field_name in ("limitations",):
        _scan_banned_phrases(getattr(spec, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(state_mapping, "state_mapping", errors)
    _scan_banned_phrases(getattr(spec, "feature_definitions", None) or {}, "feature_definitions", errors)
    _scan_banned_phrases(confound_policy if isinstance(confound_policy, dict) else {}, "confound_policy", errors)
    _scan_banned_phrases(getattr(spec, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_manifest(manifest: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(manifest, "recipe_id", None):
        errors.append("recipe_id is required")
    if not getattr(manifest, "dataset_id", None):
        errors.append("dataset_id is required")

    if not getattr(manifest, "limitations", None):
        errors.append("limitations must be a non-empty list")
    if not getattr(manifest, "provenance", None):
        errors.append("provenance is required")

    features_written = getattr(manifest, "features_written", 0)
    if not isinstance(features_written, int) or features_written < 0:
        errors.append("features_written must be a non-negative integer")

    for field_name in ("provenance", "repo_commit"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "errors", "skipped_inputs", "skipped_subjects", "states_observed"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(manifest, "qc_summary", None) or {}, "qc_summary", errors)
    _scan_banned_phrases(getattr(manifest, "metadata", None) or {}, "metadata", errors)

    return errors
