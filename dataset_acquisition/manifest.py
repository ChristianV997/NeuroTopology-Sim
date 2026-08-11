"""DatasetAcquisitionManifestV1 -- the record of what actually happened
when `dataset_acquisition.executor.execute_acquisition_plan` ran a plan.

Unlike `DatasetAcquisitionPlanV1.plan_id`, `manifest_id` is **not**
required to be deterministic across repeated runs: a manifest documents one
specific execution event (which may legitimately differ run to run --
different files present, a different `created_at`), not a reusable request.
It is still computed from the manifest's own content (not random) so a
byte-identical execution produces a byte-identical `manifest_id`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_acquisition.validation import validate_manifest

_SCHEMA_VERSION = "1"


def compute_manifest_id(
    *,
    plan_id: str,
    execution_status: str,
    acquired_paths: list[str],
    created_at: str,
) -> str:
    basis = {
        "plan_id": plan_id,
        "execution_status": execution_status,
        "acquired_paths": sorted(acquired_paths),
        "created_at": created_at,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DatasetAcquisitionManifestV1:
    schema_version: str = _SCHEMA_VERSION
    manifest_id: str = ""
    plan_id: str = ""
    candidate_id: str = ""
    source_catalog: str = ""
    source_dataset_id: str = ""
    execution_status: str = "planned_only"
    acquired_paths: list[str] = field(default_factory=list)
    acquired_file_count: int = 0
    acquired_size_bytes: int = 0
    checksums: dict[str, str] = field(default_factory=dict)
    skipped_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    bids_metadata_summary: Optional[dict[str, Any]] = None
    dataset_record_paths: list[str] = field(default_factory=list)
    artifact_record_paths: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: str = ""
    risks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        plan_id: str,
        candidate_id: str,
        execution_status: str = "planned_only",
        acquired_paths: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "DatasetAcquisitionManifestV1":
        acquired_paths = list(acquired_paths or [])
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        manifest_id = compute_manifest_id(
            plan_id=plan_id, execution_status=execution_status, acquired_paths=acquired_paths, created_at=ts
        )
        return cls(
            manifest_id=manifest_id,
            plan_id=plan_id,
            candidate_id=candidate_id,
            execution_status=execution_status,
            acquired_paths=acquired_paths,
            created_at=ts,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "plan_id": self.plan_id,
            "candidate_id": self.candidate_id,
            "source_catalog": self.source_catalog,
            "source_dataset_id": self.source_dataset_id,
            "execution_status": self.execution_status,
            "acquired_paths": list(self.acquired_paths),
            "acquired_file_count": self.acquired_file_count,
            "acquired_size_bytes": self.acquired_size_bytes,
            "checksums": dict(self.checksums or {}),
            "skipped_files": list(self.skipped_files),
            "errors": list(self.errors),
            "bids_metadata_summary": dict(self.bids_metadata_summary) if self.bids_metadata_summary else None,
            "dataset_record_paths": list(self.dataset_record_paths),
            "artifact_record_paths": list(self.artifact_record_paths),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetAcquisitionManifestV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            manifest_id=d.get("manifest_id", ""),
            plan_id=d.get("plan_id", ""),
            candidate_id=d.get("candidate_id", ""),
            source_catalog=d.get("source_catalog", ""),
            source_dataset_id=d.get("source_dataset_id", ""),
            execution_status=d.get("execution_status", "planned_only"),
            acquired_paths=list(d.get("acquired_paths") or []),
            acquired_file_count=int(d.get("acquired_file_count") or 0),
            acquired_size_bytes=int(d.get("acquired_size_bytes") or 0),
            checksums=dict(d.get("checksums") or {}),
            skipped_files=list(d.get("skipped_files") or []),
            errors=list(d.get("errors") or []),
            bids_metadata_summary=d.get("bids_metadata_summary"),
            dataset_record_paths=list(d.get("dataset_record_paths") or []),
            artifact_record_paths=list(d.get("artifact_record_paths") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit", ""),
            risks=list(d.get("risks") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetAcquisitionManifestV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_manifest(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from dataset_acquisition.validation import DatasetAcquisitionValidationError

            raise DatasetAcquisitionValidationError("; ".join(errors))
