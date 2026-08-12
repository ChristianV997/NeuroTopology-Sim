"""ReportPackV1 -- the product-facing, deterministic index of one pipeline
run's generated artifacts.

A `ReportPackV1` is not itself evidence and carries no `claim_scope`/
`evidence_level` field of its own -- it only *references* the
claim_scope_ceiling/evidence_level_ceiling values already recorded on the
`EvidenceBundleV1`(s) a pipeline run produced or consumed (see
`summary`), copied verbatim, never promoted. See
docs/report_pipeline_runner.md.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from workflows.validation import validate_report_pack

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_report_pack_id(
    *, dataset_id: str, input_mode: str, evidence_bundle_ids: list[str], evidence_report_ids: list[str]
) -> str:
    """Stable sha256[:16] over the pack's identity fields only -- excludes
    `created_at`, `summary`, `artifact_manifest`, and every other
    execution-detail/free-text field. Two pipeline runs referencing the
    same evidence bundle(s)/report(s) for the same dataset/input_mode
    always yield the same `report_pack_id`."""
    basis = {
        "dataset_id": dataset_id,
        "input_mode": input_mode,
        "evidence_bundle_ids": sorted(evidence_bundle_ids or []),
        "evidence_report_ids": sorted(evidence_report_ids or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def blocked_interpretations_template() -> list[str]:
    """A fixed, deterministic list of prohibited interpretations for a
    report pack -- not derived from pack content, mirroring
    `reports.evidence_report._blocked_claims_template`'s fixed-template
    convention, extended with pipeline-runner-specific items."""
    return [
        "This report pack does not support a clinical claim.",
        "This report pack does not support a diagnostic claim.",
        "This report pack does not support a treatment claim.",
        "This report pack does not support a claim that any referenced artifact is a validated consciousness biomarker.",
        "This report pack does not support a claim of spiritual/meditative attainment.",
        "This report pack does not support a mechanistic-causal claim.",
        "This report pack is not itself clinical evidence -- it is a deterministic index of already-governed artifacts.",
        "This report pack does not imply raw EEG/BOLD preprocessing beyond what the referenced recipe/adapter step actually performed.",
        "This report pack does not promote the claim_scope_ceiling or evidence_level_ceiling of any referenced EvidenceBundleV1.",
    ]


class ReportPackValidationError(ValueError):
    """Raised when a ReportPackV1 fails structural validation."""


@dataclass
class ReportPackV1:
    schema_version: str = _SCHEMA_VERSION
    report_pack_id: str = ""
    dataset_id: str = ""
    modality: str = ""
    input_mode: str = ""
    pipeline_run_id: str = ""
    evidence_bundle_ids: list[str] = field(default_factory=list)
    evidence_report_ids: list[str] = field(default_factory=list)
    artifact_manifest: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    blocked_interpretations: list[str] = field(default_factory=blocked_interpretations_template)
    reproducibility_commands: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        dataset_id: str,
        input_mode: str,
        evidence_bundle_ids: Optional[list[str]] = None,
        evidence_report_ids: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "ReportPackV1":
        evidence_bundle_ids = list(evidence_bundle_ids or [])
        evidence_report_ids = list(evidence_report_ids or [])
        report_pack_id = compute_report_pack_id(
            dataset_id=dataset_id, input_mode=input_mode,
            evidence_bundle_ids=evidence_bundle_ids, evidence_report_ids=evidence_report_ids,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            report_pack_id=report_pack_id,
            dataset_id=dataset_id,
            input_mode=input_mode,
            evidence_bundle_ids=evidence_bundle_ids,
            evidence_report_ids=evidence_report_ids,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_report_pack_id(
            dataset_id=self.dataset_id, input_mode=self.input_mode,
            evidence_bundle_ids=self.evidence_bundle_ids, evidence_report_ids=self.evidence_report_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_pack_id": self.report_pack_id,
            "dataset_id": self.dataset_id,
            "modality": self.modality,
            "input_mode": self.input_mode,
            "pipeline_run_id": self.pipeline_run_id,
            "evidence_bundle_ids": list(self.evidence_bundle_ids),
            "evidence_report_ids": list(self.evidence_report_ids),
            "artifact_manifest": dict(self.artifact_manifest or {}),
            "summary": dict(self.summary or {}),
            "limitations": list(self.limitations),
            "blocked_interpretations": list(self.blocked_interpretations),
            "reproducibility_commands": list(self.reproducibility_commands),
            "generated_files": list(self.generated_files),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReportPackV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            report_pack_id=d.get("report_pack_id", ""),
            dataset_id=d.get("dataset_id", ""),
            modality=d.get("modality", ""),
            input_mode=d.get("input_mode", ""),
            pipeline_run_id=d.get("pipeline_run_id", ""),
            evidence_bundle_ids=list(d.get("evidence_bundle_ids") or []),
            evidence_report_ids=list(d.get("evidence_report_ids") or []),
            artifact_manifest=dict(d.get("artifact_manifest") or {}),
            summary=dict(d.get("summary") or {}),
            limitations=list(d.get("limitations") or []),
            blocked_interpretations=list(d.get("blocked_interpretations") or []),
            reproducibility_commands=list(d.get("reproducibility_commands") or []),
            generated_files=list(d.get("generated_files") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "ReportPackV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_report_pack(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise ReportPackValidationError("; ".join(errors))
