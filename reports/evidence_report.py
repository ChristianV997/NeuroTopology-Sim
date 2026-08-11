"""EvidenceReportV1 -- a deterministic, template-based, human-readable
summary of one EvidenceBundleV1.

Mirrors the deterministic-ID / to_dict / from_dict / write_json / validate
conventions already established by `evidence.bundle.EvidenceBundleV1`,
`transitions.record.TransitionRecordV1`, and
`phase_space.coordinate.PhaseSpaceCoordinateV1`. Structural validation
lives in `reports.validation`; aggregation lives in `reports.tables`; this
module defines the record shape, its serialization, and the one function
(`build_report`) that assembles a report from an already-built bundle --
no scientific recomputation, no LLM call, purely a summary of artifacts
that already exist on disk.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from reports.tables import (
    load_phase_space_coordinate_files,
    load_transition_records,
    summarize_claim_scope,
    summarize_contamination,
    summarize_evidence_level,
    summarize_phase_space,
    summarize_registry,
    summarize_transitions,
)
from reports.validation import validate_report

_SCHEMA_VERSION = "1"
_REPO_ROOT = Path(__file__).resolve().parents[1]

REPORT_TYPE = "evidence_report"
TEMPLATE_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_report_id(
    *, bundle_id: str, report_type: str = REPORT_TYPE, template_version: str = TEMPLATE_VERSION
) -> str:
    """Stable sha256[:16] over the report's identity fields only.

    Excludes created_at, repo_commit, all summaries, limitations, and
    generated_files -- none of those change *which* report this is,
    mirroring `evidence.bundle.compute_bundle_id`.
    """
    basis = {"bundle_id": bundle_id, "report_type": report_type, "template_version": template_version}
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class ReportBuildError(ValueError):
    """Raised when a report cannot be built from a bundle (e.g. missing artifact)."""


class ReportValidationError(ValueError):
    """Raised when an EvidenceReportV1 fails structural validation."""


def _git_commit(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path)


def _blocked_claims_template() -> list[str]:
    """A fixed, deterministic list of prohibited interpretations. Not
    derived from bundle content -- these are always blocked regardless of
    what a specific bundle contains (see benchmarks.split_policy.ALWAYS_BLOCKED_USES
    and this repository's report guardrails)."""
    return [
        "This report does not support a clinical claim.",
        "This report does not support a diagnostic claim.",
        "This report does not support a treatment claim.",
        "This report does not support a claim that any coordinate or "
        "transition artifact is a validated consciousness biomarker.",
        "This report does not support a claim of spiritual/meditative attainment.",
        "This report does not support a mechanistic-causal claim.",
        "This report does not support meditation-stage identification, "
        "jhana identification, or cessation identification.",
        "This report does not support an enlightenment-related claim.",
        "This report does not support a cross-dataset replication claim or "
        "a final claim confirmation beyond what the source EvidenceBundle's "
        "own registry decisions authorized.",
    ]


def _base_limitations(bundle: Any) -> list[str]:
    return [
        "This report is a deterministic, template-based summary of an "
        "existing EvidenceBundleV1 -- it recomputes nothing and generates "
        "no new scientific result; every number it presents already "
        "existed in the referenced TransitionRecordV1/PhaseSpaceCoordinateV1 "
        "artifacts.",
        "This report was generated without any LLM call; its language is "
        "fixed template text, not an AI-generated scientific interpretation.",
        f"Source dataset '{bundle.dataset_id}'; every referenced transition/"
        "phase-space artifact carries its own independent limitations, which "
        "this report does not repeat in full -- read the referenced "
        "EvidenceBundle.json and its artifacts directly for feature-specific "
        "caveats.",
        "claim_scope_summary/evidence_level_summary are copied verbatim from "
        "the source EvidenceBundle; this report never promotes a claim scope "
        "or evidence level beyond what that bundle already recorded.",
    ]


def _reproducibility_commands(bundle: Any, bundle_path: str) -> list[str]:
    metadata = bundle.metadata or {}
    feature_set = metadata.get("feature_set", "<feature-set>")
    source = (bundle.artifact_paths or {}).get("source", "<source-dir>")
    bundle_cmd = (
        f"python -m evidence.export_bundle --dataset {bundle.dataset_id} "
        f"--feature-set {feature_set} --source {source}"
    )
    if bundle.registry_path:
        bundle_cmd += f" --registry {bundle.registry_path} --requested-use {bundle.requested_use}"
    else:
        bundle_cmd += " --no-registry"
    if metadata.get("include_phase_space"):
        bundle_cmd += " --include-phase-space"
    report_cmd = (
        f"python -m reports.export_report --bundle {bundle_path} --format markdown,json"
    )
    return [bundle_cmd, report_cmd]


@dataclass
class EvidenceReportV1:
    schema_version: str = _SCHEMA_VERSION
    report_id: str = ""
    bundle_id: str = ""
    dataset_id: str = ""
    report_title: str = ""
    requested_use: str = "transition_export"
    source_artifacts: dict[str, Any] = field(default_factory=dict)
    registry_summary: dict[str, Any] = field(default_factory=dict)
    contamination_summary: dict[str, Any] = field(default_factory=dict)
    transition_summary: dict[str, Any] = field(default_factory=dict)
    phase_space_summary: dict[str, Any] = field(default_factory=dict)
    null_control_summary: dict[str, Any] = field(default_factory=lambda: {"status": "not_provided"})
    claim_scope_summary: dict[str, Any] = field(default_factory=dict)
    evidence_level_summary: dict[str, Any] = field(default_factory=dict)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    blocked_claims: list[str] = field(default_factory=list)
    reproducibility_commands: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def make(cls, *, bundle_id: str, dataset_id: str, _now: Optional[datetime] = None, **extra: Any) -> "EvidenceReportV1":
        report_id = compute_report_id(bundle_id=bundle_id)
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        kwargs: dict[str, Any] = dict(report_id=report_id, bundle_id=bundle_id, dataset_id=dataset_id, created_at=ts)
        kwargs.update(extra)
        return cls(**kwargs)

    # ── serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "bundle_id": self.bundle_id,
            "dataset_id": self.dataset_id,
            "report_title": self.report_title,
            "requested_use": self.requested_use,
            "source_artifacts": dict(self.source_artifacts or {}),
            "registry_summary": dict(self.registry_summary or {}),
            "contamination_summary": dict(self.contamination_summary or {}),
            "transition_summary": dict(self.transition_summary or {}),
            "phase_space_summary": dict(self.phase_space_summary or {}),
            "null_control_summary": dict(self.null_control_summary or {}),
            "claim_scope_summary": dict(self.claim_scope_summary or {}),
            "evidence_level_summary": dict(self.evidence_level_summary or {}),
            "validation_summary": dict(self.validation_summary or {}),
            "limitations": list(self.limitations),
            "blocked_claims": list(self.blocked_claims),
            "reproducibility_commands": list(self.reproducibility_commands),
            "generated_files": list(self.generated_files),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceReportV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            report_id=d.get("report_id", ""),
            bundle_id=d.get("bundle_id", ""),
            dataset_id=d.get("dataset_id", ""),
            report_title=d.get("report_title", ""),
            requested_use=d.get("requested_use", "transition_export"),
            source_artifacts=dict(d.get("source_artifacts") or {}),
            registry_summary=dict(d.get("registry_summary") or {}),
            contamination_summary=dict(d.get("contamination_summary") or {}),
            transition_summary=dict(d.get("transition_summary") or {}),
            phase_space_summary=dict(d.get("phase_space_summary") or {}),
            null_control_summary=dict(d.get("null_control_summary") or {"status": "not_provided"}),
            claim_scope_summary=dict(d.get("claim_scope_summary") or {}),
            evidence_level_summary=dict(d.get("evidence_level_summary") or {}),
            validation_summary=dict(d.get("validation_summary") or {}),
            limitations=list(d.get("limitations") or []),
            blocked_claims=list(d.get("blocked_claims") or []),
            reproducibility_commands=list(d.get("reproducibility_commands") or []),
            generated_files=list(d.get("generated_files") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "EvidenceReportV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    # ── validation ──────────────────────────────────────────────────────

    def recompute_id(self) -> str:
        return compute_report_id(bundle_id=self.bundle_id)

    def validate(self, *, repo_root: Optional[Path] = None) -> list[str]:
        errors: list[str] = []
        expected_id = self.recompute_id()
        if self.report_id and self.report_id != expected_id:
            errors.append(
                f"report_id '{self.report_id}' does not match the deterministic ID "
                f"computed from this report's identity fields ('{expected_id}')"
            )
        if repo_root is not None:
            errors.extend(validate_report(self, repo_root=repo_root))
        else:
            errors.extend(validate_report(self))
        return errors

    def validate_or_raise(self, *, repo_root: Optional[Path] = None) -> None:
        errors = self.validate(repo_root=repo_root)
        if errors:
            raise ReportValidationError("; ".join(errors))


def build_report(
    bundle: Any,
    bundle_path: Path,
    *,
    repo_root: Path = _REPO_ROOT,
    _now: Optional[datetime] = None,
) -> EvidenceReportV1:
    """Assemble an EvidenceReportV1 from an already-built EvidenceBundleV1.

    Fails closed (raises ReportBuildError) if any transition/phase-space
    artifact the bundle references is missing -- no summary-only mode
    exists in this milestone.
    """
    try:
        transition_records = load_transition_records(repo_root, bundle.transition_record_paths)
    except (OSError, FileNotFoundError) as exc:
        raise ReportBuildError(f"missing referenced transition record artifact: {exc}") from exc
    try:
        coordinate_files = load_phase_space_coordinate_files(repo_root, bundle.phase_space_coordinate_paths)
    except (OSError, FileNotFoundError) as exc:
        raise ReportBuildError(f"missing referenced phase-space coordinate artifact: {exc}") from exc

    bundle_errors = bundle.validate(repo_root=repo_root)
    bundle_rel_path = _relative_path(Path(bundle_path), repo_root)

    source_artifacts = {
        "bundle_path": bundle_rel_path,
        "artifact_ids": list(bundle.artifact_ids),
        "artifact_paths": dict(bundle.artifact_paths or {}),
        "transition_record_paths": list(bundle.transition_record_paths),
        "phase_space_coordinate_paths": list(bundle.phase_space_coordinate_paths),
        "phase_space_trajectory_paths": list(bundle.phase_space_trajectory_paths),
    }

    report = EvidenceReportV1.make(
        bundle_id=bundle.bundle_id,
        dataset_id=bundle.dataset_id,
        report_title=f"Governed Evidence Report -- {bundle.dataset_id} ({bundle.requested_use})",
        requested_use=bundle.requested_use,
        source_artifacts=source_artifacts,
        registry_summary=summarize_registry(bundle),
        contamination_summary=summarize_contamination(bundle),
        transition_summary=summarize_transitions(transition_records),
        phase_space_summary=summarize_phase_space(coordinate_files),
        null_control_summary=dict(bundle.null_control_summary or {}),
        claim_scope_summary=summarize_claim_scope(bundle),
        evidence_level_summary=summarize_evidence_level(bundle),
        validation_summary={
            "bundle_valid": not bundle_errors,
            "bundle_validation_errors": bundle_errors,
        },
        limitations=_base_limitations(bundle),
        blocked_claims=_blocked_claims_template(),
        reproducibility_commands=_reproducibility_commands(bundle, bundle_rel_path),
        repo_commit=_git_commit(repo_root),
        metadata={
            "feature_set": (bundle.metadata or {}).get("feature_set"),
            "include_phase_space": (bundle.metadata or {}).get("include_phase_space", False),
            "phase_space_status": (bundle.metadata or {}).get("phase_space_status"),
        },
        _now=_now,
    )

    errors = report.validate(repo_root=repo_root)
    if errors:
        raise ReportBuildError(f"built report failed validation: {'; '.join(errors)}")
    return report
