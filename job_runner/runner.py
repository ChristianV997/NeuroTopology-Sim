"""`run_pipeline_job` -- executes one `PipelineJobV1` by calling
`workflows.report_pipeline.run_report_pipeline` (and, optionally,
`workflows.html_report_pack.render_html_report_pack`) unmodified.

This module contains no scientific logic, no feature extraction, and no
registry-mutation logic of its own -- every governed decision (registry
authorization, claim/evidence ceilings, banned-phrase enforcement) is
made by the modules it calls, exactly as it already was before this
milestone. See docs/job_runner.md.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from job_runner.job import PipelineJobV1
from job_runner.result import PipelineJobResultV1
from job_runner.store import JobLockError, JobStore

_REPO_ROOT = Path(__file__).resolve().parents[1]

_JOB_RUNNER_LIMITATIONS: list[str] = [
    "job_runner orchestrates workflows.report_pipeline.run_report_pipeline and "
    "workflows.html_report_pack.render_html_report_pack unmodified -- it contains no feature extraction, "
    "no raw EEG/fMRI signal processing, and no LLM call.",
    "This job result is not itself evidence -- it is a tracked record of one pipeline execution attempt, "
    "indexing the TransitionRecordV1/EvidenceBundleV1/EvidenceReportV1/ReportPackV1 artifacts the "
    "underlying modules already produced.",
]


def _repo_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _relative_path(path: Any) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def _read_json(path: Any) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = _REPO_ROOT / p
    return json.loads(p.read_text(encoding="utf-8"))


def run_pipeline_job(job: PipelineJobV1, *, store: Optional[JobStore] = None) -> PipelineJobResultV1:
    """Executes `job`, returns a `PipelineJobResultV1`, and persists both
    the updated job and the result via `store`. Raises only for
    caller-level problems that must never silently become a "failed"
    result: a structurally invalid job/spec (fix the job, don't retry it),
    or a lock conflict (another attempt is genuinely in progress right
    now). Every *execution*-time problem -- a missing input file, a
    denied registry use, an HTML rendering failure -- is instead recorded
    in the returned result, matching `workflows.report_pipeline.run_report_pipeline`'s
    own "fail into the manifest, don't crash" discipline."""
    from workflows.report_pipeline import ReportPipelineSpecV1, run_report_pipeline

    if store is None:
        jobs_root = Path(job.lock_path).parent.parent if job.lock_path else "outputs/jobs"
        store = JobStore(jobs_root)

    job.validate_or_raise()
    spec = ReportPipelineSpecV1.from_dict(job.pipeline_spec)
    spec.validate_or_raise()

    store.acquire_job_lock(job.job_id)
    try:
        started_at = datetime.now(timezone.utc).isoformat()
        job.job_status = "running"
        job.started_at = started_at
        job.attempts += 1
        store.save_job(job)

        errors: list[str] = []
        warnings: list[str] = []
        pipeline_run_id: Optional[str] = None
        pipeline_manifest_path: Optional[str] = None
        report_pack_path: Optional[str] = None
        report_pack_id: Optional[str] = None
        html_pack_path: Optional[str] = None
        html_pack_id: Optional[str] = None
        index_html_path: Optional[str] = None
        generated_files: list[str] = []
        job_status = "completed"
        is_dry_run = bool(spec.dry_run)

        try:
            manifest = run_report_pipeline(spec)
            pipeline_run_id = manifest.run_id
            pipeline_manifest_path = manifest.output_root and _relative_path(Path(manifest.output_root) / "PipelineRunManifest.json")

            if manifest.execution_status == "failed":
                job_status = "failed"
                errors.extend(manifest.errors)
            elif manifest.execution_status == "dry_run":
                job_status = "completed"
            else:
                if manifest.execution_status == "completed_with_warnings":
                    job_status = "completed_with_warnings"
                    warnings.extend(manifest.warnings)

                if manifest.report_pack_path:
                    report_pack_path = manifest.report_pack_path
                    try:
                        report_pack_doc = _read_json(manifest.report_pack_path)
                        report_pack_id = report_pack_doc.get("report_pack_id")
                    except (OSError, json.JSONDecodeError) as exc:
                        warnings.append(f"could not re-read ReportPack.json for report_pack_id: {exc}")
                    generated_files.append(manifest.report_pack_path)

                generated_files.extend(manifest.generated_feature_paths)
                generated_files.extend(manifest.generated_mapping_paths)
                generated_files.extend(manifest.transition_record_paths)
                generated_files.extend(manifest.phase_space_paths)
                generated_files.extend(manifest.evidence_bundle_paths)
                generated_files.extend(manifest.evidence_report_paths)

                html_meta = manifest.metadata.get("html_report_pack") if isinstance(manifest.metadata, dict) else None
                if html_meta:
                    html_pack_id = html_meta.get("html_pack_id")
                    index_html_path = html_meta.get("index_html_path")
                    html_pack_path = html_meta.get("html_pack_json_path")
                    if index_html_path:
                        generated_files.append(index_html_path)
                elif "html_report_pack" in job.requested_outputs and report_pack_path:
                    # The spec itself did not request HTML -- render it now,
                    # from the already-produced ReportPackV1, exactly as
                    # workflows.export_report_pack's own --include-html
                    # integration does.
                    from workflows.html_report_pack import HtmlReportPackError, render_html_report_pack

                    html_out = str(Path(manifest.output_root) / "html")
                    try:
                        html_pack = render_html_report_pack(
                            report_pack_path=report_pack_path, out_dir=html_out,
                            pipeline_manifest_path=pipeline_manifest_path,
                        )
                    except HtmlReportPackError as exc:
                        warnings.append(f"HTML report pack rendering failed (report pack itself is unaffected): {exc}")
                        job_status = "completed_with_warnings"
                    else:
                        html_pack_id = html_pack.html_pack_id
                        index_html_path = html_pack.index_html_path
                        html_pack_path = _relative_path(Path(html_out) / "HtmlReportPack.json")
                        generated_files.append(index_html_path)

        except Exception as exc:  # noqa: BLE001 -- fail into the result, never crash the job runner
            job_status = "failed"
            errors.append(str(exc))

        completed_at = datetime.now(timezone.utc).isoformat()

        result_metadata: dict[str, Any] = {"dry_run": is_dry_run}
        if is_dry_run:
            # A dry run must never claim report generation -- no
            # report_pack/html_pack id or path is ever set for one,
            # regardless of what requested_outputs asked for.
            report_pack_id = None
            report_pack_path = None
            html_pack_id = None
            html_pack_path = None
            index_html_path = None
            generated_files = []

        result = PipelineJobResultV1.make(
            job_id=job.job_id, job_status=job_status,
            pipeline_id=spec.pipeline_id, pipeline_run_id=pipeline_run_id,
            report_pack_id=report_pack_id, html_pack_id=html_pack_id,
            generated_files=sorted(set(generated_files)),
            output_root=job.output_root, pipeline_manifest_path=pipeline_manifest_path,
            report_pack_path=report_pack_path, html_pack_path=html_pack_path, index_html_path=index_html_path,
            errors=errors, warnings=warnings, started_at=started_at, completed_at=completed_at,
            repo_commit=_repo_commit(), limitations=list(_JOB_RUNNER_LIMITATIONS),
            provenance=f"Produced by job_runner.runner.run_pipeline_job for job_id={job.job_id} (attempt {job.attempts}).",
            metadata=result_metadata,
        )
        store.write_result(result)

        job.job_status = job_status
        job.completed_at = completed_at
        if job_status == "failed":
            job.error_summary = "; ".join(errors) or "pipeline execution failed"
        store.save_job(job)
        store.write_summary(job=job, result=result)
        return result
    finally:
        store.release_job_lock(job.job_id)
