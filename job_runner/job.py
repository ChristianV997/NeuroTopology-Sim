"""PipelineJobV1 -- a tracked, file-backed job record wrapping one
`ReportPipelineSpecV1` execution.

A job is inherently an *execution event*, not a pure request identity:
resubmitting the identical spec twice must produce two distinct jobs
(different attempts, different output directories, independently
trackable status) -- so `job_id` deliberately includes `created_at` in
its hash basis, the same "documents one execution event" precedent
`workflows.report_pipeline.compute_run_id`/
`adapters.*_feature_recipe_schema.compute_manifest_id` already
established in this repository. This is a documented departure from the
purely content-addressed `pipeline_id`/`report_pack_id`/`html_pack_id`
convention (those identify a *request*, not an *attempt*) -- see
docs/job_runner.md#job-id-tradeoff.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from job_runner.validation import validate_pipeline_job

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_job_id(
    *, pipeline_identity: str, requested_outputs: list[str], output_root: str, created_at: str,
) -> str:
    """Stable sha256[:16] over the job's identity fields -- `created_at`
    is deliberately included (see module docstring). `pipeline_identity`
    is the embedded spec's own `pipeline_id` when a spec dict is
    embedded, or the raw `pipeline_spec_path` string otherwise -- either
    way it is *some* stable handle on "which request", combined here with
    "when" to produce a per-attempt identity."""
    basis = {
        "pipeline_identity": pipeline_identity,
        "requested_outputs": sorted(requested_outputs or []),
        "output_root": output_root,
        "created_at": created_at,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class PipelineJobValidationError(ValueError):
    """Raised when a `PipelineJobV1` fails structural validation."""


@dataclass
class PipelineJobV1:
    schema_version: str = _SCHEMA_VERSION
    job_id: str = ""
    job_name: str = ""
    pipeline_spec_path: Optional[str] = None
    pipeline_spec: dict[str, Any] = field(default_factory=dict)
    requested_outputs: list[str] = field(default_factory=lambda: ["report_pack"])
    job_status: str = "created"
    priority: int = 0
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_root: str = ""
    lock_path: str = ""
    attempts: int = 0
    max_attempts: int = 1
    error_summary: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        output_root: str,
        pipeline_spec_path: Optional[str] = None,
        pipeline_spec: Optional[dict[str, Any]] = None,
        requested_outputs: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "PipelineJobV1":
        pipeline_spec = dict(pipeline_spec or {})
        requested_outputs = list(requested_outputs or ["report_pack"])
        # Normalize an explicitly-passed metadata=None (e.g. from
        # JobStore.create_job's own Optional default) to {} here, so an
        # in-memory job matches what to_dict()/from_dict() always produce
        # (to_dict() already does `dict(self.metadata or {})`).
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        pipeline_identity = pipeline_spec.get("pipeline_id") or pipeline_spec_path or ""
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        job_id = compute_job_id(
            pipeline_identity=pipeline_identity, requested_outputs=requested_outputs,
            output_root=output_root, created_at=ts,
        )
        return cls(
            job_id=job_id, output_root=output_root, pipeline_spec_path=pipeline_spec_path,
            pipeline_spec=pipeline_spec, requested_outputs=requested_outputs, created_at=ts, **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "pipeline_spec_path": self.pipeline_spec_path,
            "pipeline_spec": dict(self.pipeline_spec or {}),
            "requested_outputs": list(self.requested_outputs),
            "job_status": self.job_status,
            "priority": self.priority,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_root": self.output_root,
            "lock_path": self.lock_path,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "error_summary": self.error_summary,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineJobV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            job_id=d.get("job_id", ""),
            job_name=d.get("job_name", ""),
            pipeline_spec_path=d.get("pipeline_spec_path"),
            pipeline_spec=dict(d.get("pipeline_spec") or {}),
            requested_outputs=list(d.get("requested_outputs") or ["report_pack"]),
            job_status=d.get("job_status", "created"),
            priority=int(d.get("priority", 0)),
            created_at=d.get("created_at", ""),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            output_root=d.get("output_root", ""),
            lock_path=d.get("lock_path", ""),
            attempts=int(d.get("attempts", 0)),
            max_attempts=int(d.get("max_attempts", 1)),
            error_summary=d.get("error_summary", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "PipelineJobV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_pipeline_job(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise PipelineJobValidationError("; ".join(errors))
