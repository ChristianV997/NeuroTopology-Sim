"""Campaign orchestration: ordering, workers, timeouts, resume, dry-run."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Union

from tools.benchmark_orchestration.executor import run_case_with_retries
from tools.benchmark_orchestration.json_util import dumps
from tools.benchmark_orchestration.schema import (
    MATRIX_SCHEMA_VERSION,
    TERMINAL_STATUSES,
    CampaignConfig,
    CampaignReport,
    CaseResult,
    CaseSpec,
    CaseStatus,
    MatrixSpec,
)

PathLike = Union[str, Path]

REPORT_SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "manifest.json"


def _atomic_write(path: Path, text: str) -> None:
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_manifest(path: PathLike) -> Dict[str, CaseResult]:
    """Load prior case results keyed by case_id (empty if missing)."""
    import json

    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    results: Dict[str, CaseResult] = {}
    for raw in data.get("results", []):
        status = CaseStatus(raw["status"])
        results[raw["case_id"]] = CaseResult(
            case_id=raw["case_id"],
            command=list(raw["command"]),
            input_configuration=dict(raw.get("input_configuration") or {}),
            status=status,
            duration_s=float(raw.get("duration_s") or 0.0),
            exit_code=raw.get("exit_code"),
            timed_out=bool(raw.get("timed_out")),
            stdout_ref=raw.get("stdout_ref"),
            stderr_ref=raw.get("stderr_ref"),
            checksum=raw.get("checksum"),
            memory_telemetry_ref=raw.get("memory_telemetry_ref"),
            attempts=int(raw.get("attempts") or 1),
            retries_used=int(raw.get("retries_used") or 0),
            error_message=raw.get("error_message"),
            dry_run=bool(raw.get("dry_run")),
        )
    return results


def write_manifest(path: PathLike, report: CampaignReport) -> None:
    """Persist the campaign report as the resume manifest (finite JSON)."""
    _atomic_write(Path(path), dumps(report.to_dict()) + "\n")


def _summarize(results: List[CaseResult], ordering: List[str], duration_s: float) -> Dict:
    counts = {s.value: 0 for s in CaseStatus}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    return {
        "total_cases": len(ordering),
        "recorded_results": len(results),
        "counts": counts,
        "duration_s": round(float(duration_s), 6),
        "any_timeout": any(r.status == CaseStatus.TIMEOUT for r in results),
        "any_failure": any(
            r.status
            in {
                CaseStatus.CORRECTNESS_FAILURE,
                CaseStatus.TIMEOUT,
                CaseStatus.CHILD_CRASH,
                CaseStatus.INFRASTRUCTURE_BLOCKED,
            }
            for r in results
        ),
    }


def _dry_run_result(spec: CaseSpec) -> CaseResult:
    return CaseResult(
        case_id=spec.case_id,
        command=list(spec.command),
        input_configuration=dict(spec.config),
        status=CaseStatus.NOT_RUN,
        duration_s=0.0,
        exit_code=None,
        timed_out=False,
        stdout_ref=None,
        stderr_ref=None,
        checksum=None,
        memory_telemetry_ref=spec.memory_telemetry_ref,
        attempts=0,
        retries_used=0,
        error_message="dry-run: not executed",
        dry_run=True,
    )


def _effective_timeout(spec: CaseSpec, config: CampaignConfig) -> int:
    if config.per_case_timeout_s is not None:
        return int(config.per_case_timeout_s)
    return int(spec.timeout_s)


def _effective_retries(spec: CaseSpec, config: CampaignConfig) -> int:
    if config.max_retries is not None:
        return int(config.max_retries)
    return int(spec.max_retries)


def run_campaign(
    matrix: MatrixSpec,
    config: CampaignConfig,
    *,
    output_dir: PathLike,
) -> CampaignReport:
    """Run (or dry-run / resume) a validated matrix under ``config`` limits.

    * One case per isolated subprocess (via :func:`run_case_with_retries`).
    * Worker pool size capped by ``config.max_workers`` (thread pool scheduling
      subprocesses; each case still gets its own process).
    * Total campaign timeout marks remaining cases ``NOT_RUN`` (never PASS).
    * Resume loads ``manifest.json`` and skips terminal statuses.
    * Does not modify repository source files.
    """
    if config.max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    if config.total_timeout_s is not None and config.total_timeout_s < 1:
        raise ValueError("total_timeout_s must be >= 1 when set")

    out = Path(output_dir)
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    manifest_path = out / MANIFEST_NAME

    ordering = [c.case_id for c in matrix.cases]
    by_id: Dict[str, CaseSpec] = {c.case_id: c for c in matrix.cases}

    prior: Dict[str, CaseResult] = {}
    resumed_from: Optional[str] = None
    if config.resume and manifest_path.exists():
        prior = load_manifest(manifest_path)
        resumed_from = str(manifest_path)

    results_map: Dict[str, CaseResult] = {}
    # Carry forward prior terminal results when resuming.
    for case_id, result in prior.items():
        if case_id in by_id and result.status in TERMINAL_STATUSES:
            results_map[case_id] = result

    pending: List[CaseSpec] = [
        by_id[cid] for cid in ordering if cid not in results_map
    ]

    start = time.monotonic()
    campaign_deadline: Optional[float] = None
    if config.total_timeout_s is not None:
        campaign_deadline = start + float(config.total_timeout_s)

    if config.dry_run:
        for spec in pending:
            results_map[spec.case_id] = _dry_run_result(spec)
        pending = []

    def _remaining_budget() -> Optional[float]:
        if campaign_deadline is None:
            return None
        return max(0.0, campaign_deadline - time.monotonic())

    # Execute pending cases with a bounded worker pool.
    idx = 0
    while idx < len(pending):
        budget = _remaining_budget()
        if budget is not None and budget <= 0:
            # Mark all remaining as NOT_RUN due to total timeout.
            for spec in pending[idx:]:
                results_map[spec.case_id] = CaseResult(
                    case_id=spec.case_id,
                    command=list(spec.command),
                    input_configuration=dict(spec.config),
                    status=CaseStatus.NOT_RUN,
                    duration_s=0.0,
                    exit_code=None,
                    timed_out=False,
                    stdout_ref=None,
                    stderr_ref=None,
                    checksum=None,
                    memory_telemetry_ref=spec.memory_telemetry_ref,
                    attempts=0,
                    retries_used=0,
                    error_message="campaign total_timeout_s exhausted before execution",
                )
            break

        # Schedule up to max_workers from the remaining queue.
        batch: List[CaseSpec] = []
        while idx < len(pending) and len(batch) < config.max_workers:
            batch.append(pending[idx])
            idx += 1

        def _job(spec: CaseSpec) -> CaseResult:
            # Re-check budget inside worker scheduling path.
            rem = _remaining_budget()
            case_timeout = _effective_timeout(spec, config)
            if rem is not None:
                if rem <= 0:
                    return CaseResult(
                        case_id=spec.case_id,
                        command=list(spec.command),
                        input_configuration=dict(spec.config),
                        status=CaseStatus.NOT_RUN,
                        duration_s=0.0,
                        exit_code=None,
                        timed_out=False,
                        stdout_ref=None,
                        stderr_ref=None,
                        checksum=None,
                        memory_telemetry_ref=spec.memory_telemetry_ref,
                        attempts=0,
                        retries_used=0,
                        error_message="campaign total_timeout_s exhausted before execution",
                    )
                case_timeout = max(1, min(case_timeout, int(rem)))
            return run_case_with_retries(
                spec,
                timeout_s=case_timeout,
                max_retries=_effective_retries(spec, config),
                work_dir=logs,
            )

        if config.max_workers == 1:
            for spec in batch:
                results_map[spec.case_id] = _job(spec)
                # Persist incrementally for crash-safe resume.
                _persist_partial(
                    matrix, config, ordering, results_map, out, start, resumed_from
                )
        else:
            with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
                futures = {pool.submit(_job, spec): spec.case_id for spec in batch}
                for fut in as_completed(futures):
                    result = fut.result()
                    results_map[result.case_id] = result
                    _persist_partial(
                        matrix, config, ordering, results_map, out, start, resumed_from
                    )

    duration = time.monotonic() - start
    ordered_results = [results_map[cid] for cid in ordering if cid in results_map]
    # Any case somehow missing → NOT_RUN
    for cid in ordering:
        if cid not in results_map:
            ordered_results.append(
                CaseResult(
                    case_id=cid,
                    command=list(by_id[cid].command),
                    input_configuration=dict(by_id[cid].config),
                    status=CaseStatus.NOT_RUN,
                    duration_s=0.0,
                    exit_code=None,
                    timed_out=False,
                    stdout_ref=None,
                    stderr_ref=None,
                    checksum=None,
                    memory_telemetry_ref=by_id[cid].memory_telemetry_ref,
                    attempts=0,
                    retries_used=0,
                    error_message="not executed",
                )
            )
    # Re-order strictly by matrix ordering.
    by_result = {r.case_id: r for r in ordered_results}
    ordered_results = [by_result[cid] for cid in ordering]

    report = CampaignReport(
        schema_version=REPORT_SCHEMA_VERSION,
        matrix_schema_version=matrix.schema_version or MATRIX_SCHEMA_VERSION,
        provenance_label=matrix.provenance_label,
        campaign=config.to_dict(),
        results=ordered_results,
        summary=_summarize(ordered_results, ordering, duration),
        ordering=ordering,
        resumed_from=resumed_from,
        dry_run=bool(config.dry_run),
    )
    write_manifest(manifest_path, report)
    return report


def _persist_partial(
    matrix: MatrixSpec,
    config: CampaignConfig,
    ordering: List[str],
    results_map: Dict[str, CaseResult],
    out: Path,
    start: float,
    resumed_from: Optional[str],
) -> None:
    duration = time.monotonic() - start
    partial = [results_map[cid] for cid in ordering if cid in results_map]
    report = CampaignReport(
        schema_version=REPORT_SCHEMA_VERSION,
        matrix_schema_version=matrix.schema_version,
        provenance_label=matrix.provenance_label,
        campaign=config.to_dict(),
        results=partial,
        summary=_summarize(partial, ordering, duration),
        ordering=ordering,
        resumed_from=resumed_from,
        dry_run=bool(config.dry_run),
    )
    write_manifest(out / MANIFEST_NAME, report)
