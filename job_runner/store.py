"""Stdlib-only, file-backed job store for `PipelineJobV1`/`PipelineJobResultV1`.

Layout::

    outputs/jobs/<job_id>/
        PipelineJob.json
        PipelineJobResult.json   (only after a run attempt)
        PipelineJob.lock          (only while a run is in progress)
        logs/
            summary.json          (small, human-readable run summary)

Reuses `dataset_acquisition.store.validate_target_root` directly for
`jobs_root`/`output_root` safety -- the same `outputs/`/`data/`-only,
no-`..`-traversal check every module in this repository already uses.
Writes are atomic where practical (write-to-temp-then-`os.replace`, the
standard POSIX-portable stdlib pattern); concurrent execution of the same
job is prevented by an exclusive sentinel lock file created via
`os.open(..., os.O_CREAT | os.O_EXCL)`, which atomically fails if another
process already holds it -- no third-party lock library is used, per this
milestone's stdlib-first requirement (even though `filelock` happens to
already be installed in this environment).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

from dataset_acquisition.store import validate_target_root
from job_runner.job import PipelineJobV1
from job_runner.result import PipelineJobResultV1
from job_runner.validation import JobStoreError

_REPO_ROOT = Path(__file__).resolve().parents[1]

JOB_FILENAME = "PipelineJob.json"
RESULT_FILENAME = "PipelineJobResult.json"
LOCK_FILENAME = "PipelineJob.lock"
LOGS_SUBDIR = "logs"
SUMMARY_FILENAME = "summary.json"

DEFAULT_JOBS_ROOT = "outputs/jobs"


def _atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` atomically: write to a sibling temp file in
    the same directory, then `os.replace` -- on POSIX this is atomic, so a
    reader never observes a partially-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class JobLockError(JobStoreError):
    """Raised when a job's lock is already held by another run attempt."""


class JobStore:
    def __init__(self, jobs_root: Union[str, Path] = DEFAULT_JOBS_ROOT) -> None:
        self.jobs_root = validate_target_root(jobs_root)

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def job_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / JOB_FILENAME

    def result_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / RESULT_FILENAME

    def lock_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / LOCK_FILENAME

    def summary_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / LOGS_SUBDIR / SUMMARY_FILENAME

    # ── creation ────────────────────────────────────────────────────────

    def create_job(
        self,
        *,
        spec_path: Optional[Union[str, Path]] = None,
        spec_dict: Optional[dict[str, Any]] = None,
        output_root_override: Optional[str] = None,
        requested_outputs: Optional[list[str]] = None,
        job_name: str = "",
        priority: int = 0,
        max_attempts: int = 1,
        limitations: Optional[list[str]] = None,
        provenance: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> PipelineJobV1:
        """Creates (validates + writes) a new `PipelineJobV1`. Exactly one
        of `spec_path`/`spec_dict` is required. Never executes the
        pipeline -- see `job_runner.runner.run_pipeline_job`."""
        from workflows.report_pipeline import ReportPipelineSpecV1

        if bool(spec_path) == bool(spec_dict):
            raise JobStoreError("exactly one of spec_path or spec_dict is required")

        if spec_path is not None:
            resolved = Path(spec_path)
            if not resolved.is_absolute():
                resolved = _REPO_ROOT / resolved
            if not resolved.exists():
                raise JobStoreError(f"spec_path does not exist: {spec_path}")
            try:
                spec = ReportPipelineSpecV1.from_json(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise JobStoreError(f"spec_path is not valid JSON: {spec_path} ({exc})") from exc
            spec_path_str = str(spec_path)
        else:
            spec = ReportPipelineSpecV1.from_dict(spec_dict)
            spec_path_str = None

        if output_root_override is not None:
            spec.output_root = output_root_override
            spec.pipeline_id = spec.recompute_id()

        spec_errors = spec.validate()
        if spec_errors:
            raise JobStoreError(f"pipeline_spec failed validation: {'; '.join(spec_errors)}")

        job = PipelineJobV1.make(
            output_root=spec.output_root, pipeline_spec_path=spec_path_str, pipeline_spec=spec.to_dict(),
            requested_outputs=requested_outputs, job_name=job_name, priority=priority,
            max_attempts=max_attempts, job_status="created",
            limitations=limitations or ["This job wraps an existing ReportPipelineSpecV1 -- it contains no scientific logic of its own."],
            provenance=provenance or f"Created via job_runner.store.JobStore.create_job for spec output_root={spec.output_root!r}.",
            metadata=metadata,
        )
        # job_id is only known after .make() runs, so the lock path (which
        # is keyed by job_id) can only be filled in now.
        lock_path = self.lock_path(job.job_id)
        job.lock_path = str(lock_path.relative_to(_REPO_ROOT)) if self._under_repo(lock_path) else str(lock_path)
        job.validate_or_raise()

        _atomic_write_text(self.job_path(job.job_id), job.to_json() + "\n")
        return job

    # ── read / list / update ───────────────────────────────────────────

    def load_job(self, job_id_or_path: Union[str, Path]) -> PipelineJobV1:
        path = Path(job_id_or_path)
        if not path.name.endswith(".json"):
            path = self.job_path(str(job_id_or_path))
        if not path.is_absolute():
            path = _REPO_ROOT / path
        if not path.exists():
            raise JobStoreError(f"job not found: {job_id_or_path}")
        return PipelineJobV1.from_json(path.read_text(encoding="utf-8"))

    def load_result(self, job_id: str) -> Optional[PipelineJobResultV1]:
        path = self.result_path(job_id)
        if not path.exists():
            return None
        return PipelineJobResultV1.from_json(path.read_text(encoding="utf-8"))

    def list_jobs(self, *, status: Optional[str] = None) -> list[PipelineJobV1]:
        if not self.jobs_root.exists():
            return []
        jobs: list[PipelineJobV1] = []
        for job_json in sorted(self.jobs_root.glob(f"*/{JOB_FILENAME}")):
            try:
                job = PipelineJobV1.from_json(job_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if status is None or job.job_status == status:
                jobs.append(job)
        return jobs

    def save_job(self, job: PipelineJobV1) -> Path:
        job.validate_or_raise()
        path = self.job_path(job.job_id)
        _atomic_write_text(path, job.to_json() + "\n")
        return path

    def update_job_status(self, job_id: str, status: str, **extra_fields: Any) -> PipelineJobV1:
        job = self.load_job(job_id)
        job.job_status = status
        for key, value in extra_fields.items():
            setattr(job, key, value)
        self.save_job(job)
        return job

    def write_result(self, result: PipelineJobResultV1) -> Path:
        result.validate_or_raise()
        path = self.result_path(result.job_id)
        _atomic_write_text(path, result.to_json() + "\n")
        return path

    def write_summary(self, *, job: PipelineJobV1, result: Optional[PipelineJobResultV1]) -> Path:
        summary = {
            "job_id": job.job_id,
            "job_name": job.job_name,
            "job_status": job.job_status,
            "attempts": job.attempts,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "output_root": job.output_root,
        }
        if result is not None:
            summary.update({
                "result_id": result.result_id,
                "report_pack_id": result.report_pack_id,
                "html_pack_id": result.html_pack_id,
                "report_pack_path": result.report_pack_path,
                "index_html_path": result.index_html_path,
                "errors": result.errors,
                "warnings": result.warnings,
            })
        path = self.summary_path(job.job_id)
        _atomic_write_text(path, json.dumps(summary, indent=2, default=str) + "\n")
        return path

    # ── locking ─────────────────────────────────────────────────────────

    def acquire_job_lock(self, job_id: str) -> Path:
        """Creates an exclusive sentinel lock file for `job_id`. Raises
        `JobLockError` if another run attempt already holds it (or left a
        stale lock behind after a crash -- see `release_job_lock`)."""
        path = self.lock_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise JobLockError(f"job {job_id!r} is already locked (another run attempt in progress): {path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return path

    def release_job_lock(self, job_id: str) -> None:
        path = self.lock_path(job_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def is_locked(self, job_id: str) -> bool:
        return self.lock_path(job_id).exists()

    @staticmethod
    def _under_repo(path: Path) -> bool:
        try:
            path.resolve().relative_to(_REPO_ROOT)
            return True
        except ValueError:
            return False
