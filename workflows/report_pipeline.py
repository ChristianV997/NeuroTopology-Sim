"""ReportPipelineSpecV1 / ReportPipelineRunManifestV1 and
`run_report_pipeline` -- the governed report-pipeline runner.

This module orchestrates existing governed modules
(`adapters.mne_bids_feature_recipe`, `adapters.fmri_derivatives_feature_recipe`,
`adapters.mne_bids`, `adapters.fmri_derivatives`, `evidence.builder`,
`reports.evidence_report`) into one deterministic run. It contains no
feature extraction, no raw EEG/fMRI signal processing, no persistent
-homology computation, and no LLM call -- every scientific number a run
produces was already computed by the module that owns that logic. See
docs/report_pipeline_runner.md.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from workflows.validation import (
    REQUIRED_FIELDS_BY_MODE,
    SUPPORTED_INPUT_MODES,
    validate_pipeline_spec,
    validate_run_manifest,
)

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_pipeline_id(
    *,
    input_mode: str,
    dataset_id: str,
    source_paths: list[str],
    recipe_spec_path: Optional[str],
    feature_table_path: Optional[str],
    mapping_path: Optional[str],
    output_root: Optional[str],
) -> str:
    """Stable sha256[:16] over the pipeline's identity fields only --
    excludes `created_at`, `pipeline_name`, `limitations`, `provenance`,
    and every other mutable/free-text field. Mirrors
    `adapters.mne_bids_feature_recipe_schema.compute_recipe_id`/
    `adapters.fmri_derivatives_feature_recipe_schema.compute_recipe_id`."""
    basis = {
        "input_mode": input_mode,
        "dataset_id": dataset_id,
        "source_paths": sorted(source_paths or []),
        "recipe_spec_path": recipe_spec_path,
        "feature_table_path": feature_table_path,
        "mapping_path": mapping_path,
        "output_root": output_root,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def compute_run_id(*, pipeline_id: str, execution_status: str, created_at: str) -> str:
    """Content-addressed, but -- like `compute_manifest_id` in both feature
    -recipe schemas -- documents one execution event (`created_at` is part
    of the basis), not a pure request identity. Not required to match
    across separate real-world runs of the same pipeline."""
    basis = {"pipeline_id": pipeline_id, "execution_status": execution_status, "created_at": created_at}
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class ReportPipelineValidationError(ValueError):
    """Raised when a pipeline spec or run manifest fails structural validation."""


class ReportPipelineError(ValueError):
    """Raised for run-level problems (missing input file, unsupported
    mode, a downstream adapter/evidence/report call failing) distinct
    from spec validation."""


@dataclass
class ReportPipelineSpecV1:
    schema_version: str = _SCHEMA_VERSION
    pipeline_id: str = ""
    pipeline_name: str = ""
    input_mode: str = ""
    dataset_id: str = ""
    modality: str = ""
    source_paths: list[str] = field(default_factory=list)
    recipe_spec_path: Optional[str] = None
    feature_table_path: Optional[str] = None
    mapping_path: Optional[str] = None
    graph_summary_path: Optional[str] = None
    evidence_bundle_path: Optional[str] = None
    registry_path: Optional[str] = None
    requested_use: str = "transition_export"
    claim_family: str = "report_pipeline_transition"
    output_root: str = ""
    include_phase_space: bool = False
    include_evidence_bundle: bool = False
    include_report: bool = False
    include_html: bool = False
    html_out: Optional[str] = None
    dry_run: bool = False
    resource_bounds: dict[str, Any] = field(default_factory=dict)
    execution_steps: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        input_mode: str,
        dataset_id: str,
        output_root: str,
        source_paths: Optional[list[str]] = None,
        recipe_spec_path: Optional[str] = None,
        feature_table_path: Optional[str] = None,
        mapping_path: Optional[str] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "ReportPipelineSpecV1":
        source_paths = list(source_paths or [])
        pipeline_id = compute_pipeline_id(
            input_mode=input_mode, dataset_id=dataset_id, source_paths=source_paths,
            recipe_spec_path=recipe_spec_path, feature_table_path=feature_table_path,
            mapping_path=mapping_path, output_root=output_root,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            pipeline_id=pipeline_id,
            input_mode=input_mode,
            dataset_id=dataset_id,
            output_root=output_root,
            source_paths=source_paths,
            recipe_spec_path=recipe_spec_path,
            feature_table_path=feature_table_path,
            mapping_path=mapping_path,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_pipeline_id(
            input_mode=self.input_mode, dataset_id=self.dataset_id, source_paths=self.source_paths,
            recipe_spec_path=self.recipe_spec_path, feature_table_path=self.feature_table_path,
            mapping_path=self.mapping_path, output_root=self.output_root,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "input_mode": self.input_mode,
            "dataset_id": self.dataset_id,
            "modality": self.modality,
            "source_paths": list(self.source_paths),
            "recipe_spec_path": self.recipe_spec_path,
            "feature_table_path": self.feature_table_path,
            "mapping_path": self.mapping_path,
            "graph_summary_path": self.graph_summary_path,
            "evidence_bundle_path": self.evidence_bundle_path,
            "registry_path": self.registry_path,
            "requested_use": self.requested_use,
            "claim_family": self.claim_family,
            "output_root": self.output_root,
            "include_phase_space": self.include_phase_space,
            "include_evidence_bundle": self.include_evidence_bundle,
            "include_report": self.include_report,
            "include_html": self.include_html,
            "html_out": self.html_out,
            "dry_run": self.dry_run,
            "resource_bounds": dict(self.resource_bounds or {}),
            "execution_steps": list(self.execution_steps),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReportPipelineSpecV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            pipeline_id=d.get("pipeline_id", ""),
            pipeline_name=d.get("pipeline_name", ""),
            input_mode=d.get("input_mode", ""),
            dataset_id=d.get("dataset_id", ""),
            modality=d.get("modality", ""),
            source_paths=list(d.get("source_paths") or []),
            recipe_spec_path=d.get("recipe_spec_path"),
            feature_table_path=d.get("feature_table_path"),
            mapping_path=d.get("mapping_path"),
            graph_summary_path=d.get("graph_summary_path"),
            evidence_bundle_path=d.get("evidence_bundle_path"),
            registry_path=d.get("registry_path"),
            requested_use=d.get("requested_use", "transition_export"),
            claim_family=d.get("claim_family", "report_pipeline_transition"),
            output_root=d.get("output_root", ""),
            include_phase_space=bool(d.get("include_phase_space", False)),
            include_evidence_bundle=bool(d.get("include_evidence_bundle", False)),
            include_report=bool(d.get("include_report", False)),
            include_html=bool(d.get("include_html", False)),
            html_out=d.get("html_out"),
            dry_run=bool(d.get("dry_run", False)),
            resource_bounds=dict(d.get("resource_bounds") or {}),
            execution_steps=list(d.get("execution_steps") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "ReportPipelineSpecV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_pipeline_spec(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise ReportPipelineValidationError("; ".join(errors))


@dataclass
class ReportPipelineRunManifestV1:
    schema_version: str = _SCHEMA_VERSION
    run_id: str = ""
    pipeline_id: str = ""
    input_mode: str = ""
    dataset_id: str = ""
    modality: str = ""
    execution_status: str = "completed"
    steps_planned: list[str] = field(default_factory=list)
    steps_completed: list[str] = field(default_factory=list)
    steps_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_root: str = ""
    generated_feature_paths: list[str] = field(default_factory=list)
    generated_mapping_paths: list[str] = field(default_factory=list)
    transition_record_paths: list[str] = field(default_factory=list)
    phase_space_paths: list[str] = field(default_factory=list)
    evidence_bundle_paths: list[str] = field(default_factory=list)
    evidence_report_paths: list[str] = field(default_factory=list)
    report_pack_path: Optional[str] = None
    registry_updated_path: Optional[str] = None
    created_at: str = ""
    repo_commit: Optional[str] = None
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, pipeline_id: str, dataset_id: str, execution_status: str = "completed",
        _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "ReportPipelineRunManifestV1":
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        run_id = compute_run_id(pipeline_id=pipeline_id, execution_status=execution_status, created_at=ts)
        return cls(
            run_id=run_id, pipeline_id=pipeline_id, dataset_id=dataset_id,
            execution_status=execution_status, created_at=ts, **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "pipeline_id": self.pipeline_id,
            "input_mode": self.input_mode,
            "dataset_id": self.dataset_id,
            "modality": self.modality,
            "execution_status": self.execution_status,
            "steps_planned": list(self.steps_planned),
            "steps_completed": list(self.steps_completed),
            "steps_skipped": list(self.steps_skipped),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "output_root": self.output_root,
            "generated_feature_paths": list(self.generated_feature_paths),
            "generated_mapping_paths": list(self.generated_mapping_paths),
            "transition_record_paths": list(self.transition_record_paths),
            "phase_space_paths": list(self.phase_space_paths),
            "evidence_bundle_paths": list(self.evidence_bundle_paths),
            "evidence_report_paths": list(self.evidence_report_paths),
            "report_pack_path": self.report_pack_path,
            "registry_updated_path": self.registry_updated_path,
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReportPipelineRunManifestV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            run_id=d.get("run_id", ""),
            pipeline_id=d.get("pipeline_id", ""),
            input_mode=d.get("input_mode", ""),
            dataset_id=d.get("dataset_id", ""),
            modality=d.get("modality", ""),
            execution_status=d.get("execution_status", "completed"),
            steps_planned=list(d.get("steps_planned") or []),
            steps_completed=list(d.get("steps_completed") or []),
            steps_skipped=list(d.get("steps_skipped") or []),
            errors=list(d.get("errors") or []),
            warnings=list(d.get("warnings") or []),
            output_root=d.get("output_root", ""),
            generated_feature_paths=list(d.get("generated_feature_paths") or []),
            generated_mapping_paths=list(d.get("generated_mapping_paths") or []),
            transition_record_paths=list(d.get("transition_record_paths") or []),
            phase_space_paths=list(d.get("phase_space_paths") or []),
            evidence_bundle_paths=list(d.get("evidence_bundle_paths") or []),
            evidence_report_paths=list(d.get("evidence_report_paths") or []),
            report_pack_path=d.get("report_pack_path"),
            registry_updated_path=d.get("registry_updated_path"),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "ReportPipelineRunManifestV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_run_manifest(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise ReportPipelineValidationError("; ".join(errors))


def _repo_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _relative_path(path: Union[str, Path]) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


_BUILTIN_DISPATCH: dict[str, tuple[str, str]] = {
    "builtin_ds005620_cohort_summary": ("ds005620", "cohort_summary"),
    "builtin_ds005620_spatial_defect_map": ("ds005620", "spatial_defect_map"),
    "builtin_ds000245_schaefer100_motcorr": ("ds000245", "schaefer100_motcorr"),
    "builtin_ds000245_kmeans100": ("ds000245", "kmeans100"),
}

_PIPELINE_LIMITATIONS: list[str] = [
    "workflows.report_pipeline orchestrates existing governed modules only -- it contains no feature "
    "extraction, no raw EEG/fMRI signal processing, no persistent-homology computation, and no LLM call.",
    "This pipeline runner's own output (ReportPack.json) is not itself evidence -- it is a deterministic "
    "index over the TransitionRecordV1/PhaseSpaceCoordinateV1/EvidenceBundleV1/EvidenceReportV1 artifacts "
    "the underlying adapters/evidence/report modules already produced.",
]


def _planned_steps_for_mode(input_mode: str, spec: "ReportPipelineSpecV1") -> list[str]:
    if input_mode == "existing_evidence_bundle":
        steps = ["load_existing_evidence_bundle"]
        if spec.include_report:
            steps.append("build_evidence_report")
        steps.append("write_report_pack")
        if spec.include_html:
            steps.append("render_html_report_pack")
        return steps
    if input_mode in {"mne_bids_epoch_table_recipe", "fmri_timeseries_recipe", "fmri_connectivity_matrix_recipe", "fmri_graph_summary_recipe"}:
        steps = ["run_feature_recipe", "write_recipe_outputs", "export_adapter_transitions"]
        if spec.include_phase_space:
            steps.append("export_phase_space")
        if spec.include_evidence_bundle:
            steps.append("build_evidence_bundle")
        if spec.include_report:
            steps.append("build_evidence_report")
        steps.append("write_report_pack")
        if spec.include_html:
            steps.append("render_html_report_pack")
        return steps
    if input_mode in {"mne_bids_derived_features", "fmri_derived_features"}:
        steps = ["export_adapter_transitions"]
        if spec.include_phase_space:
            steps.append("export_phase_space")
        if spec.include_evidence_bundle:
            steps.append("build_evidence_bundle")
        if spec.include_report:
            steps.append("build_evidence_report")
        steps.append("write_report_pack")
        if spec.include_html:
            steps.append("render_html_report_pack")
        return steps
    if input_mode in _BUILTIN_DISPATCH:
        steps = ["build_evidence_bundle"]
        if spec.include_report:
            steps.append("build_evidence_report")
        steps.append("write_report_pack")
        if spec.include_html:
            steps.append("render_html_report_pack")
        return steps
    return []


def run_report_pipeline(spec: "ReportPipelineSpecV1") -> ReportPipelineRunManifestV1:
    """Validate `spec`, execute only the steps `spec.input_mode` requires,
    and write a `ReportPipelineRunManifestV1` (and, unless `dry_run`, a
    `ReportPackV1`) under a validated output directory.

    Never raises for an unsupported mode or a missing input path -- both
    are recorded in the returned manifest's `errors` with
    `execution_status="failed"`, matching the "fail clearly, don't crash
    the whole run" discipline every adapter/recipe in this repository
    already follows. Raises only `ReportPipelineValidationError` if the
    spec itself is structurally invalid (caught before any step runs)."""
    from workflows.store import ReportPackLayout

    spec.validate_or_raise()
    layout = ReportPackLayout(spec.output_root)
    steps_planned = _planned_steps_for_mode(spec.input_mode, spec)

    if spec.dry_run:
        layout.ensure_root()
        spec.write_json(layout.spec_path)
        manifest = ReportPipelineRunManifestV1.make(
            pipeline_id=spec.pipeline_id, dataset_id=spec.dataset_id, input_mode=spec.input_mode,
            modality=spec.modality, execution_status="dry_run", output_root=spec.output_root,
            steps_planned=steps_planned, steps_completed=[], steps_skipped=list(steps_planned),
            repo_commit=_repo_commit(),
            limitations=_PIPELINE_LIMITATIONS + ["dry_run=True: no recipe/adapter/evidence/report step was executed; no scientific output was generated."],
            provenance=f"Dry-run plan only for pipeline_id={spec.pipeline_id} (input_mode={spec.input_mode}).",
        )
        manifest.validate_or_raise()
        manifest.write_json(layout.manifest_path)
        return manifest

    steps_completed: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    generated_feature_paths: list[str] = []
    generated_mapping_paths: list[str] = []
    transition_record_paths: list[str] = []
    phase_space_paths: list[str] = []
    evidence_bundle_paths: list[str] = []
    evidence_report_paths: list[str] = []
    registry_updated_path: Optional[str] = None
    report_pack_path: Optional[str] = None

    evidence_bundle = None
    evidence_report = None

    try:
        layout.ensure_root()

        if spec.input_mode == "existing_evidence_bundle":
            (
                evidence_bundle, evidence_report, eb_paths, er_paths,
            ) = _run_existing_evidence_bundle(spec, layout, steps_completed)
            evidence_bundle_paths.extend(eb_paths)
            evidence_report_paths.extend(er_paths)
        elif spec.input_mode in {"mne_bids_epoch_table_recipe", "fmri_timeseries_recipe", "fmri_connectivity_matrix_recipe", "fmri_graph_summary_recipe"}:
            (
                evidence_bundle, evidence_report, feature_paths, mapping_paths, tx_paths, ps_paths, reg_out, eb_paths, er_paths,
            ) = _run_recipe_mode(spec, layout, steps_completed)
            generated_feature_paths.extend(feature_paths)
            generated_mapping_paths.extend(mapping_paths)
            transition_record_paths.extend(tx_paths)
            phase_space_paths.extend(ps_paths)
            registry_updated_path = reg_out
            evidence_bundle_paths.extend(eb_paths)
            evidence_report_paths.extend(er_paths)
        elif spec.input_mode in {"mne_bids_derived_features", "fmri_derived_features"}:
            (
                evidence_bundle, evidence_report, tx_paths, ps_paths, reg_out, eb_paths, er_paths,
            ) = _run_derived_features_mode(spec, layout, steps_completed)
            transition_record_paths.extend(tx_paths)
            phase_space_paths.extend(ps_paths)
            registry_updated_path = reg_out
            evidence_bundle_paths.extend(eb_paths)
            evidence_report_paths.extend(er_paths)
        elif spec.input_mode in _BUILTIN_DISPATCH:
            (
                evidence_bundle, evidence_report, eb_paths, er_paths,
            ) = _run_builtin_mode(spec, layout, steps_completed)
            evidence_bundle_paths.extend(eb_paths)
            evidence_report_paths.extend(er_paths)
        else:
            raise ReportPipelineError(f"unsupported input_mode: {spec.input_mode!r}")

    except (ReportPipelineError, Exception) as exc:  # noqa: BLE001 -- fail closed into the manifest, never crash
        errors.append(str(exc))
        execution_status = "failed"
        manifest = ReportPipelineRunManifestV1.make(
            pipeline_id=spec.pipeline_id, dataset_id=spec.dataset_id, input_mode=spec.input_mode,
            modality=spec.modality, execution_status=execution_status, output_root=spec.output_root,
            steps_planned=steps_planned, steps_completed=steps_completed,
            steps_skipped=[s for s in steps_planned if s not in steps_completed],
            errors=errors, warnings=warnings,
            generated_feature_paths=generated_feature_paths, generated_mapping_paths=generated_mapping_paths,
            transition_record_paths=transition_record_paths, phase_space_paths=phase_space_paths,
            evidence_bundle_paths=evidence_bundle_paths, evidence_report_paths=evidence_report_paths,
            registry_updated_path=registry_updated_path, repo_commit=_repo_commit(),
            limitations=_PIPELINE_LIMITATIONS,
            provenance=f"Failed run for pipeline_id={spec.pipeline_id} (input_mode={spec.input_mode}): {exc}",
        )
        manifest.validate_or_raise()
        manifest.write_json(layout.manifest_path)
        return manifest

    pack = None
    if evidence_bundle is not None or evidence_report is not None:
        from workflows.report_pack import ReportPackV1, blocked_interpretations_template

        summary: dict[str, Any] = {"input_mode": spec.input_mode, "dataset_id": spec.dataset_id}
        if evidence_bundle is not None:
            summary.update({
                "claim_scope_ceiling": evidence_bundle.claim_scope_ceiling,
                "evidence_level_ceiling": evidence_bundle.evidence_level_ceiling,
                "generated_claim_scope": evidence_bundle.generated_claim_scope,
                "null_control_status": (evidence_bundle.null_control_summary or {}).get("status", "not_provided"),
                "n_transition_records": len(evidence_bundle.transition_record_ids),
                "n_phase_space_coordinates": len(evidence_bundle.phase_space_coordinate_ids),
            })
        if evidence_report is not None:
            summary["report_id"] = evidence_report.report_id

        artifact_manifest = {
            "generated_feature_paths": generated_feature_paths,
            "generated_mapping_paths": generated_mapping_paths,
            "transition_record_paths": transition_record_paths,
            "phase_space_paths": phase_space_paths,
            "evidence_bundle_paths": evidence_bundle_paths,
            "evidence_report_paths": evidence_report_paths,
        }
        generated_files = (
            generated_feature_paths + generated_mapping_paths + transition_record_paths
            + phase_space_paths + evidence_bundle_paths + evidence_report_paths
        )

        pack = ReportPackV1.make(
            dataset_id=spec.dataset_id, input_mode=spec.input_mode,
            evidence_bundle_ids=[evidence_bundle.bundle_id] if evidence_bundle is not None else [],
            evidence_report_ids=[evidence_report.report_id] if evidence_report is not None else [],
            modality=spec.modality, pipeline_run_id=spec.pipeline_id,
            artifact_manifest=artifact_manifest, summary=summary,
            limitations=_PIPELINE_LIMITATIONS + [
                "This report pack references artifacts produced by this single pipeline run only -- it is "
                "not a cross-run or cross-dataset aggregate.",
            ],
            blocked_interpretations=blocked_interpretations_template(),
            reproducibility_commands=[
                f"python -m workflows.export_report_pack --spec {layout.spec_path_relative} --out {spec.output_root}"
            ],
            generated_files=generated_files,
            repo_commit=_repo_commit(),
        )
        pack.validate_or_raise()
        pack.write_json(layout.report_pack_path)
        report_pack_path = _relative_path(layout.report_pack_path)
        steps_completed.append("write_report_pack")

    execution_status = "completed" if not warnings else "completed_with_warnings"

    manifest = ReportPipelineRunManifestV1.make(
        pipeline_id=spec.pipeline_id, dataset_id=spec.dataset_id, input_mode=spec.input_mode,
        modality=spec.modality, execution_status=execution_status, output_root=spec.output_root,
        steps_planned=steps_planned, steps_completed=steps_completed,
        steps_skipped=[s for s in steps_planned if s not in steps_completed],
        errors=errors, warnings=warnings,
        generated_feature_paths=generated_feature_paths, generated_mapping_paths=generated_mapping_paths,
        transition_record_paths=transition_record_paths, phase_space_paths=phase_space_paths,
        evidence_bundle_paths=evidence_bundle_paths, evidence_report_paths=evidence_report_paths,
        report_pack_path=report_pack_path, registry_updated_path=registry_updated_path,
        repo_commit=_repo_commit(), limitations=_PIPELINE_LIMITATIONS,
        provenance=f"Produced by workflows.report_pipeline.run_report_pipeline for pipeline_id={spec.pipeline_id} (input_mode={spec.input_mode}).",
    )
    manifest.validate_or_raise()
    spec.write_json(layout.spec_path)
    manifest.write_json(layout.manifest_path)

    # Optional HTML report-pack rendering -- only ever attempted after a
    # successful run with a real ReportPack.json already on disk (a failed
    # run returns earlier, above, and never reaches this point). Metadata
    # is added additively, mirroring evidence.builder.build_evidence_bundle's
    # own "write once, optionally augment metadata, re-write" pattern for
    # its include_report step.
    if spec.include_html and report_pack_path is not None:
        from workflows.html_report_pack import HtmlReportPackError, render_html_report_pack

        html_out = spec.html_out or str(Path(spec.output_root) / "html")
        try:
            html_pack = render_html_report_pack(
                report_pack_path=layout.report_pack_path, out_dir=html_out,
                pipeline_manifest_path=layout.manifest_path,
            )
        except HtmlReportPackError as exc:
            manifest.warnings.append(f"HTML report pack rendering failed (report pack itself is unaffected): {exc}")
            manifest.execution_status = "completed_with_warnings"
        else:
            manifest.metadata["html_report_pack"] = {
                "html_pack_id": html_pack.html_pack_id,
                "index_html_path": html_pack.index_html_path,
                "html_pack_json_path": _relative_path(Path(html_out) / "HtmlReportPack.json"),
            }
            manifest.steps_completed.append("render_html_report_pack")
            if "render_html_report_pack" in manifest.steps_skipped:
                manifest.steps_skipped.remove("render_html_report_pack")
        manifest.write_json(layout.manifest_path)

    return manifest


# ── per-mode execution helpers ─────────────────────────────────────────────


def _resolve_repo_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def _require_exists(path: Optional[str], *, label: str) -> Path:
    if not path:
        raise ReportPipelineError(f"{label} is required but was not provided")
    resolved = _resolve_repo_path(path)
    if not resolved.exists():
        raise ReportPipelineError(f"{label} does not exist: {path}")
    return resolved


def _run_existing_evidence_bundle(spec: "ReportPipelineSpecV1", layout: Any, steps_completed: list[str]):
    from evidence.bundle import EvidenceBundleV1

    bundle_path = _require_exists(spec.evidence_bundle_path, label="evidence_bundle_path")
    bundle = EvidenceBundleV1.from_json(bundle_path.read_text(encoding="utf-8"))
    bundle_errors = bundle.validate(repo_root=_REPO_ROOT)
    if bundle_errors:
        raise ReportPipelineError(f"existing evidence bundle at {spec.evidence_bundle_path} failed validation: {'; '.join(bundle_errors)}")
    steps_completed.append("load_existing_evidence_bundle")
    eb_paths = [_relative_path(bundle_path)]

    report = None
    er_paths: list[str] = []
    if spec.include_report:
        from reports.evidence_report import ReportBuildError, build_report
        from reports.renderer import render_markdown

        try:
            report = build_report(bundle, bundle_path)
        except ReportBuildError as exc:
            raise ReportPipelineError(f"report generation failed: {exc}") from exc
        out_dir = layout.existing_bundle_report_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        report.generated_files = [_relative_path(out_dir / "EvidenceReport.md"), _relative_path(out_dir / "EvidenceReport.json")]
        (out_dir / "EvidenceReport.md").write_text(render_markdown(report), encoding="utf-8")
        report.write_json(out_dir / "EvidenceReport.json")
        er_paths = list(report.generated_files)
        steps_completed.append("build_evidence_report")

    return bundle, report, eb_paths, er_paths


def _load_recipe_spec(spec: "ReportPipelineSpecV1"):
    recipe_spec_path = _require_exists(spec.recipe_spec_path, label="recipe_spec_path")
    if spec.input_mode == "mne_bids_epoch_table_recipe":
        from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

        return FeatureRecipeSpecV1.from_json(recipe_spec_path.read_text(encoding="utf-8")), "eeg"
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    return FmriFeatureRecipeSpecV1.from_json(recipe_spec_path.read_text(encoding="utf-8")), "fmri"


def _run_recipe_mode(spec: "ReportPipelineSpecV1", layout: Any, steps_completed: list[str]):
    recipe_spec, family = _load_recipe_spec(spec)

    if family == "eeg":
        from adapters.mne_bids_feature_recipe import run_feature_recipe as run_recipe
        from adapters.mne_bids_feature_recipe import write_recipe_outputs as write_recipe

        input_path = _require_exists(spec.source_paths[0] if spec.source_paths else None, label="source_paths[0]")
        result = run_recipe(recipe_spec, epoch_table_path=input_path)
    else:
        from adapters.fmri_derivatives_feature_recipe import run_feature_recipe as run_recipe
        from adapters.fmri_derivatives_feature_recipe import write_recipe_outputs as write_recipe

        if spec.input_mode == "fmri_graph_summary_recipe":
            input_path = _require_exists(spec.graph_summary_path, label="graph_summary_path")
        else:
            input_path = _require_exists(spec.source_paths[0] if spec.source_paths else None, label="source_paths[0]")
        result = run_recipe(recipe_spec, input_path=input_path)

    steps_completed.append("run_feature_recipe")

    features_path, mapping_path, recipe_manifest, _summary_path = write_recipe(
        recipe_spec, result, str(layout.recipe_output_dir_relative)
    )
    steps_completed.append("write_recipe_outputs")
    generated_feature_paths = [_relative_path(features_path)]
    generated_mapping_paths = [_relative_path(mapping_path)]

    updated_registry_out = layout.registry_updated_path if spec.registry_path else None

    if family == "eeg":
        from adapters.mne_bids import export_mne_bids_derived_transitions as export_transitions
    else:
        from adapters.fmri_derivatives import export_fmri_derivative_transitions as export_transitions

    adapter_out = layout.adapter_export_dir
    adapter_result = export_transitions(
        features_path, mapping_path, adapter_out,
        registry_path=Path(_resolve_repo_path(spec.registry_path)) if spec.registry_path else None,
        no_registry=spec.registry_path is None,
        requested_use=spec.requested_use, claim_family=spec.claim_family,
        include_phase_space=spec.include_phase_space,
        include_evidence_bundle=spec.include_evidence_bundle,
        include_report=spec.include_report,
        updated_registry_out=updated_registry_out,
    )
    steps_completed.append("export_adapter_transitions")

    from transitions.store import RECORD_FILENAME

    tx_paths = [_relative_path(adapter_out / "transitions" / tid / RECORD_FILENAME) for tid in [r.transition_id for r in adapter_result["records"]]]
    ps_paths: list[str] = []
    if spec.include_phase_space:
        steps_completed.append("export_phase_space")
        ps_dir = adapter_out / "phase_space"
        if ps_dir.exists():
            ps_paths = [_relative_path(p) for p in sorted(ps_dir.glob("*/PhaseSpaceCoordinates.json"))]

    reg_out = None
    if updated_registry_out is not None and Path(updated_registry_out).exists():
        reg_out = _relative_path(updated_registry_out)

    bundle = adapter_result.get("evidence_bundle")
    eb_paths: list[str] = []
    if spec.include_evidence_bundle and bundle is not None:
        steps_completed.append("build_evidence_bundle")
        eb_paths = [_relative_path(adapter_out / "EvidenceBundle.json")]

    report = None
    er_paths: list[str] = []
    if spec.include_report and adapter_result.get("report") is not None:
        from reports.evidence_report import EvidenceReportV1

        report_json_path = adapter_out / "EvidenceReport.json"
        if report_json_path.exists():
            report = EvidenceReportV1.from_json(report_json_path.read_text(encoding="utf-8"))
            er_paths = [_relative_path(adapter_out / "EvidenceReport.md"), _relative_path(report_json_path)]
        steps_completed.append("build_evidence_report")

    return bundle, report, generated_feature_paths, generated_mapping_paths, tx_paths, ps_paths, reg_out, eb_paths, er_paths


def _run_derived_features_mode(spec: "ReportPipelineSpecV1", layout: Any, steps_completed: list[str]):
    features_path = _require_exists(spec.feature_table_path, label="feature_table_path")
    mapping_path = _require_exists(spec.mapping_path, label="mapping_path")

    if spec.input_mode == "mne_bids_derived_features":
        from adapters.mne_bids import export_mne_bids_derived_transitions as export_transitions
    else:
        from adapters.fmri_derivatives import export_fmri_derivative_transitions as export_transitions

    updated_registry_out = layout.registry_updated_path if spec.registry_path else None
    adapter_out = layout.adapter_export_dir
    adapter_result = export_transitions(
        features_path, mapping_path, adapter_out,
        registry_path=Path(_resolve_repo_path(spec.registry_path)) if spec.registry_path else None,
        no_registry=spec.registry_path is None,
        requested_use=spec.requested_use, claim_family=spec.claim_family,
        include_phase_space=spec.include_phase_space,
        include_evidence_bundle=spec.include_evidence_bundle,
        include_report=spec.include_report,
        updated_registry_out=updated_registry_out,
    )
    steps_completed.append("export_adapter_transitions")

    from transitions.store import RECORD_FILENAME

    tx_paths = [_relative_path(adapter_out / "transitions" / tid / RECORD_FILENAME) for tid in [r.transition_id for r in adapter_result["records"]]]
    ps_paths: list[str] = []
    if spec.include_phase_space:
        steps_completed.append("export_phase_space")
        ps_dir = adapter_out / "phase_space"
        if ps_dir.exists():
            ps_paths = [_relative_path(p) for p in sorted(ps_dir.glob("*/PhaseSpaceCoordinates.json"))]

    reg_out = None
    if updated_registry_out is not None and Path(updated_registry_out).exists():
        reg_out = _relative_path(updated_registry_out)

    bundle = adapter_result.get("evidence_bundle")
    eb_paths: list[str] = []
    if spec.include_evidence_bundle and bundle is not None:
        steps_completed.append("build_evidence_bundle")
        eb_paths = [_relative_path(adapter_out / "EvidenceBundle.json")]

    report = None
    er_paths: list[str] = []
    if spec.include_report and adapter_result.get("report") is not None:
        from reports.evidence_report import EvidenceReportV1

        report_json_path = adapter_out / "EvidenceReport.json"
        if report_json_path.exists():
            report = EvidenceReportV1.from_json(report_json_path.read_text(encoding="utf-8"))
            er_paths = [_relative_path(adapter_out / "EvidenceReport.md"), _relative_path(report_json_path)]
        steps_completed.append("build_evidence_report")

    return bundle, report, tx_paths, ps_paths, reg_out, eb_paths, er_paths


def _run_builtin_mode(spec: "ReportPipelineSpecV1", layout: Any, steps_completed: list[str]):
    from evidence.builder import BuildError, build_evidence_bundle

    dataset, feature_set = _BUILTIN_DISPATCH[spec.input_mode]
    source = _require_exists(spec.source_paths[0] if spec.source_paths else None, label="source_paths[0]")

    try:
        bundle = build_evidence_bundle(
            dataset=dataset, feature_set=feature_set, source=source, out=layout.adapter_export_dir,
            registry_path=Path(_resolve_repo_path(spec.registry_path)) if spec.registry_path else None,
            requested_use=spec.requested_use, claim_family=spec.claim_family,
            include_phase_space=spec.include_phase_space,
            no_registry=spec.registry_path is None,
            include_report=spec.include_report,
        )
    except BuildError as exc:
        raise ReportPipelineError(f"builtin evidence bundle build failed: {exc}") from exc
    steps_completed.append("build_evidence_bundle")
    eb_paths = [_relative_path(layout.adapter_export_dir / "EvidenceBundle.json")]

    report = None
    er_paths: list[str] = []
    if spec.include_report:
        from reports.evidence_report import EvidenceReportV1

        report_json_path = layout.adapter_export_dir / "EvidenceReport.json"
        if report_json_path.exists():
            report = EvidenceReportV1.from_json(report_json_path.read_text(encoding="utf-8"))
            er_paths = [_relative_path(layout.adapter_export_dir / "EvidenceReport.md"), _relative_path(report_json_path)]
        steps_completed.append("build_evidence_report")

    return bundle, report, eb_paths, er_paths
