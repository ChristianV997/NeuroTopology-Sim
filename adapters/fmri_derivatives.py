"""fMRIPrep/Nilearn Derived fMRI Adapter v1.

Usage::

    # fMRIPrep-style metadata scan only (no transitions)
    python -m adapters.fmri_derivatives --scan-derivatives /path/to/derivatives_root \\
        --write-dataset-records outputs/adapters/fmri_derivatives/scan.json

    # derived-feature export -> TransitionRecordV1 (+ optional phase-space/
    # evidence-bundle/report)
    python -m adapters.fmri_derivatives \\
        --features derived_features.csv --mapping mapping.json \\
        --out outputs/adapters/fmri_derivatives/my_export \\
        --registry benchmarks/registry_seed.json \\
        --requested-use transition_export

    # self-contained connectivity/graph-summary JSON (no separate --mapping)
    python -m adapters.fmri_derivatives \\
        --features graph_summary.json \\
        --out outputs/adapters/fmri_derivatives/my_export \\
        --registry benchmarks/registry_seed.json

This adapter does not run raw BOLD preprocessing, does not execute
fMRIPrep, and does not fit Nilearn models. It reads lightweight fMRIPrep-
style metadata (`dataset_description.json`, `participants.tsv`,
`*_desc-confounds_timeseries.tsv`, derivative JSON sidecars) and/or an
explicit, user-provided derived feature table + mapping (or a
self-contained connectivity/graph-summary JSON), then produces governed
`DatasetRecordV1`/`ArtifactRecordV1`/`TransitionRecordV1` (and,
optionally, `PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/`EvidenceReportV1`)
artifacts. See docs/fmri_derivatives_adapter.md.

This is the package's only CLI entry point for this adapter (mirroring
`adapters.mne_bids`'s own precedent); `adapters.fmri_derivatives_validation`,
`adapters.fmri_derivatives_features`, and `adapters.fmri_derivatives_contract`
are library-only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.artifact_registry import ArtifactRecordV1  # noqa: E402
from benchmarks.dataset_registry import DatasetRecordV1  # noqa: E402
from benchmarks.export_registry import BenchmarkRegistry, RegistryError  # noqa: E402
from transitions.record import TransitionRecordV1  # noqa: E402
from transitions.store import TransitionStore  # noqa: E402

from adapters.fmri_derivatives_contract import AdapterEligibilityError, check_adapter_eligible  # noqa: E402
from adapters.fmri_derivatives_features import (  # noqa: E402
    AdapterDataError,
    cross_validate_rows,
    expand_graph_summary,
    group_rows,
    load_feature_table,
    load_graph_summary,
    load_mapping,
    normalize_wide_rows,
    peek_json_format,
)
from adapters.fmri_derivatives_validation import AdapterMappingError  # noqa: E402

_FORBIDDEN_USES: list[str] = [
    "clinical_claim", "diagnostic_claim", "treatment_claim",
    "consciousness_biomarker_claim", "spiritual_attainment_claim",
    "mechanistic_causal_claim", "final_claim_confirmation",
    "cross_dataset_replication_claim", "prospective_prediction_claim",
]

_CONFOUNDS_SUFFIX = "_desc-confounds_timeseries.tsv"
_BIDS_ENTITY_PATTERN = re.compile(r"(?P<key>[a-zA-Z]+)-(?P<value>[a-zA-Z0-9]+)")


class AdapterExportError(ValueError):
    """Raised when the derived-feature export cannot proceed, or produces
    zero valid transition records."""


class AdapterRegistryError(ValueError):
    """Raised when the benchmark registry denies the requested use, or
    registry context is missing without an explicit no_registry override."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "unknown"


def _bids_entities(filename: str) -> dict[str, str]:
    """Parse explicit BIDS filename entities (key-value, hyphen-separated,
    underscore-delimited) -- reading a formal, standardized filename
    grammar, not inferring anything about content."""
    stem = filename.split("_desc-")[0] if "_desc-" in filename else filename
    entities: dict[str, str] = {}
    for part in stem.split("_"):
        m = _BIDS_ENTITY_PATTERN.fullmatch(part)
        if m:
            entities[m.group("key")] = m.group("value")
    return entities


# ── Phase D: fMRIPrep-style metadata scan ────────────────────────────────


@dataclass
class FmriDerivativesMetadataSummary:
    derivatives_root: str
    dataset_id: str
    dataset_description: Optional[dict[str, Any]]
    fmriprep_dataset_description: Optional[dict[str, Any]]
    participants: list[dict[str, Any]] = field(default_factory=list)
    n_subjects: int = 0
    confounds_files: list[str] = field(default_factory=list)
    confounds_entities: list[dict[str, str]] = field(default_factory=list)
    derivative_metadata_files: list[str] = field(default_factory=list)
    modalities_declared: list[str] = field(default_factory=list)


def scan_fmri_derivatives_metadata(derivatives_root: Path) -> FmriDerivativesMetadataSummary:
    """Read cheap fMRIPrep-style metadata (JSON/TSV file presence and
    content, plus explicit BIDS filename entities) -- never opens, parses,
    or reads any raw BOLD NIfTI file."""
    derivatives_root = Path(derivatives_root)
    if not derivatives_root.exists() or not derivatives_root.is_dir():
        raise AdapterDataError(f"derivatives_root does not exist or is not a directory: {derivatives_root}")

    dd_path = derivatives_root / "dataset_description.json"
    dataset_description: Optional[dict[str, Any]] = None
    if dd_path.exists():
        try:
            dataset_description = json.loads(dd_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterDataError(f"dataset_description.json is not valid JSON: {dd_path} ({exc})") from exc

    fmriprep_dd_path = derivatives_root / "derivatives" / "fmriprep" / "dataset_description.json"
    fmriprep_dataset_description: Optional[dict[str, Any]] = None
    if fmriprep_dd_path.exists():
        try:
            fmriprep_dataset_description = json.loads(fmriprep_dd_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterDataError(f"fmriprep dataset_description.json is not valid JSON: {fmriprep_dd_path} ({exc})") from exc

    participants_path = derivatives_root / "participants.tsv"
    participants: list[dict[str, Any]] = []
    if participants_path.exists():
        with participants_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            participants = [dict(row) for row in reader]

    confounds_paths = sorted(derivatives_root.rglob(f"*{_CONFOUNDS_SUFFIX}"))
    confounds_files = [str(p.relative_to(derivatives_root)) for p in confounds_paths]
    confounds_entities = [_bids_entities(p.name) for p in confounds_paths]

    json_sidecars = sorted(
        p for p in derivatives_root.rglob("*.json")
        if p != dd_path and p != fmriprep_dd_path and "dataset_description.json" not in p.name
    )
    derivative_metadata_files = [str(p.relative_to(derivatives_root)) for p in json_sidecars]

    modalities_declared = ["fMRI"] if (list(derivatives_root.rglob("func")) or confounds_paths) else ["unknown"]

    if dataset_description and dataset_description.get("Name"):
        dataset_id = _slugify(str(dataset_description["Name"]))
    else:
        dataset_id = _slugify(derivatives_root.name)

    return FmriDerivativesMetadataSummary(
        derivatives_root=str(derivatives_root),
        dataset_id=dataset_id,
        dataset_description=dataset_description,
        fmriprep_dataset_description=fmriprep_dataset_description,
        participants=participants,
        n_subjects=len(participants),
        confounds_files=confounds_files,
        confounds_entities=confounds_entities,
        derivative_metadata_files=derivative_metadata_files,
        modalities_declared=modalities_declared,
    )


def make_dataset_record_from_fmri_derivatives(
    summary: FmriDerivativesMetadataSummary, *, mapping_provided: bool = False,
) -> DatasetRecordV1:
    """Conservative, exploration-role DatasetRecordV1 -- never marks
    validation-ready. 'transition_export' is only added to allowed_uses
    when an explicit mapping accompanied this scan."""
    display_name = (
        str(summary.dataset_description["Name"])
        if summary.dataset_description and summary.dataset_description.get("Name")
        else summary.dataset_id
    )

    allowed_uses = ["documentation", "feature_design"]
    if mapping_provided:
        allowed_uses.append("transition_export")

    provenance = (
        f"fMRIPrep-style metadata scan via "
        f"adapters.fmri_derivatives.scan_fmri_derivatives_metadata over "
        f"'{summary.derivatives_root}': dataset_description.json "
        f"{'found' if summary.dataset_description else 'not found'}; "
        f"fmriprep derivatives dataset_description.json "
        f"{'found' if summary.fmriprep_dataset_description else 'not found'}; "
        f"participants.tsv {'found (' + str(summary.n_subjects) + ' rows)' if summary.participants else 'not found'}; "
        f"{len(summary.confounds_files)} *{_CONFOUNDS_SUFFIX} file(s); "
        f"{len(summary.derivative_metadata_files)} derivative metadata sidecar file(s)."
    )

    limitations = [
        "This DatasetRecordV1 was generated by a lightweight fMRIPrep-style "
        "metadata scan (dataset_description.json/participants.tsv/"
        "*_desc-confounds_timeseries.tsv/derivative JSON sidecar file "
        "presence and content) -- it does not validate, parse, or analyze "
        "any raw BOLD signal, does not run fMRIPrep or fit any Nilearn "
        "model, and does not confirm transition semantics, atlas validity, "
        "or condition labels for any subject.",
        "modalities_declared reflects only the presence of a 'func' "
        "directory or confounds files on disk, not any inspection of BOLD "
        "signal content.",
    ]
    if not mapping_provided:
        limitations.append(
            "No derived-feature mapping accompanied this scan -- "
            "'transition_export' is deliberately excluded from allowed_uses "
            "until an explicit mapping is provided to "
            "adapters.fmri_derivatives.export_fmri_derivative_transitions."
        )

    return DatasetRecordV1.make(
        dataset_id=summary.dataset_id,
        display_name=str(display_name),
        modalities=list(summary.modalities_declared),
        artifact_paths=[summary.derivatives_root],
        artifact_kinds=["fmriprep_derivatives_scan"],
        current_role="exploration",
        allowed_uses=allowed_uses,
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling=("L4_cross_subject_dataset_specific" if mapping_provided else "L0_computational_artifact"),
        label_quality="unvalidated_fmriprep_metadata_scan",
        provenance=provenance,
        limitations=limitations,
        metadata={"fmri_derivatives_scan": True, "mapping_provided": mapping_provided, "adapter": "adapters.fmri_derivatives"},
    )


def make_artifact_records_from_fmri_derivatives(summary: FmriDerivativesMetadataSummary) -> list[ArtifactRecordV1]:
    """One ArtifactRecordV1 per notable fMRIPrep-style metadata file found
    -- always `external=True` (the scanned directory is a user's local
    derivatives tree, not part of this repository)."""
    common = dict(
        dataset_id=summary.dataset_id,
        record_kind="committed_artifact",
        external=True,
        current_role="exploration",
        allowed_uses=["documentation", "feature_design"],
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        produced_by="adapters.fmri_derivatives.scan_fmri_derivatives_metadata",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        limitations=["fMRIPrep-style metadata file presence/content only -- not scientifically validated by this scan."],
    )

    records: list[ArtifactRecordV1] = []
    root = Path(summary.derivatives_root)

    if summary.dataset_description is not None:
        records.append(ArtifactRecordV1.make(
            path=str(root / "dataset_description.json"), artifact_kind="bids_dataset_description", **common,
        ))
    if summary.fmriprep_dataset_description is not None:
        records.append(ArtifactRecordV1.make(
            path=str(root / "derivatives" / "fmriprep" / "dataset_description.json"),
            artifact_kind="fmriprep_dataset_description", **common,
        ))
    if summary.participants:
        records.append(ArtifactRecordV1.make(
            path=str(root / "participants.tsv"), artifact_kind="bids_participants_tsv", **common,
        ))
    for rel in summary.confounds_files:
        records.append(ArtifactRecordV1.make(
            path=str(root / rel), artifact_kind="fmriprep_confounds_timeseries_tsv", **common,
        ))
    for rel in summary.derivative_metadata_files:
        records.append(ArtifactRecordV1.make(
            path=str(root / rel), artifact_kind="fmriprep_derivative_metadata", **common,
        ))
    return records


def _candidate_dataset_record_from_mapping(
    mapping: dict[str, Any], *, features_path: Path, mapping_path: Optional[Path], include_phase_space: bool = False,
) -> DatasetRecordV1:
    """Conservative candidate DatasetRecordV1 for a dataset_id that is not
    yet in the loaded registry, built from an explicit mapping/graph-summary
    (not a metadata scan) -- 'transition_export' is included because a
    valid mapping already exists by the time this is called."""
    allowed_uses = ["documentation", "feature_design", "transition_export"]
    if include_phase_space:
        allowed_uses.append("phase_space_export")
    provenance_path = str(mapping_path) if mapping_path is not None else str(features_path)
    return DatasetRecordV1.make(
        dataset_id=mapping["dataset_id"],
        display_name=mapping["dataset_id"],
        modalities=[mapping["modality"]],
        artifact_paths=[str(features_path), provenance_path],
        artifact_kinds=["nilearn_derived_feature_table"],
        current_role="exploration",
        allowed_uses=allowed_uses,
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L4_cross_subject_dataset_specific",
        label_quality="explicit_user_provided_mapping",
        provenance=(
            f"Auto-registered by adapters.fmri_derivatives.export_fmri_derivative_transitions "
            f"from an explicit mapping/graph-summary ('{provenance_path}') and derived feature "
            f"artifact ('{features_path}') -- no prior registry entry existed for dataset_id="
            f"'{mapping['dataset_id']}'."
        ),
        limitations=[
            "This DatasetRecordV1 was auto-generated because no prior registry "
            "entry existed for this dataset_id -- it reflects only what the "
            "supplied mapping/graph-summary declares, not an independent review.",
        ],
        metadata={"auto_registered_by": "adapters.fmri_derivatives", "mapping_path": provenance_path},
    )


# ── Phase F: derived-feature transition export ──────────────────────────


def _conservative_transition_limitations() -> list[str]:
    return [
        "Generated from a user-provided derived feature table/graph-summary "
        "+ explicit mapping via adapters.fmri_derivatives -- source_state/"
        "target_state/modality/atlas_or_parcellation/feature definitions "
        "were explicitly declared, never inferred from column names, file "
        "paths, or parcel counts.",
        "This adapter does not run raw BOLD preprocessing, does not execute "
        "fMRIPrep, and does not fit any Nilearn model -- it trusts the "
        "mapping author's provenance, confound policy, and feature "
        "definitions as given.",
        "Atlas/parcellation identity is recorded as provided, not "
        "independently validated as anatomically accurate.",
    ]


def _delta_summary(feature_names: list[str], deltas: dict[str, float]) -> dict[str, Any]:
    # phase_space.estimators._deltas_by_feature expects delta_per_feature
    # as a list positionally aligned with feature_names, not a
    # {feature_name: value} mapping.
    return {"delta_per_feature": [deltas[name] for name in feature_names]}


def export_fmri_derivative_transitions(
    features_path: Path,
    mapping_path: Optional[Path],
    out_dir: Path,
    *,
    registry_path: Optional[Path] = None,
    no_registry: bool = False,
    requested_use: str = "transition_export",
    claim_family: Optional[str] = "fmri_derivatives_transition",
    include_phase_space: bool = False,
    normalization_mode: str = "within_record",
    include_evidence_bundle: bool = False,
    include_report: bool = False,
    updated_registry_out: Optional[Path] = None,
    tool_registry_path: Optional[Path] = None,
    adapter_contracts_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Convert an explicit derived feature table/graph-summary + mapping
    into governed `TransitionRecordV1` artifacts (and, optionally,
    `PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/`EvidenceReportV1`).

    `mapping_path` may be omitted only when `features_path` is a
    self-contained `format="graph_summary"` JSON document (detected via
    `peek_json_format`); otherwise it is required. Fails closed on:
    adapter/tool ineligibility, an invalid mapping, zero valid rows after
    cross-validation, zero valid transition groups, or a denied registry
    use. Individual malformed rows are skipped and reported in the
    returned dict's `errors` list rather than aborting the whole export.
    """
    features_path = Path(features_path)
    mapping_path = Path(mapping_path) if mapping_path is not None else None
    out_dir = Path(out_dir)

    try:
        check_adapter_eligible(tool_registry_path=tool_registry_path, adapter_contracts_path=adapter_contracts_path)
    except AdapterEligibilityError as exc:
        raise AdapterExportError(f"adapter is not eligible to run: {exc}") from exc

    is_graph_summary = peek_json_format(features_path) == "graph_summary"

    cohort_entry: Optional[dict[str, Any]] = None
    if is_graph_summary:
        summary = load_graph_summary(features_path)
        mapping = summary
        subject_long_rows, cohort_entry = expand_graph_summary(summary)
    else:
        if mapping_path is None:
            raise AdapterMappingError(
                "mapping_path is required unless --features is a self-contained format='graph_summary' JSON"
            )
        mapping = load_mapping(mapping_path)
        raw_rows = load_feature_table(features_path)
        if mapping["format"] == "wide":
            raw_rows = normalize_wide_rows(raw_rows, mapping)
        subject_long_rows = raw_rows

    valid_rows: list[dict[str, Any]] = []
    row_errors: list[str] = []
    groups = []
    group_errors: list[str] = []
    if subject_long_rows:
        valid_rows, row_errors = cross_validate_rows(subject_long_rows, mapping)
        groups, group_errors = group_rows(valid_rows) if valid_rows else ([], [])

    if not groups and cohort_entry is None:
        raise AdapterExportError(
            f"no valid subject-level rows or explicit cohort statistics after cross-validation "
            f"({len(row_errors)} row errors, {len(group_errors)} group errors): {(row_errors + group_errors)[:10]}"
        )

    dataset_id = mapping["dataset_id"]

    if registry_path is None and not no_registry:
        raise AdapterRegistryError("registry_path is required unless no_registry=True is explicitly given")

    registry: Optional[BenchmarkRegistry] = None
    registry_decisions: list[dict[str, Any]] = []
    dataset_record_created = False

    if registry_path is not None:
        try:
            registry = BenchmarkRegistry.load(registry_path)
        except RegistryError as exc:
            raise AdapterRegistryError(f"benchmark registry error: {exc}") from exc

        if dataset_id not in registry.datasets:
            candidate = _candidate_dataset_record_from_mapping(
                mapping, features_path=features_path, mapping_path=mapping_path, include_phase_space=include_phase_space,
            )
            registry.datasets[dataset_id] = candidate
            dataset_record_created = True

        try:
            allowed, reason = registry.check_use(dataset_id, requested_use, claim_family=claim_family)
        except RegistryError as exc:
            raise AdapterRegistryError(f"benchmark registry error: {exc}") from exc
        registry_decisions.append(
            {"id": dataset_id, "kind": "dataset", "requested_use": requested_use, "allowed": allowed, "reason": reason}
        )
        if not allowed:
            raise AdapterRegistryError(
                f"benchmark registry denied requested_use={requested_use!r} for dataset='{dataset_id}': {reason}"
            )

    transitions_dir = out_dir / "transitions"
    store = TransitionStore(transitions_dir)
    written_records: list[TransitionRecordV1] = []
    record_errors: list[str] = list(row_errors) + list(group_errors)
    provenance_path = str(mapping_path) if mapping_path is not None else str(features_path)

    for group in groups:
        feature_names = sorted({r["feature_name"] for r in group.rows})
        delta_by_feature = {r["feature_name"]: r["target_value"] - r["source_value"] for r in group.rows}

        statuses = {r["null_control_status"] for r in group.rows}
        if len(statuses) > 1:
            record_errors.append(f"group {group.key}: inconsistent null_control_status {sorted(statuses)}")
            continue
        null_status = statuses.pop() if statuses else "not_provided"

        provenance_values = [r["preprocessing_provenance"] for r in group.rows if r.get("preprocessing_provenance")]
        preprocessing_provenance = provenance_values[0] if provenance_values else {}
        if not isinstance(preprocessing_provenance, dict):
            preprocessing_provenance = {"note": str(preprocessing_provenance)}

        confound_values = [r["confound_policy"] for r in group.rows if r.get("confound_policy")]
        confound_policy = confound_values[0] if confound_values else None
        preprocessing_provenance = dict(preprocessing_provenance)
        if confound_policy:
            preprocessing_provenance["confound_policy"] = confound_policy

        artifact_path_values = sorted({r["artifact_path"] for r in group.rows if r.get("artifact_path")})
        feature_set_id = (
            f"fmri_derivatives::{dataset_id}::{group.atlas_or_parcellation}::{group.modality}::"
            f"{group.source_state}_to_{group.target_state}"
        )

        artifact_paths = {"mapping": provenance_path, "features_table": str(features_path)}
        if len(artifact_path_values) == 1:
            artifact_paths["source_features"] = artifact_path_values[0]

        record = TransitionRecordV1.make(
            dataset_id=group.dataset_id,
            subject_id=group.subject_id,
            session_id=group.session_id,
            record_level="subject",
            modality=group.modality,
            source_state=group.source_state,
            target_state=group.target_state,
            transition_class=f"{group.source_state}_to_{group.target_state}",
            feature_names=feature_names,
            delta_summary=_delta_summary(feature_names, delta_by_feature),
            preprocessing_provenance=preprocessing_provenance,
            null_control_summary={"status": null_status},
            claim_scope="exploratory_metric",
            evidence_level="L2_single_subject_real_signal",
            limitations=_conservative_transition_limitations(),
            artifact_paths=artifact_paths,
            metadata={
                "feature_set_id": feature_set_id,
                "adapter": "adapters.fmri_derivatives",
                "mapping_path": provenance_path,
                "features_path": str(features_path),
                "atlas_or_parcellation": group.atlas_or_parcellation,
                "source_artifact_paths": artifact_path_values,
            },
        )
        record_validation_errors = record.validate()
        if record_validation_errors:
            record_errors.append(f"group {group.key}: record failed validation: {'; '.join(record_validation_errors)}")
            continue
        store.write(record)
        written_records.append(record)

    n_cohort_written = 0
    if cohort_entry is not None:
        feature_names = sorted(cohort_entry["metrics"].keys())
        delta_by_feature = {
            name: values["target_value"] - values["source_value"]
            for name, values in cohort_entry["metrics"].items()
        }
        preprocessing_provenance = dict(cohort_entry.get("preprocessing_provenance") or {})
        if cohort_entry.get("confound_policy"):
            preprocessing_provenance["confound_policy"] = cohort_entry["confound_policy"]
        cohort_feature_set_id = (
            f"fmri_derivatives::{dataset_id}::{cohort_entry['atlas_or_parcellation']}::"
            f"{cohort_entry['modality']}::{cohort_entry['source_state']}_to_{cohort_entry['target_state']}::cohort"
        )
        cohort_record = TransitionRecordV1.make(
            dataset_id=cohort_entry["dataset_id"],
            subject_id=None,
            session_id=None,
            record_level="cohort",
            modality=cohort_entry["modality"],
            source_state=cohort_entry["source_state"],
            target_state=cohort_entry["target_state"],
            transition_class=f"{cohort_entry['source_state']}_to_{cohort_entry['target_state']}",
            feature_names=feature_names,
            delta_summary=_delta_summary(feature_names, delta_by_feature),
            preprocessing_provenance=preprocessing_provenance,
            null_control_summary={"status": cohort_entry.get("null_control_status") or "not_provided"},
            claim_scope="exploratory_metric",
            evidence_level="L4_cross_subject_dataset_specific",
            limitations=_conservative_transition_limitations() + [
                "Cohort-level record: subject_count and per-feature statistics were "
                "explicitly provided in the input graph-summary, never computed by this adapter.",
            ],
            artifact_paths={"mapping": provenance_path, "features_table": str(features_path)},
            metadata={
                "feature_set_id": cohort_feature_set_id,
                "adapter": "adapters.fmri_derivatives",
                "mapping_path": provenance_path,
                "features_path": str(features_path),
                "atlas_or_parcellation": cohort_entry["atlas_or_parcellation"],
                "subject_count": cohort_entry["subject_count"],
            },
        )
        cohort_validation_errors = cohort_record.validate()
        if cohort_validation_errors:
            record_errors.append(f"cohort record failed validation: {'; '.join(cohort_validation_errors)}")
        else:
            store.write(cohort_record)
            written_records.append(cohort_record)
            n_cohort_written = 1

    if not written_records:
        raise AdapterExportError(f"no transition records written ({len(record_errors)} errors): {record_errors[:10]}")

    downstream_registry_work = include_phase_space or include_evidence_bundle
    effective_registry_path = registry_path
    updated_registry_path: Optional[str] = None
    if registry is not None and dataset_record_created:
        if downstream_registry_work and updated_registry_out is None:
            raise AdapterRegistryError(
                f"a new candidate DatasetRecordV1 was registered for dataset_id='{dataset_id}' during this "
                "run; --updated-registry-out is required so downstream phase-space/evidence-bundle "
                "generation can see it (the original --registry file is never mutated in place)"
            )
        if updated_registry_out is not None:
            written = registry.save(updated_registry_out)
            updated_registry_path = str(written)
            effective_registry_path = updated_registry_out

    result: dict[str, Any] = {
        "dataset_id": dataset_id,
        "n_groups": len(groups),
        "n_written": len(written_records) - n_cohort_written,
        "n_cohort_written": n_cohort_written,
        "n_skipped_rows": len(row_errors),
        "errors": record_errors,
        "transitions_dir": str(transitions_dir),
        "records": written_records,
        "registry_decisions": registry_decisions,
        "dataset_record_created": dataset_record_created,
        "updated_registry_path": updated_registry_path,
        "phase_space": None,
        "evidence_bundle": None,
        "report": None,
    }

    if include_evidence_bundle:
        from evidence.builder import BuildError as GenericBuildError
        from evidence.builder import build_generic_evidence_bundle

        single_group_label = None
        if groups and len(groups) == 1 and cohort_entry is None:
            single_group_label = f"{groups[0].source_state}_to_{groups[0].target_state}"
        feature_set_label = single_group_label or "fmri_derivatives"
        try:
            bundle = build_generic_evidence_bundle(
                dataset_id=dataset_id,
                feature_set=feature_set_label,
                modality=mapping["modality"],
                transitions_dir=transitions_dir,
                out=out_dir,
                registry=registry,
                registry_path=effective_registry_path,
                requested_use=requested_use,
                claim_family=claim_family,
                include_phase_space=include_phase_space,
                normalization_mode=normalization_mode,
                no_registry=no_registry,
                include_report=include_report,
                source_artifact_path=str(features_path),
                extra_limitations=[
                    "Built via adapters.fmri_derivatives.export_fmri_derivative_transitions "
                    "-- consumes user-provided derived features/fMRIPrep-style metadata only, "
                    "not raw BOLD signal.",
                ],
            )
        except GenericBuildError as exc:
            raise AdapterExportError(f"evidence bundle build failed: {exc}") from exc
        result["evidence_bundle"] = bundle
        result["phase_space"] = {"status": bundle.metadata.get("phase_space_status")} if include_phase_space else None
        result["report"] = bundle.metadata.get("report") if include_report else None
    elif include_phase_space:
        from phase_space.export_from_transitions import ExportError as PhaseSpaceExportError
        from phase_space.export_from_transitions import export as export_phase_space

        try:
            ps_result = export_phase_space(
                transitions_dir, out_dir / "phase_space",
                normalization_mode=normalization_mode,
                registry_path=effective_registry_path, requested_use="phase_space_export", claim_family=claim_family,
                mark_seen=False,
            )
        except PhaseSpaceExportError as exc:
            raise AdapterExportError(f"phase-space export failed: {exc}") from exc
        result["phase_space"] = {
            "n_coordinates": ps_result["n_coordinates"],
            "n_estimated": ps_result["n_estimated"],
            "n_failed_validation": ps_result["n_failed_validation"],
        }

    return result


# ── CLI ──────────────────────────────────────────────────────────────────


def _dataset_record_summary(record: DatasetRecordV1) -> dict[str, Any]:
    return {
        "dataset_id": record.dataset_id, "display_name": record.display_name,
        "modalities": record.modalities, "current_role": record.current_role,
        "allowed_uses": record.allowed_uses, "evidence_level_ceiling": record.evidence_level_ceiling,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--features", type=Path, default=None, help="derived feature table or graph-summary JSON")
    parser.add_argument("--mapping", type=Path, default=None, help="explicit mapping JSON (omit only for a self-contained graph_summary --features file)")
    parser.add_argument("--out", type=Path, default=None, help="output directory (required with --features)")
    parser.add_argument("--scan-derivatives", type=Path, default=None, help="local fMRIPrep-style derivatives root to scan (metadata only)")
    parser.add_argument("--write-dataset-records", type=Path, default=None, help="write --scan-derivatives results as JSON here")
    parser.add_argument("--registry", type=Path, default=None, help="benchmarks.export_registry.BenchmarkRegistry JSON path")
    parser.add_argument("--no-registry", action="store_true", help="explicit legacy mode: export without registry authorization")
    parser.add_argument("--requested-use", default="transition_export")
    parser.add_argument("--claim-family", default="fmri_derivatives_transition")
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--normalization-mode", default="within_record")
    parser.add_argument("--include-evidence-bundle", action="store_true")
    parser.add_argument("--include-report", action="store_true")
    parser.add_argument("--updated-registry-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.scan_derivatives and not args.features:
        print("[adapters.fmri_derivatives] FAILED: one of --scan-derivatives or --features is required")
        return 1

    if args.scan_derivatives:
        try:
            summary = scan_fmri_derivatives_metadata(args.scan_derivatives)
        except AdapterDataError as exc:
            print(f"[adapters.fmri_derivatives] FAILED: {exc}")
            return 1
        dataset_record = make_dataset_record_from_fmri_derivatives(summary, mapping_provided=bool(args.mapping or args.features))
        artifact_records = make_artifact_records_from_fmri_derivatives(summary)
        scan_summary = {
            "dataset_id": summary.dataset_id, "derivatives_root": summary.derivatives_root,
            "n_subjects": summary.n_subjects, "n_confounds_files": len(summary.confounds_files),
            "n_derivative_metadata_files": len(summary.derivative_metadata_files),
            "modalities_declared": summary.modalities_declared,
            "dataset_record": _dataset_record_summary(dataset_record),
            "n_artifact_records": len(artifact_records),
        }
        print(json.dumps(scan_summary, indent=2))
        if args.write_dataset_records:
            payload = {
                "dataset_record": dataset_record.to_dict(),
                "artifact_records": [r.to_dict() for r in artifact_records],
            }
            args.write_dataset_records.parent.mkdir(parents=True, exist_ok=True)
            args.write_dataset_records.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"[adapters.fmri_derivatives] wrote dataset/artifact records: {args.write_dataset_records}")
        if not args.features:
            return 0

    if not args.features:
        return 0

    if not args.out:
        print("[adapters.fmri_derivatives] FAILED: --features requires --out")
        return 1

    try:
        result = export_fmri_derivative_transitions(
            args.features, args.mapping, args.out,
            registry_path=args.registry, no_registry=args.no_registry,
            requested_use=args.requested_use, claim_family=args.claim_family,
            include_phase_space=args.include_phase_space, normalization_mode=args.normalization_mode,
            include_evidence_bundle=args.include_evidence_bundle, include_report=args.include_report,
            updated_registry_out=args.updated_registry_out,
        )
    except (AdapterEligibilityError, AdapterMappingError, AdapterDataError, AdapterExportError, AdapterRegistryError) as exc:
        print(f"[adapters.fmri_derivatives] FAILED: {exc}")
        return 1

    atlas_summary = sorted({
        r.metadata.get("atlas_or_parcellation") for r in result["records"] if r.metadata.get("atlas_or_parcellation")
    })

    summary_out: dict[str, Any] = {
        "dataset_id": result["dataset_id"],
        "n_groups_parsed": result["n_groups"],
        "n_transitions_written": result["n_written"],
        "n_cohort_records_written": result["n_cohort_written"],
        "n_skipped_rows": result["n_skipped_rows"],
        "n_errors": len(result["errors"]),
        "errors": result["errors"][:20],
        "transitions_dir": result["transitions_dir"],
        "registry_decisions": result["registry_decisions"],
        "dataset_record_created": result["dataset_record_created"],
        "updated_registry_path": result["updated_registry_path"],
        "atlas_or_parcellation": atlas_summary,
        "limitations_count": sum(len(r.limitations) for r in result["records"]),
    }
    if result["phase_space"] is not None:
        summary_out["phase_space"] = result["phase_space"]
    if result["evidence_bundle"] is not None:
        bundle = result["evidence_bundle"]
        summary_out["evidence_bundle"] = {
            "bundle_id": bundle.bundle_id,
            "claim_scope_ceiling": bundle.claim_scope_ceiling,
            "evidence_level_ceiling": bundle.evidence_level_ceiling,
            "generated_claim_scope": bundle.generated_claim_scope,
        }
    elif args.include_evidence_bundle:
        summary_out["evidence_bundle"] = "not built (see errors)"
    if result["report"] is not None:
        summary_out["report"] = result["report"]
    elif args.include_report:
        summary_out["report"] = "not built (requires --include-evidence-bundle)"

    print(json.dumps(summary_out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
