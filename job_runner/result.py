"""PipelineJobResultV1 -- the outcome record of one `PipelineJobV1`
execution.

Content-addressed over the result's own identity fields
(`job_id`/`job_status`/`report_pack_id`/`html_pack_id`/`generated_files`)
-- unlike `job_id`, `result_id` does not need its own `created_at` in the
hash basis, since `job_id` (already embedded as an identity field here)
already anchors this result to a specific execution event. Two writes of
the *same finished outcome* for the same job therefore produce the same
`result_id`, which is the more useful property for a result object (a
caller re-reading a result after a crash-free re-run of the same
already-completed job should see it recognized as unchanged).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from job_runner.validation import validate_pipeline_job_result

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_result_id(
    *, job_id: str, job_status: str, report_pack_id: Optional[str], html_pack_id: Optional[str],
    generated_files: list[str],
) -> str:
    import hashlib

    basis = {
        "job_id": job_id, "job_status": job_status, "report_pack_id": report_pack_id,
        "html_pack_id": html_pack_id, "generated_files": sorted(generated_files or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class PipelineJobResultValidationError(ValueError):
    """Raised when a `PipelineJobResultV1` fails structural validation."""


@dataclass
class PipelineJobResultV1:
    schema_version: str = _SCHEMA_VERSION
    result_id: str = ""
    job_id: str = ""
    job_status: str = "completed"
    pipeline_id: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    report_pack_id: Optional[str] = None
    html_pack_id: Optional[str] = None
    output_root: str = ""
    pipeline_manifest_path: Optional[str] = None
    report_pack_path: Optional[str] = None
    html_pack_path: Optional[str] = None
    index_html_path: Optional[str] = None
    generated_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    repo_commit: Optional[str] = None
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        job_id: str,
        job_status: str = "completed",
        report_pack_id: Optional[str] = None,
        html_pack_id: Optional[str] = None,
        generated_files: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "PipelineJobResultV1":
        generated_files = list(generated_files or [])
        result_id = compute_result_id(
            job_id=job_id, job_status=job_status, report_pack_id=report_pack_id,
            html_pack_id=html_pack_id, generated_files=generated_files,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            result_id=result_id, job_id=job_id, job_status=job_status,
            report_pack_id=report_pack_id, html_pack_id=html_pack_id,
            generated_files=generated_files, created_at=ts, **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_result_id(
            job_id=self.job_id, job_status=self.job_status, report_pack_id=self.report_pack_id,
            html_pack_id=self.html_pack_id, generated_files=self.generated_files,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "job_id": self.job_id,
            "job_status": self.job_status,
            "pipeline_id": self.pipeline_id,
            "pipeline_run_id": self.pipeline_run_id,
            "report_pack_id": self.report_pack_id,
            "html_pack_id": self.html_pack_id,
            "output_root": self.output_root,
            "pipeline_manifest_path": self.pipeline_manifest_path,
            "report_pack_path": self.report_pack_path,
            "html_pack_path": self.html_pack_path,
            "index_html_path": self.index_html_path,
            "generated_files": list(self.generated_files),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineJobResultV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            result_id=d.get("result_id", ""),
            job_id=d.get("job_id", ""),
            job_status=d.get("job_status", "completed"),
            pipeline_id=d.get("pipeline_id"),
            pipeline_run_id=d.get("pipeline_run_id"),
            report_pack_id=d.get("report_pack_id"),
            html_pack_id=d.get("html_pack_id"),
            output_root=d.get("output_root", ""),
            pipeline_manifest_path=d.get("pipeline_manifest_path"),
            report_pack_path=d.get("report_pack_path"),
            html_pack_path=d.get("html_pack_path"),
            index_html_path=d.get("index_html_path"),
            generated_files=list(d.get("generated_files") or []),
            errors=list(d.get("errors") or []),
            warnings=list(d.get("warnings") or []),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            repo_commit=d.get("repo_commit"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "PipelineJobResultV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_pipeline_job_result(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise PipelineJobResultValidationError("; ".join(errors))
