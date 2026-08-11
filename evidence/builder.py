"""Orchestrates existing exporters into one `EvidenceBundleV1`.

Does not duplicate transition/phase-space exporter logic: it imports and
calls the library `export()` functions already exposed by
`tools.export_ds005620_pitnn_transitions`, `tools.export_ds000245_fmri_transitions`,
and `phase_space.export_from_transitions` (all already importable -- `tools/`
and `phase_space/` are real packages with `__init__.py`, and the exporter
tests already import these functions the same way). This module contains no
raw EEG/fMRI pipeline code and reads only already-committed artifacts via
those exporters.

Dataset/feature-set dispatch is intentionally a simple lookup table, not a
plugin system -- see `DISPATCH` below. Extending to a new dataset/feature
set means adding one entry, not writing a new abstraction.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.export_registry import BenchmarkRegistry, RegistryError  # noqa: E402
from evidence.bundle import EvidenceBundleV1  # noqa: E402
from evidence.store import EvidenceBundleStore  # noqa: E402
from evidence.validation import EVIDENCE_LEVEL_ORDER  # noqa: E402
from phase_space.coordinate import CLAIM_SCOPE_ORDER, PHASE_SPACE_MAX_CLAIM_SCOPE  # noqa: E402
from phase_space.export_from_transitions import ExportError as PhaseSpaceExportError  # noqa: E402
from phase_space.export_from_transitions import export as export_phase_space  # noqa: E402
from phase_space.store import PhaseSpaceStore  # noqa: E402
from transitions.store import RECORD_FILENAME  # noqa: E402
from tools.export_ds000245_fmri_transitions import ExportError as DS000245ExportError  # noqa: E402
from tools.export_ds000245_fmri_transitions import export as export_ds000245  # noqa: E402
from tools.export_ds005620_pitnn_transitions import ExportError as DS005620ExportError  # noqa: E402
from tools.export_ds005620_pitnn_transitions import TransitionValidationError  # noqa: E402
from tools.export_ds005620_pitnn_transitions import export as export_ds005620  # noqa: E402

# (dataset, feature_set) -> which exporter to call and how. `artifact_kind`
# must match benchmarks/registry_seed.json's ArtifactRecordV1.artifact_kind
# for the same feature family, so the builder can resolve a registry
# artifact_id (best-effort; a missing match is not fatal, only the
# dataset-level check is required).
DISPATCH: dict[tuple[str, str], dict[str, Any]] = {
    ("ds005620", "cohort_summary"): {
        "modality": "EEG",
        "artifact_kind": "pitnn_cohort_summary",
        "default_source": "contracts/btc_icft/ds005620/pitnn_cohort",
    },
    ("ds005620", "spatial_defect_map"): {
        "modality": "EEG",
        "artifact_kind": "spatial_defect_map",
        "default_source": "contracts/btc_icft/ds005620/pitnn_cohort",
    },
    ("ds000245", "schaefer100_motcorr"): {
        "modality": "fMRI",
        "artifact_kind": "fmri_graph_cohort_result_schaefer100_motcorr",
        "default_source": "contracts/fmri_tda/ds000245",
    },
    ("ds000245", "kmeans100"): {
        "modality": "fMRI",
        "artifact_kind": "fmri_graph_cohort_result_kmeans100",
        "default_source": "contracts/fmri_tda/ds000245",
    },
}


class BuildError(ValueError):
    """Raised when an evidence bundle cannot be built."""


def _git_commit(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _claim_scope_rank(scope: str) -> int:
    return CLAIM_SCOPE_ORDER.index(scope) if scope in CLAIM_SCOPE_ORDER else 0


def _aggregate_null_control(records: list[Any]) -> dict[str, Any]:
    """Honestly roll up per-record null_control_summary.status into one
    bundle-level status. Never reports 'passed' unless at least one real
    per-record status is 'passed'; never silently converts an all-absent
    set of per-record statuses into anything other than 'not_provided'."""
    per_transition = {r.transition_id: (r.null_control_summary or {}).get("status", "not_provided") for r in records}
    statuses = set(per_transition.values())
    if "passed" in statuses:
        status = "passed"
    elif "failed" in statuses:
        status = "failed"
    elif statuses == {"not_provided"}:
        status = "not_provided"
    elif statuses == {"not_applicable"}:
        status = "not_applicable"
    elif statuses <= {"not_provided", "not_applicable"}:
        status = "not_provided"
    else:
        status = "mixed"
    return {
        "status": status,
        "per_transition": per_transition,
        "note": (
            "Aggregated from each generated TransitionRecordV1's own "
            "null_control_summary.status; 'passed' requires at least one "
            "real per-transition 'passed' entry, never fabricated."
        ),
    }


def _flatten_transition_records(dataset: str, result: dict[str, Any]) -> list[Any]:
    if dataset == "ds005620":
        records = list(result.get("subject_records") or [])
        if result.get("cohort_record") is not None:
            records.append(result["cohort_record"])
        return records
    return list(result.get("records") or [])


def _base_limitations(dataset: str, feature_set: str) -> list[str]:
    return [
        "This is a governed evidence bundle: a reproducible artifact manifest "
        "linking a registry use decision to the TransitionRecordV1/"
        "PhaseSpaceCoordinateV1 artifacts it authorized -- it is NOT itself a "
        "theory result, and asserts nothing beyond what those underlying "
        "artifacts already state.",
        f"Source dataset '{dataset}', feature_set '{feature_set}'; every "
        "TransitionRecordV1/PhaseSpaceCoordinateV1 referenced here carries "
        "its own independent limitations, which this bundle does not "
        "repeat in full -- read the referenced artifacts directly for "
        "feature-specific caveats.",
        "Not a clinical, diagnostic, or psychiatric-state measure; does not "
        "validate treatment response, mechanistic causality, or "
        "spiritual/meditative attainment.",
        "claim_scope_ceiling/evidence_level_ceiling reflect the weakest "
        "applicable ceiling across the registry dataset record and (if "
        "included) the phase-space layer's own hard cap; generated_claim_scope "
        "and generated_evidence_levels are the weakest/actual values observed "
        "across the artifacts this bundle references, never promoted.",
    ]


def build_evidence_bundle(
    *,
    dataset: str,
    feature_set: str,
    source: Path,
    out: Path,
    registry_path: Optional[Path] = None,
    requested_use: str = "transition_export",
    claim_family: Optional[str] = None,
    include_phase_space: bool = False,
    normalization_mode: str = "within_record",
    mark_seen: bool = False,
    seen_by: str = "exploration",
    updated_registry_out: Optional[Path] = None,
    no_registry: bool = False,
    include_report: bool = False,
    report_out: Optional[Path] = None,
) -> EvidenceBundleV1:
    key = (dataset, feature_set)
    if key not in DISPATCH:
        raise BuildError(
            f"unsupported (dataset, feature_set) combination {key!r}; choose one of "
            f"{sorted(DISPATCH)}"
        )
    spec = DISPATCH[key]

    if registry_path is None and not no_registry:
        raise BuildError(
            "registry_path is required unless --no-registry is explicitly given "
            "(legacy mode; validation fails closed on missing registry context otherwise)"
        )
    if mark_seen and registry_path is None:
        raise BuildError("mark_seen=True requires registry_path")
    if mark_seen and updated_registry_out is None:
        raise BuildError("mark_seen=True requires updated_registry_out (never mutates registry_path in place)")

    registry = None
    registry_decisions: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    # No registry means no *additional* registry-derived constraint to
    # apply -- default to the widest allowed ceiling (narrowed below only
    # by phase-space's own hard cap when --include-phase-space is used),
    # not the narrowest. A narrowest-first default would make --no-registry
    # unusable, since the exporters legitimately produce exploratory_metric/
    # L2-L4 records regardless of registry involvement.
    claim_scope_ceiling = CLAIM_SCOPE_ORDER[-1]
    evidence_level_ceiling = EVIDENCE_LEVEL_ORDER[-1]

    if registry_path is not None:
        try:
            registry = BenchmarkRegistry.load(registry_path)
        except RegistryError as exc:
            raise BuildError(f"benchmark registry error: {exc}") from exc

        try:
            allowed, reason = registry.check_use(dataset, requested_use, claim_family=claim_family)
        except RegistryError as exc:
            raise BuildError(f"benchmark registry error: {exc}") from exc
        registry_decisions.append(
            {"id": dataset, "kind": "dataset", "requested_use": requested_use, "allowed": allowed, "reason": reason}
        )
        if not allowed:
            raise BuildError(f"benchmark registry denied requested_use={requested_use!r} for dataset='{dataset}': {reason}")

        dataset_record = registry.datasets.get(dataset)
        if dataset_record is not None:
            claim_scope_ceiling = dataset_record.claim_scope_ceiling
            evidence_level_ceiling = dataset_record.evidence_level_ceiling

        for artifact_id, artifact_record in registry.artifacts.items():
            if artifact_record.dataset_id == dataset and artifact_record.artifact_kind == spec["artifact_kind"]:
                artifact_ids.append(artifact_id)
                try:
                    a_allowed, a_reason = registry.check_use(artifact_id, requested_use, claim_family=claim_family)
                except RegistryError as exc:
                    raise BuildError(f"benchmark registry error for artifact {artifact_id!r}: {exc}") from exc
                registry_decisions.append(
                    {"id": artifact_id, "kind": "artifact", "requested_use": requested_use, "allowed": a_allowed, "reason": a_reason}
                )
                if not a_allowed:
                    raise BuildError(
                        f"benchmark registry denied requested_use={requested_use!r} for "
                        f"artifact='{artifact_id}' ({spec['artifact_kind']}): {a_reason}"
                    )

    store = EvidenceBundleStore(out)
    transitions_dir = store.transitions_dir
    phase_space_dir = store.phase_space_dir

    try:
        if dataset == "ds005620":
            tx_result = export_ds005620(
                Path(source), transitions_dir, feature_set=feature_set,
                registry_path=registry_path, requested_use=requested_use, claim_family=claim_family,
            )
        elif dataset == "ds000245":
            tx_result = export_ds000245(
                Path(source), transitions_dir, variant=feature_set,
                registry_path=registry_path, requested_use=requested_use, claim_family=claim_family,
            )
        else:  # pragma: no cover - guarded by DISPATCH membership above
            raise BuildError(f"no exporter wired for dataset={dataset!r}")
    except (DS005620ExportError, DS000245ExportError, TransitionValidationError) as exc:
        raise BuildError(f"transition export failed: {exc}") from exc

    records = _flatten_transition_records(dataset, tx_result)
    if not records:
        raise BuildError(f"transition export for {key!r} produced zero records")

    transition_record_ids = [r.transition_id for r in records]
    transition_record_paths = [
        _relative_path(transitions_dir / tid / RECORD_FILENAME) for tid in transition_record_ids
    ]

    phase_space_coordinate_ids: list[str] = []
    phase_space_coordinate_paths: list[str] = []
    phase_space_trajectory_paths: list[str] = []
    phase_space_status = "not_requested"
    phase_space_n_failed_validation = 0

    if include_phase_space:
        try:
            ps_result = export_phase_space(
                transitions_dir, phase_space_dir,
                normalization_mode=normalization_mode,
                registry_path=registry_path, requested_use="phase_space_export", claim_family=claim_family,
                mark_seen=False,  # the bundle owns contamination bookkeeping, see below
            )
        except PhaseSpaceExportError as exc:
            raise BuildError(f"phase-space export failed: {exc}") from exc

        if registry_path is not None:
            for decision in ps_result.get("registry_decisions") or []:
                registry_decisions.append(
                    {
                        "id": decision["dataset_id"], "kind": "dataset",
                        "requested_use": decision["requested_use"],
                        "allowed": decision["allowed"], "reason": decision["reason"],
                        "note": "checked again by phase_space.export_from_transitions",
                    }
                )

        phase_space_coordinate_ids = [c.coordinate_id for c in ps_result["coordinates"]]
        phase_space_store = PhaseSpaceStore(phase_space_dir)
        for tid in phase_space_store.list_records():
            phase_space_coordinate_paths.append(
                _relative_path(phase_space_dir / tid / "PhaseSpaceCoordinates.json")
            )
            trajectory_path = phase_space_dir / tid / "PhaseSpaceTrajectory.json"
            if trajectory_path.exists():
                phase_space_trajectory_paths.append(_relative_path(trajectory_path))

        phase_space_n_failed_validation = ps_result["n_failed_validation"]
        if ps_result["n_estimated"] > 0:
            phase_space_status = "estimated"
        elif ps_result["n_coordinates"] == 0:
            phase_space_status = "failed"
        else:
            phase_space_status = "insufficient_data_only"

        claim_scope_ceiling = CLAIM_SCOPE_ORDER[
            min(_claim_scope_rank(claim_scope_ceiling), _claim_scope_rank(PHASE_SPACE_MAX_CLAIM_SCOPE))
        ]

    generated_claim_scope = CLAIM_SCOPE_ORDER[
        min(_claim_scope_rank(r.claim_scope) for r in records)
    ]
    generated_evidence_levels = sorted({r.evidence_level for r in records})

    contamination_updates: list[dict[str, Any]] = []
    updated_registry_path: Optional[str] = None
    if mark_seen and registry is not None:
        note = f"evidence_bundle:{requested_use}"
        registry.mark_seen(dataset, seen_by=seen_by, note=note)
        contamination_updates.append({"id": dataset, "kind": "dataset", "seen_by": seen_by, "note": note, "applied": True})
        for artifact_id in artifact_ids:
            registry.mark_seen(artifact_id, seen_by=seen_by, note=note)
            contamination_updates.append({"id": artifact_id, "kind": "artifact", "seen_by": seen_by, "note": note, "applied": True})
        written = registry.save(updated_registry_out)
        updated_registry_path = _relative_path(written) if written.is_absolute() else str(written)

    bundle = EvidenceBundleV1.make(
        dataset_id=dataset,
        artifact_ids=sorted(artifact_ids),
        requested_use=requested_use,
        transition_record_ids=transition_record_ids,
        phase_space_coordinate_ids=phase_space_coordinate_ids,
        artifact_paths={"source": _relative_path(Path(source)) if Path(source).exists() else str(source)},
        registry_path=str(registry_path) if registry_path else None,
        registry_decisions=registry_decisions,
        contamination_updates=contamination_updates,
        transition_record_paths=transition_record_paths,
        phase_space_coordinate_paths=phase_space_coordinate_paths,
        phase_space_trajectory_paths=phase_space_trajectory_paths,
        claim_scope_ceiling=claim_scope_ceiling,
        evidence_level_ceiling=evidence_level_ceiling,
        generated_claim_scope=generated_claim_scope,
        generated_evidence_levels=generated_evidence_levels,
        null_control_summary=_aggregate_null_control(records),
        validation_summary={
            "transition_records_valid": True,  # export() already raised on any invalid record
            "phase_space_coordinates_valid": (phase_space_n_failed_validation == 0) if include_phase_space else None,
            "phase_space_n_failed_validation": phase_space_n_failed_validation,
        },
        limitations=_base_limitations(dataset, feature_set),
        repo_commit=_git_commit(_REPO_ROOT),
        metadata={
            "feature_set": feature_set,
            "modality": spec["modality"],
            "include_phase_space": include_phase_space,
            "phase_space_status": phase_space_status,
            "normalization_mode": normalization_mode if include_phase_space else None,
            "updated_registry_path": updated_registry_path,
        },
    )

    errors = bundle.validate()
    if errors:
        raise BuildError(f"built bundle failed validation: {'; '.join(errors)}")

    store.write(bundle)

    if include_report:
        from reports.evidence_report import ReportBuildError, build_report
        from reports.renderer import render_markdown

        bundle_path = store.root / "EvidenceBundle.json"
        try:
            report = build_report(bundle, bundle_path)
        except ReportBuildError as exc:
            raise BuildError(f"report generation failed: {exc}") from exc

        report_dir = Path(report_out) if report_out is not None else Path(out)
        md_path = report_dir / "EvidenceReport.md"
        json_path = report_dir / "EvidenceReport.json"
        report.generated_files = [_relative_path(md_path), _relative_path(json_path)]
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report.write_json(json_path)

        bundle.metadata["report"] = {
            "report_id": report.report_id,
            "generated_files": list(report.generated_files),
        }
        post_report_errors = bundle.validate()
        if post_report_errors:
            raise BuildError(f"bundle failed validation after attaching report metadata: {'; '.join(post_report_errors)}")
        store.write(bundle)  # re-write so EvidenceBundle.json reflects metadata.report

    return bundle
