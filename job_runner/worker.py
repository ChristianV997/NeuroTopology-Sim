"""WorkerRunManifestV1 -- one bounded worker invocation over
`outputs/jobs/`. `run_worker_once`/`run_worker_loop` only call
`job_runner.queue.select_next_jobs` and
`job_runner.runner.run_pipeline_job` -- they contain no scientific logic
of their own and never mutate a seed registry.

This is a local, single-process, bounded worker, not a distributed queue
and not an always-on daemon: `run_worker_loop` requires an explicit,
bounded `max_loops` (there is no "run forever" mode in v1). See
docs/job_worker.md.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from job_runner.queue import select_next_jobs
from job_runner.store import JobLockError, JobStore
from job_runner.validation import (
    MAX_JOBS_CEILING,
    MAX_LOOPS_CEILING,
    MAX_POLL_INTERVAL_SECONDS_CEILING,
    validate_worker_run_manifest,
)

_SCHEMA_VERSION = "1"

_WORKER_LIMITATIONS: list[str] = [
    "job_runner.worker only calls job_runner.runner.run_pipeline_job for jobs already created by "
    "job_runner.store.create_job -- it contains no scientific logic of its own, mutates no seed registry, "
    "and downloads nothing.",
    "This is a local, single-process, bounded worker, not a distributed queue and not an always-on daemon.",
]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_worker_run_id(*, jobs_root: str, worker_id: str, started_at: str, max_jobs: int, dry_run: bool) -> str:
    """A worker run is an execution event -- like `job_id`, its id
    deliberately includes `started_at` in its hash basis."""
    basis = {
        "jobs_root": jobs_root, "worker_id": worker_id, "started_at": started_at,
        "max_jobs": max_jobs, "dry_run": bool(dry_run),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class WorkerRunManifestValidationError(ValueError):
    """Raised when a `WorkerRunManifestV1` fails structural validation."""


@dataclass
class WorkerRunManifestV1:
    schema_version: str = _SCHEMA_VERSION
    worker_run_id: str = ""
    jobs_root: str = ""
    worker_id: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None
    max_jobs: int = 1
    poll_interval_seconds: float = 0
    dry_run: bool = False
    jobs_seen: list[str] = field(default_factory=list)
    jobs_selected: list[str] = field(default_factory=list)
    jobs_completed: list[str] = field(default_factory=list)
    jobs_failed: list[str] = field(default_factory=list)
    jobs_blocked: list[str] = field(default_factory=list)
    jobs_skipped: list[str] = field(default_factory=list)
    lock_conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_paths: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls, *, jobs_root: str, worker_id: Optional[str] = None, max_jobs: int = 1,
        poll_interval_seconds: float = 0, dry_run: bool = False, _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "WorkerRunManifestV1":
        kwargs["metadata"] = dict(kwargs.get("metadata") or {})
        worker_id = worker_id or uuid.uuid4().hex[:12]
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        worker_run_id = compute_worker_run_id(
            jobs_root=jobs_root, worker_id=worker_id, started_at=ts, max_jobs=max_jobs, dry_run=dry_run,
        )
        return cls(
            worker_run_id=worker_run_id, jobs_root=jobs_root, worker_id=worker_id, started_at=ts,
            max_jobs=max_jobs, poll_interval_seconds=poll_interval_seconds, dry_run=dry_run, **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "worker_run_id": self.worker_run_id,
            "jobs_root": self.jobs_root,
            "worker_id": self.worker_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "max_jobs": self.max_jobs,
            "poll_interval_seconds": self.poll_interval_seconds,
            "dry_run": self.dry_run,
            "jobs_seen": list(self.jobs_seen),
            "jobs_selected": list(self.jobs_selected),
            "jobs_completed": list(self.jobs_completed),
            "jobs_failed": list(self.jobs_failed),
            "jobs_blocked": list(self.jobs_blocked),
            "jobs_skipped": list(self.jobs_skipped),
            "lock_conflicts": list(self.lock_conflicts),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "result_paths": list(self.result_paths),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkerRunManifestV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            worker_run_id=d.get("worker_run_id", ""),
            jobs_root=d.get("jobs_root", ""),
            worker_id=d.get("worker_id", ""),
            started_at=d.get("started_at", ""),
            completed_at=d.get("completed_at"),
            max_jobs=int(d.get("max_jobs", 1)),
            poll_interval_seconds=d.get("poll_interval_seconds", 0),
            dry_run=bool(d.get("dry_run", False)),
            jobs_seen=list(d.get("jobs_seen") or []),
            jobs_selected=list(d.get("jobs_selected") or []),
            jobs_completed=list(d.get("jobs_completed") or []),
            jobs_failed=list(d.get("jobs_failed") or []),
            jobs_blocked=list(d.get("jobs_blocked") or []),
            jobs_skipped=list(d.get("jobs_skipped") or []),
            lock_conflicts=list(d.get("lock_conflicts") or []),
            errors=list(d.get("errors") or []),
            warnings=list(d.get("warnings") or []),
            result_paths=list(d.get("result_paths") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "WorkerRunManifestV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_worker_run_manifest(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise WorkerRunManifestValidationError("; ".join(errors))


def run_worker_once(
    jobs_root: Union[str, Path], *, max_jobs: int = 1, dry_run: bool = False, worker_id: Optional[str] = None,
) -> WorkerRunManifestV1:
    """Scans the queue, selects up to `max_jobs` created/queued jobs, and
    (unless `dry_run`) runs each one via `job_runner.runner.run_pipeline_job`
    -- one at a time, under that job's own lock. Never raises past a
    recoverable per-job failure or lock conflict; always continues to the
    next selected job."""
    from job_runner.runner import run_pipeline_job

    if not (1 <= max_jobs <= MAX_JOBS_CEILING):
        raise ValueError(f"max_jobs must be an integer in [1, {MAX_JOBS_CEILING}], got {max_jobs!r}")

    manifest = WorkerRunManifestV1.make(
        jobs_root=str(jobs_root), worker_id=worker_id, max_jobs=max_jobs, dry_run=dry_run,
        limitations=list(_WORKER_LIMITATIONS),
        provenance=f"Produced by job_runner.worker.run_worker_once over jobs_root={jobs_root!r}.",
    )

    store = JobStore(jobs_root)
    selected = select_next_jobs(jobs_root, max_jobs=max_jobs, statuses=("queued", "created"))
    manifest.jobs_seen = [job.job_id for job in selected]
    manifest.jobs_selected = [job.job_id for job in selected]

    if not dry_run:
        for job in selected:
            if job.attempts >= job.max_attempts:
                # Defensive: a "created"/"queued" job normally has
                # attempts=0, but a job manually reset to "queued" after
                # already exhausting its attempts must not be re-run.
                manifest.jobs_blocked.append(job.job_id)
                manifest.warnings.append(
                    f"{job.job_id}: already at max_attempts={job.max_attempts}, not re-run"
                )
                continue
            try:
                result = run_pipeline_job(job, store=store)
            except JobLockError as exc:
                manifest.lock_conflicts.append(job.job_id)
                manifest.warnings.append(f"{job.job_id}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 -- a single bad job must never stop the rest
                manifest.jobs_failed.append(job.job_id)
                manifest.errors.append(f"{job.job_id}: {exc}")
                continue

            manifest.result_paths.append(str(store.result_path(job.job_id)))
            if result.job_status == "failed":
                manifest.jobs_failed.append(job.job_id)
            elif result.job_status in {"completed", "completed_with_warnings"}:
                manifest.jobs_completed.append(job.job_id)
            else:
                manifest.jobs_skipped.append(job.job_id)

    manifest.completed_at = datetime.now(timezone.utc).isoformat()
    return manifest


def run_worker_loop(
    jobs_root: Union[str, Path], *, max_jobs_per_loop: int = 1, max_loops: int = 1,
    poll_interval_seconds: float = 0, dry_run: bool = False, worker_id: Optional[str] = None,
) -> list[WorkerRunManifestV1]:
    """Runs `run_worker_once` up to `max_loops` times, sleeping
    `poll_interval_seconds` between loops. Always bounded -- `max_loops`
    is required and capped at `MAX_LOOPS_CEILING`; there is no infinite
    daemon mode. Returns one `WorkerRunManifestV1` per loop iteration
    (including loops that found no eligible jobs)."""
    if not (1 <= max_loops <= MAX_LOOPS_CEILING):
        raise ValueError(f"max_loops must be an integer in [1, {MAX_LOOPS_CEILING}], got {max_loops!r}")
    if not (0 <= poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS_CEILING):
        raise ValueError(
            f"poll_interval_seconds must be in [0, {MAX_POLL_INTERVAL_SECONDS_CEILING}], "
            f"got {poll_interval_seconds!r}"
        )

    worker_id = worker_id or uuid.uuid4().hex[:12]
    manifests: list[WorkerRunManifestV1] = []
    for i in range(max_loops):
        manifest = run_worker_once(jobs_root, max_jobs=max_jobs_per_loop, dry_run=dry_run, worker_id=worker_id)
        manifests.append(manifest)
        if i < max_loops - 1 and poll_interval_seconds:
            time.sleep(poll_interval_seconds)
    return manifests
