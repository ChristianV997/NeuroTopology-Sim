"""`create_batch_from_specs`/`run_batch` -- batch creation and execution
of many `PipelineJobV1` jobs from a list of `ReportPipelineSpecV1` files.
Reuses `job_runner.store.JobStore.create_job` (one call per spec) and
`job_runner.runner.run_pipeline_job` unmodified -- this module contains
no pipeline logic of its own and never writes to an input spec file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from job_runner.batch_manifest import BatchRunManifestV1
from job_runner.store import JobLockError, JobStore

_BATCH_MANIFEST_FILENAME = "BatchRunManifest.json"

_BATCH_LIMITATIONS: list[str] = [
    "BatchRunManifestV1 only tracks execution of job_runner.runner.run_pipeline_job for the jobs it "
    "created -- it contains no scientific logic of its own, mutates no seed registry, and never writes to "
    "an input ReportPipelineSpecV1 file.",
]


def _batches_dir(jobs_root: Union[str, Path]) -> Path:
    return Path(jobs_root) / "batches"


def batch_manifest_path(jobs_root: Union[str, Path], batch_id: str) -> Path:
    return _batches_dir(jobs_root) / batch_id / _BATCH_MANIFEST_FILENAME


def create_batch_from_specs(
    spec_paths: list[str], jobs_root: Union[str, Path], *,
    requested_outputs: Optional[list[str]] = None, batch_name: str = "",
) -> BatchRunManifestV1:
    """Creates one `PipelineJobV1` per spec path via
    `JobStore.create_job(spec_path=...)` -- every spec is only ever
    opened for reading; never runs anything. Fails closed (raises) if any
    spec path is missing or structurally invalid, exactly as
    `JobStore.create_job` already does for a single spec -- a partially
    created batch is never left behind, since job creation happens before
    the batch manifest itself is written."""
    store = JobStore(jobs_root)
    job_ids: list[str] = []
    for spec_path in spec_paths:
        job = store.create_job(
            spec_path=str(spec_path), requested_outputs=requested_outputs,
            provenance=f"Created via job_runner.batch.create_batch_from_specs (batch_name={batch_name!r}).",
        )
        job_ids.append(job.job_id)

    manifest = BatchRunManifestV1.make(
        jobs_root=str(jobs_root), spec_paths=[str(p) for p in spec_paths], batch_name=batch_name,
        requested_outputs=requested_outputs, job_ids=job_ids, batch_status="created",
        limitations=list(_BATCH_LIMITATIONS),
        provenance=f"Produced by job_runner.batch.create_batch_from_specs for {len(spec_paths)} spec(s).",
    )
    manifest.write_json(batch_manifest_path(jobs_root, manifest.batch_id))
    return manifest


def run_batch(
    batch_manifest_path_: Union[str, Path], *, max_jobs: Optional[int] = None, dry_run: bool = False,
) -> BatchRunManifestV1:
    """Runs only the jobs `create_batch_from_specs` created for this
    batch (by `job_ids`, never a queue-wide scan) via
    `job_runner.runner.run_pipeline_job`, one at a time. Never crashes on
    a per-job failure or lock conflict -- continues to the next job in
    the batch. A job already blocked/cancelled before this call is
    counted but never executed."""
    from job_runner.runner import run_pipeline_job

    path = Path(batch_manifest_path_)
    manifest = BatchRunManifestV1.from_json(path.read_text(encoding="utf-8"))
    store = JobStore(manifest.jobs_root)

    manifest.run_started_at = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        manifest.batch_status = "running"

    job_ids = manifest.job_ids if max_jobs is None else manifest.job_ids[: max(0, max_jobs)]
    completed = failed = blocked = skipped = 0
    result_paths: list[str] = []

    if not dry_run:
        for job_id in job_ids:
            try:
                job = store.load_job(job_id)
            except Exception:  # noqa: BLE001 -- a missing/corrupt job record must not stop the batch
                skipped += 1
                continue

            if job.job_status == "blocked":
                blocked += 1
                continue
            if job.job_status not in ("created", "queued"):
                # covers "cancelled" (rule 11: never executed) and any
                # already-running/terminal status this batch didn't itself set.
                skipped += 1
                continue

            try:
                result = run_pipeline_job(job, store=store)
            except JobLockError:
                skipped += 1
                continue
            except Exception:  # noqa: BLE001 -- a single bad job must never stop the rest of the batch
                failed += 1
                continue

            result_paths.append(str(store.result_path(job_id)))
            if result.job_status == "failed":
                failed += 1
            elif result.job_status in ("completed", "completed_with_warnings"):
                completed += 1
            else:
                skipped += 1

    manifest.run_completed_at = datetime.now(timezone.utc).isoformat()
    manifest.job_result_paths = result_paths
    manifest.completed_count = completed
    manifest.failed_count = failed
    manifest.blocked_count = blocked
    manifest.skipped_count = skipped

    total = len(job_ids)
    if dry_run:
        manifest.batch_status = "queued"
    elif total == 0:
        manifest.batch_status = "completed"
    elif completed == total:
        manifest.batch_status = "completed"
    elif failed == total:
        manifest.batch_status = "failed"
    elif blocked == total:
        manifest.batch_status = "blocked"
    else:
        manifest.batch_status = "completed_with_failures"

    manifest.write_json(path)
    return manifest
