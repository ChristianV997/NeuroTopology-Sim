"""CLI for `job_runner` -- create, run, inspect, and list report-pipeline jobs.

    python -m job_runner.export_job create --spec pipeline_spec.json --out outputs/jobs \\
        --requested-output report_pack --requested-output html_report_pack

    python -m job_runner.export_job run --job outputs/jobs/<job_id>/PipelineJob.json

    python -m job_runner.export_job run-spec --spec pipeline_spec.json --out outputs/jobs \\
        --requested-output html_report_pack

    python -m job_runner.export_job status --job <job_id or path/to/PipelineJob.json>

    python -m job_runner.export_job list --jobs-root outputs/jobs --status completed

`create` only writes a `PipelineJobV1` -- it never executes the pipeline.
`run` executes exactly one already-created job. `run-spec` is `create`
immediately followed by `run` in one invocation. Every subcommand talks to
`job_runner.store.JobStore`/`job_runner.runner.run_pipeline_job` only --
it duplicates no pipeline logic. See docs/job_runner.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from dataset_acquisition.store import TargetRootError
from job_runner.job import PipelineJobValidationError
from job_runner.result import PipelineJobResultValidationError
from job_runner.runner import run_pipeline_job
from job_runner.store import DEFAULT_JOBS_ROOT, JobStore
from job_runner.validation import JobStoreError
from workflows.report_pipeline import ReportPipelineError, ReportPipelineValidationError

_PROG = "job_runner.export_job"
_REPO_ROOT = Path(__file__).resolve().parents[1]

_ALL_CLI_ERRORS = (
    JobStoreError, PipelineJobValidationError, PipelineJobResultValidationError,
    TargetRootError, ReportPipelineValidationError, ReportPipelineError,
    OSError, json.JSONDecodeError,
)


def _jobs_root_for(job_path_str: str, fallback: str) -> str:
    """Given a `--job` argument that names a `PipelineJob.json` path,
    return its grandparent directory as a repository-relative string
    (`validate_target_root` rejects absolute paths) -- falls back to
    `fallback` when `--job` is a bare job_id rather than a path."""
    path = Path(job_path_str)
    if not path.name.endswith(".json"):
        return fallback
    resolved = path if path.is_absolute() else (_REPO_ROOT / path)
    jobs_root = resolved.resolve().parent.parent
    try:
        return str(jobs_root.relative_to(_REPO_ROOT))
    except ValueError:
        return str(jobs_root)


def _job_summary(job: Any) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "job_status": job.job_status,
        "requested_outputs": job.requested_outputs,
        "attempts": job.attempts,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "output_root": job.output_root,
        "error_summary": job.error_summary,
    }


def _result_summary(result: Any) -> dict[str, Any]:
    return {
        "result_id": result.result_id,
        "job_id": result.job_id,
        "job_status": result.job_status,
        "report_pack_id": result.report_pack_id,
        "html_pack_id": result.html_pack_id,
        "report_pack_path": result.report_pack_path,
        "index_html_path": result.index_html_path,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def _cmd_create(args: argparse.Namespace) -> int:
    store = JobStore(args.out)
    job = store.create_job(
        spec_path=str(args.spec), requested_outputs=args.requested_output or None,
        job_name=args.job_name or "", priority=args.priority, max_attempts=args.max_attempts,
    )
    print(json.dumps({"job_path": str(store.job_path(job.job_id)), **_job_summary(job)}, indent=2, default=str))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    jobs_root = _jobs_root_for(args.job, args.jobs_root or DEFAULT_JOBS_ROOT)
    store = JobStore(jobs_root)
    job = store.load_job(args.job)
    result = run_pipeline_job(job, store=store)
    print(json.dumps(_result_summary(result), indent=2, default=str))
    return 1 if result.job_status == "failed" else 0


def _cmd_run_spec(args: argparse.Namespace) -> int:
    store = JobStore(args.out)
    job = store.create_job(
        spec_path=str(args.spec), requested_outputs=args.requested_output or None,
        job_name=args.job_name or "", priority=args.priority, max_attempts=args.max_attempts,
    )
    result = run_pipeline_job(job, store=store)
    print(json.dumps({"job_id": job.job_id, **_result_summary(result)}, indent=2, default=str))
    return 1 if result.job_status == "failed" else 0


def _cmd_status(args: argparse.Namespace) -> int:
    jobs_root = _jobs_root_for(args.job, DEFAULT_JOBS_ROOT)
    store = JobStore(jobs_root)
    job = store.load_job(args.job)
    output: dict[str, Any] = _job_summary(job)
    result = store.load_result(job.job_id)
    if result is not None:
        output["result"] = _result_summary(result)
    print(json.dumps(output, indent=2, default=str))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = JobStore(args.jobs_root)
    jobs = store.list_jobs(status=args.status)
    print(json.dumps([_job_summary(job) for job in jobs], indent=2, default=str))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=_PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="create (but do not execute) a job from a ReportPipelineSpecV1 file")
    p_create.add_argument("--spec", type=Path, required=True, help="ReportPipelineSpecV1 JSON file")
    p_create.add_argument("--out", type=str, default=DEFAULT_JOBS_ROOT, help="jobs root directory (default: %(default)s)")
    p_create.add_argument("--requested-output", action="append", choices=["report_pack", "html_report_pack", "json_manifests_only"])
    p_create.add_argument("--job-name", type=str, default="")
    p_create.add_argument("--priority", type=int, default=0)
    p_create.add_argument("--max-attempts", type=int, default=1)
    p_create.set_defaults(func=_cmd_create)

    p_run = sub.add_parser("run", help="execute one already-created job")
    p_run.add_argument("--job", type=str, required=True, help="job_id, or path to PipelineJob.json")
    p_run.add_argument("--jobs-root", type=str, default=None, help="jobs root (only needed if --job is a bare job_id)")
    p_run.set_defaults(func=_cmd_run)

    p_run_spec = sub.add_parser("run-spec", help="create and execute a job in one step")
    p_run_spec.add_argument("--spec", type=Path, required=True, help="ReportPipelineSpecV1 JSON file")
    p_run_spec.add_argument("--out", type=str, default=DEFAULT_JOBS_ROOT, help="jobs root directory (default: %(default)s)")
    p_run_spec.add_argument("--requested-output", action="append", choices=["report_pack", "html_report_pack", "json_manifests_only"])
    p_run_spec.add_argument("--job-name", type=str, default="")
    p_run_spec.add_argument("--priority", type=int, default=0)
    p_run_spec.add_argument("--max-attempts", type=int, default=1)
    p_run_spec.set_defaults(func=_cmd_run_spec)

    p_status = sub.add_parser("status", help="print the current status (and result, if any) of one job")
    p_status.add_argument("--job", type=str, required=True, help="job_id, or path to PipelineJob.json")
    p_status.set_defaults(func=_cmd_status)

    p_list = sub.add_parser("list", help="list jobs, optionally filtered by status")
    p_list.add_argument("--jobs-root", type=str, default=DEFAULT_JOBS_ROOT)
    p_list.add_argument("--status", type=str, default=None, choices=[
        "created", "queued", "running", "completed", "completed_with_warnings", "failed", "cancelled", "blocked",
    ])
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except _ALL_CLI_ERRORS as exc:
        print(f"[{_PROG}] FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
