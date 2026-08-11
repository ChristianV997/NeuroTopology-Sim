"""MNE/BIDS Derived Feature Adapter v1.

Usage::

    # BIDS metadata scan only (no transitions)
    python -m adapters.mne_bids --scan-bids /path/to/bids_root \\
        --write-dataset-records outputs/adapters/mne_bids/bids_scan.json

    # derived-feature export -> TransitionRecordV1 (+ optional phase-space/
    # evidence-bundle/report)
    python -m adapters.mne_bids \\
        --features derived_features.csv --mapping mapping.json \\
        --out outputs/adapters/mne_bids/my_export \\
        --registry benchmarks/registry_seed.json \\
        --requested-use transition_export

This adapter does not run raw EEG/MEG/iEEG/fNIRS preprocessing. It reads
lightweight BIDS metadata (`dataset_description.json`, `participants.tsv`,
`*_events.tsv`) and/or an explicit, user-provided derived feature table +
mapping, then produces governed `DatasetRecordV1`/`ArtifactRecordV1`/
`TransitionRecordV1` (and, optionally, `PhaseSpaceCoordinateV1`/
`EvidenceBundleV1`/`EvidenceReportV1`) artifacts. See
docs/mne_bids_adapter.md for the full input schema and design rationale.

This is the package's only CLI entry point; `adapters.validation`,
`adapters.mne_bids_features`, and `adapters.mne_bids_contract` are
library-only, matching `benchmarks.dataset_registry`/`transitions.record`'s
precedent of having no CLI of their own.
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

from adapters.mne_bids_contract import AdapterEligibilityError, check_adapter_eligible  # noqa: E402
from adapters.mne_bids_features import (  # noqa: E402
    AdapterDataError,
    cross_validate_rows,
    group_rows,
    load_feature_table,
    load_mapping,
    normalize_wide_rows,
)
from adapters.validation import AdapterMappingError  # noqa: E402

_FORBIDDEN_USES: list[str] = [
    "clinical_claim", "diagnostic_claim", "treatment_claim",
    "consciousness_biomarker_claim", "spiritual_attainment_claim",
    "mechanistic_causal_claim", "final_claim_confirmation",
    "cross_dataset_replication_claim", "prospective_prediction_claim",
]

_BIDS_MODALITY_DIRS: dict[str, str] = {"eeg": "EEG", "meg": "MEG", "ieeg": "iEEG", "nirs": "fNIRS"}


class AdapterExportError(ValueError):
    """Raised when the derived-feature export cannot proceed, or produces
    zero valid transition records."""


class AdapterRegistryError(ValueError):
    """Raised when the benchmark registry denies the requested use, or
    registry context is missing without an explicit no_registry override."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "unknown"


# ── Phase D: BIDS metadata scan ─────────────────────────────────────────


@dataclass
class BidsMetadataSummary:
    bids_root: str
    dataset_id: str
    dataset_description: Optional[dict[str, Any]]
    participants: list[dict[str, Any]] = field(default_factory=list)
    n_subjects: int = 0
    events_files: list[str] = field(default_factory=list)
    derivative_metadata_files: list[str] = field(default_factory=list)
    modalities_declared: list[str] = field(default_factory=list)


def scan_bids_metadata(bids_root: Path) -> BidsMetadataSummary:
    """Read cheap BIDS metadata (JSON/TSV file presence and content, plus
    standardized modality-subdirectory names) -- never opens, parses, or
    reads any raw signal file."""
    bids_root = Path(bids_root)
    if not bids_root.exists() or not bids_root.is_dir():
        raise AdapterDataError(f"bids_root does not exist or is not a directory: {bids_root}")

    dd_path = bids_root / "dataset_description.json"
    dataset_description: Optional[dict[str, Any]] = None
    if dd_path.exists():
        try:
            dataset_description = json.loads(dd_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterDataError(f"dataset_description.json is not valid JSON: {dd_path} ({exc})") from exc

    participants_path = bids_root / "participants.tsv"
    participants: list[dict[str, Any]] = []
    if participants_path.exists():
        with participants_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            participants = [dict(row) for row in reader]

    events_files = sorted(str(p.relative_to(bids_root)) for p in bids_root.rglob("*_events.tsv"))

    derivatives_dir = bids_root / "derivatives"
    derivative_metadata_files = (
        sorted(str(p.relative_to(bids_root)) for p in derivatives_dir.rglob("*.json"))
        if derivatives_dir.exists() else []
    )

    modalities_declared = sorted({
        _BIDS_MODALITY_DIRS[d.name] for d in bids_root.rglob("*") if d.is_dir() and d.name in _BIDS_MODALITY_DIRS
    })
    if not modalities_declared:
        modalities_declared = ["unknown"]

    if dataset_description and dataset_description.get("Name"):
        dataset_id = _slugify(str(dataset_description["Name"]))
    else:
        dataset_id = _slugify(bids_root.name)

    return BidsMetadataSummary(
        bids_root=str(bids_root),
        dataset_id=dataset_id,
        dataset_description=dataset_description,
        participants=participants,
        n_subjects=len(participants),
        events_files=events_files,
        derivative_metadata_files=derivative_metadata_files,
        modalities_declared=modalities_declared,
    )


def make_dataset_record_from_bids(summary: BidsMetadataSummary, *, mapping_provided: bool = False) -> DatasetRecordV1:
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
        f"BIDS metadata scan via adapters.mne_bids.scan_bids_metadata over '{summary.bids_root}': "
        f"dataset_description.json {'found' if summary.dataset_description else 'not found'}; "
        f"participants.tsv {'found (' + str(summary.n_subjects) + ' rows)' if summary.participants else 'not found'}; "
        f"{len(summary.events_files)} *_events.tsv file(s); "
        f"{len(summary.derivative_metadata_files)} derivative metadata file(s)."
    )

    limitations = [
        "This DatasetRecordV1 was generated by a lightweight BIDS metadata "
        "scan (dataset_description.json/participants.tsv/*_events.tsv file "
        "presence and content, plus standardized BIDS modality-subdirectory "
        "names) -- it does not validate, parse, or analyze any scientific "
        "feature or raw signal, and does not confirm transition semantics "
        "for any subject.",
        "modalities_declared reflects only the presence of BIDS-standard "
        "modality subdirectories (eeg/, meg/, ieeg/, nirs/) on disk, not "
        "any inspection of signal content.",
    ]
    if not mapping_provided:
        limitations.append(
            "No derived-feature mapping accompanied this scan -- "
            "'transition_export' is deliberately excluded from allowed_uses "
            "until an explicit mapping is provided to "
            "adapters.mne_bids.export_mne_bids_derived_transitions."
        )

    return DatasetRecordV1.make(
        dataset_id=summary.dataset_id,
        display_name=str(display_name),
        modalities=list(summary.modalities_declared),
        artifact_paths=[summary.bids_root],
        artifact_kinds=["bids_dataset_scan"],
        current_role="exploration",
        allowed_uses=allowed_uses,
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling=("L2_single_subject_real_signal" if mapping_provided else "L0_computational_artifact"),
        label_quality="unvalidated_bids_metadata_scan",
        provenance=provenance,
        limitations=limitations,
        metadata={"bids_scan": True, "mapping_provided": mapping_provided, "adapter": "adapters.mne_bids"},
    )


def make_artifact_records_from_bids(summary: BidsMetadataSummary) -> list[ArtifactRecordV1]:
    """One ArtifactRecordV1 per notable BIDS metadata file found -- always
    `external=True` (the scanned BIDS root is a user's local directory, not
    a path inside this repository)."""
    common = dict(
        dataset_id=summary.dataset_id,
        record_kind="committed_artifact",
        external=True,
        current_role="exploration",
        allowed_uses=["documentation", "feature_design"],
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        produced_by="adapters.mne_bids.scan_bids_metadata",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        limitations=["BIDS metadata file presence/content only -- not scientifically validated by this scan."],
    )

    records: list[ArtifactRecordV1] = []
    root = Path(summary.bids_root)

    if summary.dataset_description is not None:
        records.append(ArtifactRecordV1.make(
            path=str(root / "dataset_description.json"), artifact_kind="bids_dataset_description", **common,
        ))
    if summary.participants:
        records.append(ArtifactRecordV1.make(
            path=str(root / "participants.tsv"), artifact_kind="bids_participants_tsv", **common,
        ))
    for rel in summary.events_files:
        records.append(ArtifactRecordV1.make(
            path=str(root / rel), artifact_kind="bids_events_tsv", **common,
        ))
    for rel in summary.derivative_metadata_files:
        records.append(ArtifactRecordV1.make(
            path=str(root / rel), artifact_kind="bids_derivative_metadata", **common,
        ))
    return records


def _candidate_dataset_record_from_mapping(
    mapping: dict[str, Any], *, features_path: Path, mapping_path: Path, include_phase_space: bool = False,
) -> DatasetRecordV1:
    """Conservative candidate DatasetRecordV1 for a dataset_id that is not
    yet in the loaded registry, built from an explicit mapping (not a BIDS
    scan) -- 'transition_export' is included because a valid mapping
    already exists by the time this is called; 'phase_space_export' is
    included only when the caller actually requested phase-space output
    for this run, mirroring how existing seed registry entries only ever
    declare the uses their own pipelines actually exercise."""
    allowed_uses = ["documentation", "feature_design", "transition_export"]
    if include_phase_space:
        allowed_uses.append("phase_space_export")
    return DatasetRecordV1.make(
        dataset_id=mapping["dataset_id"],
        display_name=mapping["dataset_id"],
        modalities=[mapping["modality"]],
        artifact_paths=[str(features_path), str(mapping_path)],
        artifact_kinds=["mne_bids_derived_feature_table"],
        current_role="exploration",
        allowed_uses=allowed_uses,
        forbidden_uses=list(_FORBIDDEN_USES),
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L2_single_subject_real_signal",
        label_quality="explicit_user_provided_mapping",
        provenance=(
            f"Auto-registered by adapters.mne_bids.export_mne_bids_derived_transitions "
            f"from an explicit mapping ('{mapping_path}') and derived feature table "
            f"('{features_path}') -- no prior registry entry existed for dataset_id="
            f"'{mapping['dataset_id']}'."
        ),
        limitations=[
            "This DatasetRecordV1 was auto-generated because no prior registry "
            "entry existed for this dataset_id -- it reflects only what the "
            "supplied mapping declares, not an independent review.",
        ],
        metadata={"auto_registered_by": "adapters.mne_bids", "mapping_path": str(mapping_path)},
    )


# ── Phase E: derived-feature transition export ──────────────────────────


def _conservative_transition_limitations() -> list[str]:
    return [
        "Generated from a user-provided derived feature table + explicit "
        "mapping via adapters.mne_bids -- source_state/target_state/"
        "modality/feature definitions were explicitly declared by the "
        "mapping author, never inferred from column names or file paths.",
        "This adapter does not run raw EEG/MEG/iEEG/fNIRS preprocessing and "
        "does not independently verify the correctness of the supplied "
        "feature values -- it trusts the mapping author's provenance and "
        "definitions as given.",
        "Subject-level record only (record_level='subject') -- no "
        "cohort-level statistics are computed or claimed by this adapter.",
    ]


def export_mne_bids_derived_transitions(
    features_path: Path,
    mapping_path: Path,
    out_dir: Path,
    *,
    registry_path: Optional[Path] = None,
    no_registry: bool = False,
    requested_use: str = "transition_export",
    claim_family: Optional[str] = "mne_bids_derived_transition",
    include_phase_space: bool = False,
    normalization_mode: str = "within_record",
    include_evidence_bundle: bool = False,
    include_report: bool = False,
    updated_registry_out: Optional[Path] = None,
    tool_registry_path: Optional[Path] = None,
    adapter_contracts_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Convert an explicit derived feature table + mapping into governed
    `TransitionRecordV1` artifacts (and, optionally,
    `PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/`EvidenceReportV1`).

    Fails closed (raises before writing anything) on: adapter/tool
    ineligibility, an invalid mapping, zero valid rows after
    cross-validation, zero valid transition groups, or a denied registry
    use. Individual malformed rows are skipped and reported in the
    returned dict's `errors` list rather than aborting the whole export.
    """
    features_path = Path(features_path)
    mapping_path = Path(mapping_path)
    out_dir = Path(out_dir)

    try:
        check_adapter_eligible(tool_registry_path=tool_registry_path, adapter_contracts_path=adapter_contracts_path)
    except AdapterEligibilityError as exc:
        raise AdapterExportError(f"adapter is not eligible to run: {exc}") from exc

    mapping = load_mapping(mapping_path)  # raises AdapterMappingError, fails closed

    raw_rows = load_feature_table(features_path)
    if mapping["format"] == "wide":
        raw_rows = normalize_wide_rows(raw_rows, mapping)

    valid_rows, row_errors = cross_validate_rows(raw_rows, mapping)
    if not valid_rows:
        raise AdapterExportError(f"no valid rows after cross-validation ({len(row_errors)} errors): {row_errors[:10]}")

    groups, group_errors = group_rows(valid_rows)
    if not groups:
        raise AdapterExportError(
            f"no valid transition groups after grouping ({len(group_errors)} errors): {group_errors[:10]}"
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

    for group in groups:
        feature_names = sorted({r["feature_name"] for r in group.rows})
        delta_by_feature = {r["feature_name"]: r["target_value"] - r["source_value"] for r in group.rows}
        # phase_space.estimators._deltas_by_feature expects delta_per_feature
        # as a list positionally aligned with feature_names, not a
        # {feature_name: value} mapping -- see phase_space/estimators.py.
        delta_summary = {"delta_per_feature": [delta_by_feature[name] for name in feature_names]}

        statuses = {r["null_control_status"] for r in group.rows}
        if len(statuses) > 1:
            record_errors.append(f"group {group.key}: inconsistent null_control_status {sorted(statuses)}")
            continue
        null_status = statuses.pop() if statuses else "not_provided"

        provenance_values = [r["preprocessing_provenance"] for r in group.rows if r.get("preprocessing_provenance")]
        preprocessing_provenance = provenance_values[0] if provenance_values else {}
        if not isinstance(preprocessing_provenance, dict):
            preprocessing_provenance = {"note": str(preprocessing_provenance)}

        artifact_path_values = sorted({r["artifact_path"] for r in group.rows if r.get("artifact_path")})
        feature_set_id = f"mne_bids_derived::{dataset_id}::{group.modality}::{group.source_state}_to_{group.target_state}"

        artifact_paths = {"mapping": str(mapping_path), "features_table": str(features_path)}
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
            delta_summary=delta_summary,
            preprocessing_provenance=preprocessing_provenance,
            null_control_summary={"status": null_status},
            claim_scope="exploratory_metric",
            evidence_level="L2_single_subject_real_signal",
            limitations=_conservative_transition_limitations(),
            artifact_paths=artifact_paths,
            metadata={
                "feature_set_id": feature_set_id,
                "adapter": "adapters.mne_bids",
                "mapping_path": str(mapping_path),
                "features_path": str(features_path),
                "source_artifact_paths": artifact_path_values,
            },
        )
        record_validation_errors = record.validate()
        if record_validation_errors:
            record_errors.append(f"group {group.key}: record failed validation: {'; '.join(record_validation_errors)}")
            continue
        store.write(record)
        written_records.append(record)

    if not written_records:
        raise AdapterExportError(f"no transition records written ({len(record_errors)} errors): {record_errors[:10]}")

    # phase_space.export_from_transitions.export() (and, transitively,
    # build_generic_evidence_bundle's own phase-space step) always reloads
    # the registry fresh from disk -- neither accepts an in-memory
    # BenchmarkRegistry object. So if a brand-new candidate DatasetRecordV1
    # was just registered in-memory (dataset_record_created=True) and
    # downstream phase-space/evidence-bundle work is requested, that
    # candidate MUST be persisted first (to updated_registry_out, never to
    # registry_path itself) and that path used for every downstream
    # registry-aware call -- otherwise the candidate would appear
    # unregistered again the moment anything re-reads the registry from
    # disk. Fails closed rather than silently falling back to registry_path.
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
        "n_written": len(written_records),
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

        single_group = groups[0] if len(groups) == 1 else None
        feature_set_label = (
            f"{single_group.source_state}_to_{single_group.target_state}" if single_group else "mne_bids_derived"
        )
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
                    "Built via adapters.mne_bids.export_mne_bids_derived_transitions "
                    "-- consumes user-provided derived features/BIDS metadata only, "
                    "not raw EEG/MEG/iEEG/fNIRS signal.",
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
    parser.add_argument("--features", type=Path, default=None, help="derived feature table (CSV or JSON)")
    parser.add_argument("--mapping", type=Path, default=None, help="explicit mapping JSON (required with --features)")
    parser.add_argument("--out", type=Path, default=None, help="output directory (required with --features)")
    parser.add_argument("--scan-bids", type=Path, default=None, help="local BIDS root directory to scan (metadata only)")
    parser.add_argument("--write-dataset-records", type=Path, default=None, help="write --scan-bids results as JSON here")
    parser.add_argument("--registry", type=Path, default=None, help="benchmarks.export_registry.BenchmarkRegistry JSON path")
    parser.add_argument("--no-registry", action="store_true", help="explicit legacy mode: export without registry authorization")
    parser.add_argument("--requested-use", default="transition_export")
    parser.add_argument("--claim-family", default="mne_bids_derived_transition")
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--normalization-mode", default="within_record")
    parser.add_argument("--include-evidence-bundle", action="store_true")
    parser.add_argument("--include-report", action="store_true")
    parser.add_argument("--updated-registry-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.scan_bids and not args.features:
        print("[adapters.mne_bids] FAILED: one of --scan-bids or --features is required")
        return 1

    if args.scan_bids:
        try:
            summary = scan_bids_metadata(args.scan_bids)
        except AdapterDataError as exc:
            print(f"[adapters.mne_bids] FAILED: {exc}")
            return 1
        dataset_record = make_dataset_record_from_bids(summary, mapping_provided=bool(args.mapping))
        artifact_records = make_artifact_records_from_bids(summary)
        scan_summary = {
            "bids_root": summary.bids_root, "dataset_id": summary.dataset_id,
            "n_subjects": summary.n_subjects, "n_events_files": len(summary.events_files),
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
            print(f"[adapters.mne_bids] wrote dataset/artifact records: {args.write_dataset_records}")
        if not args.features:
            return 0

    if not args.features:
        return 0

    if not args.mapping or not args.out:
        print("[adapters.mne_bids] FAILED: --features requires --mapping and --out")
        return 1

    try:
        result = export_mne_bids_derived_transitions(
            args.features, args.mapping, args.out,
            registry_path=args.registry, no_registry=args.no_registry,
            requested_use=args.requested_use, claim_family=args.claim_family,
            include_phase_space=args.include_phase_space, normalization_mode=args.normalization_mode,
            include_evidence_bundle=args.include_evidence_bundle, include_report=args.include_report,
            updated_registry_out=args.updated_registry_out,
        )
    except (AdapterEligibilityError, AdapterMappingError, AdapterDataError, AdapterExportError, AdapterRegistryError) as exc:
        print(f"[adapters.mne_bids] FAILED: {exc}")
        return 1

    summary_out: dict[str, Any] = {
        "dataset_id": result["dataset_id"],
        "n_groups_parsed": result["n_groups"],
        "n_transitions_written": result["n_written"],
        "n_skipped_rows": result["n_skipped_rows"],
        "n_errors": len(result["errors"]),
        "errors": result["errors"][:20],
        "transitions_dir": result["transitions_dir"],
        "registry_decisions": result["registry_decisions"],
        "dataset_record_created": result["dataset_record_created"],
        "updated_registry_path": result["updated_registry_path"],
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
