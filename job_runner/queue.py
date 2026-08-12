"""JobQueueStateV1 -- a read-only snapshot of `outputs/jobs/`, and the
pure scanning/selection functions `job_runner.worker`/`job_runner.batch`
build on.

Scanning never executes a job and never mutates a `PipelineJob.json` --
it only reads. `queued_job_ids` deliberately buckets together
`job_status in {"created", "queued"}`: nothing in this repository's
`job_runner.store` ever transitions a job to `"queued"` today
(`create_job` always writes `job_status="created"`), so from a queue's
point of view a freshly created job and an explicitly queued one are the
same kind of pending work -- both are eligible for
`job_runner.worker`/`job_runner.batch`'s selection.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from job_runner.job import PipelineJobV1
from job_runner.store import JOB_FILENAME, JobStore
from job_runner.validation import validate_job_queue_state

_SCHEMA_VERSION = "1"

# A job whose job_status is not yet a terminal/running state is pending
# work -- eligible for selection by job_runner.worker/job_runner.batch.
PENDING_STATUSES: frozenset[str] = frozenset({"created", "queued"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_queue_id(*, jobs_root: str, last_scan_at: str, total_jobs: int) -> str:
    """A queue state is a point-in-time scan, not a request -- so, like
    `job_id`, its id deliberately includes the scan timestamp in its hash
    basis (documents one scan event, not a stable request identity)."""
    basis = {"jobs_root": jobs_root, "last_scan_at": last_scan_at, "total_jobs": total_jobs}
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class JobQueueStateValidationError(ValueError):
    """Raised when a `JobQueueStateV1` fails structural validation."""


@dataclass
class JobQueueStateV1:
    schema_version: str = _SCHEMA_VERSION
    queue_id: str = ""
    jobs_root: str = ""
    queued_job_ids: list[str] = field(default_factory=list)
    running_job_ids: list[str] = field(default_factory=list)
    completed_job_ids: list[str] = field(default_factory=list)
    failed_job_ids: list[str] = field(default_factory=list)
    blocked_job_ids: list[str] = field(default_factory=list)
    cancelled_job_ids: list[str] = field(default_factory=list)
    total_jobs: int = 0
    last_scan_at: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    _BUCKET_FIELDS = (
        "queued_job_ids", "running_job_ids", "completed_job_ids",
        "failed_job_ids", "blocked_job_ids", "cancelled_job_ids",
    )

    @classmethod
    def make(cls, *, jobs_root: str, _now: Optional[datetime] = None, **kwargs: Any) -> "JobQueueStateV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        for name in cls._BUCKET_FIELDS:
            kwargs[name] = list(kwargs.get(name) or [])
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        total_jobs = kwargs.pop("total_jobs", None)
        if total_jobs is None:
            total_jobs = sum(len(kwargs[name]) for name in cls._BUCKET_FIELDS)
        queue_id = compute_queue_id(jobs_root=jobs_root, last_scan_at=ts, total_jobs=total_jobs)
        return cls(queue_id=queue_id, jobs_root=jobs_root, total_jobs=total_jobs, last_scan_at=ts, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "queue_id": self.queue_id,
            "jobs_root": self.jobs_root,
            "queued_job_ids": list(self.queued_job_ids),
            "running_job_ids": list(self.running_job_ids),
            "completed_job_ids": list(self.completed_job_ids),
            "failed_job_ids": list(self.failed_job_ids),
            "blocked_job_ids": list(self.blocked_job_ids),
            "cancelled_job_ids": list(self.cancelled_job_ids),
            "total_jobs": self.total_jobs,
            "last_scan_at": self.last_scan_at,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobQueueStateV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            queue_id=d.get("queue_id", ""),
            jobs_root=d.get("jobs_root", ""),
            queued_job_ids=list(d.get("queued_job_ids") or []),
            running_job_ids=list(d.get("running_job_ids") or []),
            completed_job_ids=list(d.get("completed_job_ids") or []),
            failed_job_ids=list(d.get("failed_job_ids") or []),
            blocked_job_ids=list(d.get("blocked_job_ids") or []),
            cancelled_job_ids=list(d.get("cancelled_job_ids") or []),
            total_jobs=int(d.get("total_jobs", 0)),
            last_scan_at=d.get("last_scan_at", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "JobQueueStateV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_job_queue_state(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise JobQueueStateValidationError("; ".join(errors))


def _iter_job_files(jobs_root: Union[str, Path]):
    store = JobStore(jobs_root)
    if not store.jobs_root.exists():
        return
    for job_json in sorted(store.jobs_root.glob(f"*/{JOB_FILENAME}")):
        yield job_json


def scan_job_queue(jobs_root: Union[str, Path], *, status_filter: Optional[str] = None) -> JobQueueStateV1:
    """Reads every `PipelineJob.json` under `jobs_root` and buckets it by
    status. Never executes anything, never writes a job file. An
    unparseable job file is skipped and recorded in
    `metadata["scan_warnings"]` -- unlike `JobStore.list_jobs` (optimized
    for the common case, drops silently), a queue scan should surface a
    corrupt job file rather than hide it."""
    buckets: dict[str, list[str]] = {name: [] for name in JobQueueStateV1._BUCKET_FIELDS}
    warnings: list[str] = []

    for job_json in _iter_job_files(jobs_root):
        try:
            job = PipelineJobV1.from_json(job_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"could not parse {job_json}: {exc}")
            continue
        if status_filter is not None and job.job_status != status_filter:
            continue
        if job.job_status in PENDING_STATUSES:
            buckets["queued_job_ids"].append(job.job_id)
        elif job.job_status == "running":
            buckets["running_job_ids"].append(job.job_id)
        elif job.job_status in {"completed", "completed_with_warnings"}:
            buckets["completed_job_ids"].append(job.job_id)
        elif job.job_status == "failed":
            buckets["failed_job_ids"].append(job.job_id)
        elif job.job_status == "blocked":
            buckets["blocked_job_ids"].append(job.job_id)
        elif job.job_status == "cancelled":
            buckets["cancelled_job_ids"].append(job.job_id)

    return JobQueueStateV1.make(
        jobs_root=str(jobs_root),
        **buckets,
        limitations=[
            "JobQueueStateV1 is a read-only snapshot -- scanning never executes a job or mutates a "
            "PipelineJob.json.",
        ],
        provenance=f"Produced by job_runner.queue.scan_job_queue over jobs_root={jobs_root!r}.",
        metadata={"scan_warnings": warnings} if warnings else {},
    )


def select_next_jobs(
    jobs_root: Union[str, Path], *, max_jobs: int = 1, statuses: tuple[str, ...] = ("queued", "created"),
) -> list[PipelineJobV1]:
    """Returns up to `max_jobs` `PipelineJobV1` records eligible to run,
    ordered deterministically by `(-priority, created_at, job_id)` --
    higher priority first, ties broken by earliest creation, then by
    job_id. `running`/`completed`/`completed_with_warnings`/`failed`/
    `cancelled`/`blocked` jobs are never selected regardless of
    `statuses` -- a cancelled or blocked job must never be executed, and
    a running job already has its own lock held by another attempt."""
    allowed = frozenset(statuses) & PENDING_STATUSES
    if not allowed:
        return []

    candidates: list[PipelineJobV1] = []
    for job_json in _iter_job_files(jobs_root):
        try:
            job = PipelineJobV1.from_json(job_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if job.job_status in allowed:
            candidates.append(job)

    candidates.sort(key=lambda j: (-j.priority, j.created_at, j.job_id))
    return candidates[: max(0, max_jobs)]
