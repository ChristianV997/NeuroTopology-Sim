"""Structural validation and shared vocabulary for
`ReportPipelineSpecV1`/`ReportPipelineRunManifestV1`/`ReportPackV1`.

Reuses this repository's shared banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`) plus a small additive
report-pack-specific banned-phrase tuple, mirroring every other
validation module in this repository (`adapters.mne_bids_feature_recipe_validation`,
`adapters.fmri_derivatives_feature_recipe_validation`, ...). Output-path
safety (`dataset_acquisition.store.validate_target_root`) is enforced at
write time in `workflows.store`, not here -- this module never touches
the filesystem, matching every other `validation.py` in this repository.
"""
from __future__ import annotations

from typing import Any

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from phase_space.coordinate import scan_banned_phrases

# Modes fully supported by workflows.report_pipeline.run_report_pipeline in
# v1. `mne_bids_bids_raw_recipe` is intentionally NOT supported in v1 (see
# docs/report_pipeline_runner.md) -- it requires synthesizing/reading a
# real MNE Raw file, which is a materially riskier code path than the
# other nine modes, all of which are thin orchestration over
# already-tested library functions.
SUPPORTED_INPUT_MODES: frozenset[str] = frozenset(
    {
        "existing_evidence_bundle",
        "mne_bids_epoch_table_recipe",
        "mne_bids_derived_features",
        "fmri_timeseries_recipe",
        "fmri_connectivity_matrix_recipe",
        "fmri_graph_summary_recipe",
        "fmri_derived_features",
        "builtin_ds005620_cohort_summary",
        "builtin_ds005620_spatial_defect_map",
        "builtin_ds000245_schaefer100_motcorr",
        "builtin_ds000245_kmeans100",
    }
)

# Every input_mode this milestone's mission spec names, including the ones
# this runner deliberately does not implement -- membership here (but not
# in SUPPORTED_INPUT_MODES) produces a clear "unsupported in v1" error
# rather than a generic "not a recognized input_mode" error.
KNOWN_BUT_UNSUPPORTED_INPUT_MODES: frozenset[str] = frozenset({"mne_bids_bids_raw_recipe"})

ALLOWED_INPUT_MODES: frozenset[str] = SUPPORTED_INPUT_MODES | KNOWN_BUT_UNSUPPORTED_INPUT_MODES

ALLOWED_MODALITIES: frozenset[str] = frozenset({"EEG", "fMRI"})

# (field_name -> "path" | "path_list") required, non-empty, for this
# input_mode's spec to even attempt execution (rule 7). Presence-only --
# actual file-existence is checked by the runner at execution time, since
# validation.py stays side-effect-free.
REQUIRED_FIELDS_BY_MODE: dict[str, tuple[tuple[str, str], ...]] = {
    "existing_evidence_bundle": (("evidence_bundle_path", "path"),),
    "mne_bids_epoch_table_recipe": (("recipe_spec_path", "path"), ("source_paths", "path_list")),
    "mne_bids_derived_features": (("feature_table_path", "path"), ("mapping_path", "path")),
    "fmri_timeseries_recipe": (("recipe_spec_path", "path"), ("source_paths", "path_list")),
    "fmri_connectivity_matrix_recipe": (("recipe_spec_path", "path"), ("source_paths", "path_list")),
    "fmri_graph_summary_recipe": (("recipe_spec_path", "path"), ("graph_summary_path", "path")),
    "fmri_derived_features": (("feature_table_path", "path"), ("mapping_path", "path")),
    "builtin_ds005620_cohort_summary": (("source_paths", "path_list"),),
    "builtin_ds005620_spatial_defect_map": (("source_paths", "path_list"),),
    "builtin_ds000245_schaefer100_motcorr": (("source_paths", "path_list"),),
    "builtin_ds000245_kmeans100": (("source_paths", "path_list"),),
}

REPORT_PIPELINE_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "is clinical evidence",
    "confirms diagnosis",
)


class ReportPipelineValidationError(ValueError):
    """Raised when a pipeline spec, run manifest, or report pack fails
    structural validation."""


def _scan_extra_phrases(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        low = value.lower()
        for phrase in REPORT_PIPELINE_EXTRA_BANNED_PHRASES:
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


def validate_output_root(output_root: Any) -> list[str]:
    """String-level prefix check only (rule 6) -- the real traversal/
    containment safety check is `dataset_acquisition.store.validate_target_root`,
    applied at write time in `workflows.store`."""
    errors: list[str] = []
    if not output_root or not isinstance(output_root, str):
        errors.append("output_root is required (non-empty string) (rule 6)")
        return errors
    raw = output_root.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in raw.split("/"):
        errors.append(f"output_root must be a safe relative repository path, got {output_root!r} (rule 6)")
        return errors
    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"output_root must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {output_root!r} (rule 6)")
    return errors


def validate_pipeline_spec(spec: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    dataset_id = getattr(spec, "dataset_id", None)
    if not dataset_id:
        errors.append("dataset_id is required")

    # Rule 1.
    if not getattr(spec, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(spec, "provenance", None):
        errors.append("provenance is required (rule 2)")

    # Rule 3 / 4.
    input_mode = getattr(spec, "input_mode", None)
    if not input_mode:
        errors.append("input_mode is required (rule 3) -- states/modes are never inferred")
    elif input_mode in KNOWN_BUT_UNSUPPORTED_INPUT_MODES:
        errors.append(f"input_mode '{input_mode}' is a recognized mode but is unsupported in v1 (rule 4)")
    elif input_mode not in SUPPORTED_INPUT_MODES:
        errors.append(f"input_mode '{input_mode}' is not a recognized mode; must be one of {sorted(ALLOWED_INPUT_MODES)} (rule 4)")

    modality = getattr(spec, "modality", None)
    if modality is not None and modality not in ALLOWED_MODALITIES:
        errors.append(f"modality '{modality}' must be one of {sorted(ALLOWED_MODALITIES)} when given")

    # Rule 1 (pipeline_id determinism).
    pipeline_id = getattr(spec, "pipeline_id", None)
    if input_mode and dataset_id and pipeline_id:
        from workflows.report_pipeline import compute_pipeline_id

        expected_id = compute_pipeline_id(
            input_mode=input_mode,
            dataset_id=dataset_id,
            source_paths=list(getattr(spec, "source_paths", None) or []),
            recipe_spec_path=getattr(spec, "recipe_spec_path", None),
            feature_table_path=getattr(spec, "feature_table_path", None),
            mapping_path=getattr(spec, "mapping_path", None),
            output_root=getattr(spec, "output_root", None),
        )
        if pipeline_id != expected_id:
            errors.append(f"pipeline_id '{pipeline_id}' does not match deterministic id '{expected_id}' (rule 1)")

    # Rule 6.
    errors.extend(validate_output_root(getattr(spec, "output_root", None)))

    # Rule 7.
    if input_mode in SUPPORTED_INPUT_MODES:
        for field_name, kind in REQUIRED_FIELDS_BY_MODE.get(input_mode, ()):
            value = getattr(spec, field_name, None)
            if kind == "path" and not value:
                errors.append(f"'{field_name}' is required for input_mode='{input_mode}' (rule 7)")
            elif kind == "path_list" and not value:
                errors.append(f"'{field_name}' must be a non-empty list for input_mode='{input_mode}' (rule 7)")

    resource_bounds = getattr(spec, "resource_bounds", None)
    if resource_bounds is not None and not isinstance(resource_bounds, dict):
        errors.append("resource_bounds must be an object when given")

    execution_steps = getattr(spec, "execution_steps", None)
    if execution_steps is not None and not isinstance(execution_steps, list):
        errors.append("execution_steps must be a list when given")

    # Rule 11.
    for field_name in ("pipeline_name", "provenance", "requested_use", "claim_family"):
        _scan_banned_phrases(getattr(spec, field_name, None) or "", field_name, errors)
    _scan_banned_phrases(getattr(spec, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(spec, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_run_manifest(manifest: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(manifest, "pipeline_id", None):
        errors.append("pipeline_id is required")
    if not getattr(manifest, "dataset_id", None):
        errors.append("dataset_id is required")
    if not getattr(manifest, "limitations", None):
        errors.append("limitations must be a non-empty list")
    if not getattr(manifest, "provenance", None):
        errors.append("provenance is required")

    execution_status = getattr(manifest, "execution_status", None)
    if execution_status not in {"dry_run", "completed", "completed_with_warnings", "failed"}:
        errors.append(
            f"execution_status '{execution_status}' must be one of "
            "{'dry_run', 'completed', 'completed_with_warnings', 'failed'}"
        )

    for field_name in ("provenance", "repo_commit"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "errors", "warnings", "steps_planned", "steps_completed", "steps_skipped"):
        _scan_banned_phrases(getattr(manifest, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(manifest, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_report_pack(pack: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises.

    Rules 9 / 12: a report pack never carries its own claim_scope/
    evidence_level field to promote -- it can only ever *reference* the
    claim_scope_ceiling/evidence_level_ceiling values already recorded on
    the EvidenceBundleV1(s) it points to (via `summary`), never assign a
    new/higher one. This function checks that no promoting field exists
    on the pack itself and that the banned-phrase scan (which includes
    'is clinical evidence') finds nothing."""
    errors: list[str] = []

    if not getattr(pack, "dataset_id", None):
        errors.append("dataset_id is required")
    if not getattr(pack, "limitations", None):
        errors.append("limitations must be a non-empty list")
    if not getattr(pack, "blocked_interpretations", None):
        errors.append("blocked_interpretations must be a non-empty list -- a report pack must always be explicit about what it does not support")

    if hasattr(pack, "claim_scope") or hasattr(pack, "evidence_level"):
        errors.append(
            "ReportPackV1 must not carry its own claim_scope/evidence_level field -- it may only "
            "reference the ceilings already recorded on the EvidenceBundleV1(s) it points to (rule 9/12)"
        )

    report_pack_id = getattr(pack, "report_pack_id", None)
    if report_pack_id:
        from workflows.report_pack import compute_report_pack_id

        expected_id = compute_report_pack_id(
            dataset_id=getattr(pack, "dataset_id", None),
            input_mode=getattr(pack, "input_mode", None),
            evidence_bundle_ids=list(getattr(pack, "evidence_bundle_ids", None) or []),
            evidence_report_ids=list(getattr(pack, "evidence_report_ids", None) or []),
        )
        if report_pack_id != expected_id:
            errors.append(f"report_pack_id '{report_pack_id}' does not match deterministic id '{expected_id}'")

    for field_name in ("summary", "artifact_manifest", "metadata"):
        _scan_banned_phrases(getattr(pack, field_name, None) or {}, field_name, errors)
    for field_name in ("limitations", "blocked_interpretations", "reproducibility_commands", "generated_files"):
        _scan_banned_phrases(getattr(pack, field_name, None) or [], field_name, errors)

    return errors
