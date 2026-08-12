"""CLI for `job_runner.queue`/`job_runner.worker`/`job_runner.batch` --
scan the local job queue, run jobs under lock (once or in a bounded
loop), and create/run batches of jobs from many `ReportPipelineSpecV1`
files.

    python -m job_runner.export_worker scan --jobs-root outputs/jobs

    python -m job_runner.export_worker run-once --jobs-root outputs/jobs --max-jobs 1

    python -m job_runner.export_worker loop --jobs-root outputs/jobs \\
        --max-loops 3 --max-jobs-per-loop 1 --poll-interval-seconds 0

    python -m job_runner.export_worker create-batch --spec a.json --spec b.json \\
        --jobs-root outputs/jobs --requested-output report_pack --batch-name demo_batch

    python -m job_runner.export_worker run-batch --batch outputs/jobs/batches/<batch_id>/BatchRunManifest.json

This is a bounded, local, single-process worker -- not a distributed
queue and not a daemon by default (`loop` requires an explicit, bounded
`--max-loops`). See docs/job_worker.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from dataset_acquisition.store import TargetRootError
from job_runner.batch import create_batch_from_specs, run_batch
from job_runner.batch_manifest import BatchRunManifestValidationError
from job_runner.job import PipelineJobValidationError
from job_runner.queue import JobQueueStateValidationError, scan_job_queue
from job_runner.store import DEFAULT_JOBS_ROOT
from job_runner.validation import JobStoreError
from job_runner.worker import WorkerRunManifestValidationError, run_worker_loop, run_worker_once
from workflows.report_pipeline import ReportPipelineError, ReportPipelineValidationError

_PROG = "job_runner.export_worker"

_ALL_CLI_ERRORS = (
    JobStoreError, JobQueueStateValidationError, WorkerRunManifestValidationError,
    BatchRunManifestValidationError, PipelineJobValidationError, TargetRootError,
    ReportPipelineValidationError, ReportPipelineError, OSError, json.JSONDecodeError, ValueError,
)


def _queue_summary(state: Any) -> dict[str, Any]:
    return {
        "queue_id": state.queue_id,
        "jobs_root": state.jobs_root,
        "total_jobs": state.total_jobs,
        "queued": len(state.queued_job_ids),
        "running": len(state.running_job_ids),
        "completed": len(state.completed_job_ids),
        "failed": len(state.failed_job_ids),
        "blocked": len(state.blocked_job_ids),
        "cancelled": len(state.cancelled_job_ids),
    }


def _worker_summary(manifest: Any) -> dict[str, Any]:
    return {
        "worker_run_id": manifest.worker_run_id,
        "dry_run": manifest.dry_run,
        "jobs_selected": manifest.jobs_selected,
        "jobs_completed": manifest.jobs_completed,
        "jobs_failed": manifest.jobs_failed,
        "jobs_blocked": manifest.jobs_blocked,
        "jobs_skipped": manifest.jobs_skipped,
        "lock_conflicts": manifest.lock_conflicts,
        "result_paths": manifest.result_paths,
    }


def _batch_summary(manifest: Any) -> dict[str, Any]:
    return {
        "batch_id": manifest.batch_id,
        "batch_name": manifest.batch_name,
        "batch_status": manifest.batch_status,
        "job_ids": manifest.job_ids,
        "completed_count": manifest.completed_count,
        "failed_count": manifest.failed_count,
        "blocked_count": manifest.blocked_count,
        "skipped_count": manifest.skipped_count,
        "job_result_paths": manifest.job_result_paths,
    }


def _cmd_scan(args: argparse.Namespace) -> int:
    state = scan_job_queue(args.jobs_root)
    print(json.dumps(_queue_summary(state), indent=2, default=str))
    return 0


def _worker_run_failed(manifest: Any) -> bool:
    """Lock conflicts are reported, not fatal, unless every selected job
    hit one (per this CLI's documented behavior)."""
    if manifest.jobs_failed:
        return True
    if manifest.jobs_selected and len(manifest.lock_conflicts) == len(manifest.jobs_selected):
        return True
    return False


def _cmd_run_once(args: argparse.Namespace) -> int:
    manifest = run_worker_once(args.jobs_root, max_jobs=args.max_jobs, dry_run=args.dry_run)
    print(json.dumps(_worker_summary(manifest), indent=2, default=str))
    return 1 if _worker_run_failed(manifest) else 0


def _cmd_loop(args: argparse.Namespace) -> int:
    manifests = run_worker_loop(
        args.jobs_root, max_jobs_per_loop=args.max_jobs_per_loop, max_loops=args.max_loops,
        poll_interval_seconds=args.poll_interval_seconds, dry_run=args.dry_run,
    )
    total_selected = sum(len(m.jobs_selected) for m in manifests)
    total_lock_conflicts = sum(len(m.lock_conflicts) for m in manifests)
    summary = {
        "loops": len(manifests),
        "worker_run_ids": [m.worker_run_id for m in manifests],
        "jobs_completed": sum(len(m.jobs_completed) for m in manifests),
        "jobs_failed": sum(len(m.jobs_failed) for m in manifests),
        "jobs_blocked": sum(len(m.jobs_blocked) for m in manifests),
        "jobs_skipped": sum(len(m.jobs_skipped) for m in manifests),
        "lock_conflicts": total_lock_conflicts,
    }
    print(json.dumps(summary, indent=2, default=str))
    all_conflicted = bool(total_selected) and total_lock_conflicts == total_selected
    return 1 if (summary["jobs_failed"] or all_conflicted) else 0


def _cmd_create_batch(args: argparse.Namespace) -> int:
    manifest = create_batch_from_specs(
        args.spec, args.jobs_root, requested_outputs=args.requested_output or None,
        batch_name=args.batch_name or "",
    )
    print(json.dumps(_batch_summary(manifest), indent=2, default=str))
    return 0


def _cmd_run_batch(args: argparse.Namespace) -> int:
    manifest = run_batch(args.batch, max_jobs=args.max_jobs, dry_run=args.dry_run)
    print(json.dumps(_batch_summary(manifest), indent=2, default=str))
    return 1 if manifest.batch_status in ("failed", "completed_with_failures") else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=_PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="print current queue counts")
    p_scan.add_argument("--jobs-root", type=str, default=DEFAULT_JOBS_ROOT)
    p_scan.set_defaults(func=_cmd_scan)

    p_run_once = sub.add_parser("run-once", help="select and run up to --max-jobs queued/created jobs")
    p_run_once.add_argument("--jobs-root", type=str, default=DEFAULT_JOBS_ROOT)
    p_run_once.add_argument("--max-jobs", type=int, default=1)
    p_run_once.add_argument("--dry-run", action="store_true")
    p_run_once.set_defaults(func=_cmd_run_once)

    p_loop = sub.add_parser("loop", help="run a bounded number of worker loops")
    p_loop.add_argument("--jobs-root", type=str, default=DEFAULT_JOBS_ROOT)
    p_loop.add_argument("--max-loops", type=int, required=True, help="required and bounded -- no infinite daemon mode")
    p_loop.add_argument("--max-jobs-per-loop", type=int, default=1)
    p_loop.add_argument("--poll-interval-seconds", type=float, default=0)
    p_loop.add_argument("--dry-run", action="store_true")
    p_loop.set_defaults(func=_cmd_loop)

    p_create_batch = sub.add_parser("create-batch", help="create (but do not run) one job per spec")
    p_create_batch.add_argument("--spec", action="append", required=True, dest="spec")
    p_create_batch.add_argument("--jobs-root", type=str, default=DEFAULT_JOBS_ROOT)
    p_create_batch.add_argument(
        "--requested-output", action="append", choices=["report_pack", "html_report_pack", "json_manifests_only"],
    )
    p_create_batch.add_argument("--batch-name", type=str, default="")
    p_create_batch.set_defaults(func=_cmd_create_batch)

    p_run_batch = sub.add_parser("run-batch", help="run only the jobs a batch created")
    p_run_batch.add_argument("--batch", type=str, required=True)
    p_run_batch.add_argument("--max-jobs", type=int, default=None)
    p_run_batch.add_argument("--dry-run", action="store_true")
    p_run_batch.set_defaults(func=_cmd_run_batch)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except _ALL_CLI_ERRORS as exc:
        print(f"[{_PROG}] FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
