"""BatchRunManifestV1 -- one batch of `PipelineJobV1` jobs created (and,
optionally, run) together from a list of `ReportPipelineSpecV1` files.
`job_runner.batch.create_batch_from_specs`/`run_batch` build on this
schema; the schema itself performs no I/O.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from job_runner.validation import validate_batch_run_manifest

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_batch_id(*, jobs_root: str, batch_name: str, spec_paths: list[str], created_at: str) -> str:
    """A batch is an execution event (creating one from the same spec
    list twice must produce two independently trackable batches, the
    same reasoning as `job_runner.job.compute_job_id`) -- `created_at` is
    deliberately included in the hash basis."""
    basis = {
        "jobs_root": jobs_root, "batch_name": batch_name,
        "spec_paths": sorted(spec_paths or []), "created_at": created_at,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class BatchRunManifestValidationError(ValueError):
    """Raised when a `BatchRunManifestV1` fails structural validation."""


@dataclass
class BatchRunManifestV1:
    schema_version: str = _SCHEMA_VERSION
    batch_id: str = ""
    batch_name: str = ""
    spec_paths: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    jobs_root: str = ""
    requested_outputs: list[str] = field(default_factory=lambda: ["report_pack"])
    created_at: str = ""
    run_started_at: Optional[str] = None
    run_completed_at: Optional[str] = None
    batch_status: str = "created"
    job_result_paths: list[str] = field(default_factory=list)
    completed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, jobs_root: str, spec_paths: list[str], batch_name: str = "",
        requested_outputs: Optional[list[str]] = None, _now: Optional[datetime] = None, **kwargs: Any,
    ) -> "BatchRunManifestV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        kwargs["job_ids"] = list(kwargs.get("job_ids") or [])
        spec_paths = list(spec_paths or [])
        requested_outputs = list(requested_outputs or ["report_pack"])
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        batch_id = compute_batch_id(jobs_root=jobs_root, batch_name=batch_name, spec_paths=spec_paths, created_at=ts)
        return cls(
            batch_id=batch_id, batch_name=batch_name, spec_paths=spec_paths, jobs_root=jobs_root,
            requested_outputs=requested_outputs, created_at=ts, **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_batch_id(
            jobs_root=self.jobs_root, batch_name=self.batch_name, spec_paths=self.spec_paths,
            created_at=self.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "batch_name": self.batch_name,
            "spec_paths": list(self.spec_paths),
            "job_ids": list(self.job_ids),
            "jobs_root": self.jobs_root,
            "requested_outputs": list(self.requested_outputs),
            "created_at": self.created_at,
            "run_started_at": self.run_started_at,
            "run_completed_at": self.run_completed_at,
            "batch_status": self.batch_status,
            "job_result_paths": list(self.job_result_paths),
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "blocked_count": self.blocked_count,
            "skipped_count": self.skipped_count,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BatchRunManifestV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            batch_id=d.get("batch_id", ""),
            batch_name=d.get("batch_name", ""),
            spec_paths=list(d.get("spec_paths") or []),
            job_ids=list(d.get("job_ids") or []),
            jobs_root=d.get("jobs_root", ""),
            requested_outputs=list(d.get("requested_outputs") or ["report_pack"]),
            created_at=d.get("created_at", ""),
            run_started_at=d.get("run_started_at"),
            run_completed_at=d.get("run_completed_at"),
            batch_status=d.get("batch_status", "created"),
            job_result_paths=list(d.get("job_result_paths") or []),
            completed_count=int(d.get("completed_count", 0)),
            failed_count=int(d.get("failed_count", 0)),
            blocked_count=int(d.get("blocked_count", 0)),
            skipped_count=int(d.get("skipped_count", 0)),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "BatchRunManifestV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_batch_run_manifest(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise BatchRunManifestValidationError("; ".join(errors))
