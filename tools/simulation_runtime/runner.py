"""Simulation campaign runner enforcing bounded, isolated, and resumable execution.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from tools.simulation_runtime.atomic_io import (
    compute_config_hash,
    compute_sha256,
    get_git_commit,
    json_safe,
    write_atomic_json,
)
from tools.simulation_runtime.checkpoint import CampaignCheckpointManager
from tools.simulation_runtime.guards import (
    check_dependencies,
    check_disk_budget,
    check_memory_budget,
)
from tools.simulation_runtime.process_cleanup import (
    ProcessExecutionResult,
    run_isolated_process,
)
from tools.simulation_runtime.types import (
    CampaignManifest,
    CampaignState,
    Outcome,
    ResourcePolicy,
    UnitResult,
    WorkUnit,
    capture_environment_metadata,
    is_retryable_outcome,
)


class SimulationCampaignRunner:
    """Orchestrates the execution of a bounded simulation campaign.

    Enforces:
      - Manifest-first execution.
      - Sequential bounded execution by default (max_workers=1).
      - Configurable but strictly capped concurrency.
      - Atomic per-unit recording and incremental checkpointing.
      - Resume without recomputing terminal units.
      - Retry only for explicitly retryable infrastructure failures (network, disk, memory).
      - Immediate terminal stop for correctness failures and missing dependencies.
      - Subprocess isolation with process-tree cleanup on timeout or crash.
      - Transparent outcome categorization (no silent partial success).
    """

    def __init__(
        self,
        manifest: CampaignManifest,
        output_dir: Path | str,
        *,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.manifest = manifest
        self.output_dir = Path(output_dir).resolve()
        self.cancel_check = cancel_check or (lambda: False)
        self.checkpoint_manager = CampaignCheckpointManager(self.output_dir, self.manifest)

    def run(self, *, resume: bool = True) -> CampaignState:
        """Run or resume the campaign.

        Returns the final CampaignState.
        """
        start_time = time.monotonic()
        state, completed_ids = self.checkpoint_manager.initialize_or_resume(resume=resume)

        # Sort units deterministically by unit_id
        ordered_units = sorted(self.manifest.units, key=lambda u: u.unit_id)
        pending_units = [u for u in ordered_units if u.unit_id not in completed_ids]

        if not pending_units:
            # Already 100% completed
            self._write_final_summaries(state, time.monotonic() - start_time)
            return state

        workers = self.manifest.resource_policy.effective_workers()

        if workers == 1:
            # Deterministic sequential execution
            for unit in pending_units:
                if self.cancel_check():
                    self.checkpoint_manager.mark_cancelled(state)
                    break

                state.active_unit = unit.unit_id
                result = self._execute_unit_with_retries(unit)
                self.checkpoint_manager.record_unit_completed(state, result)

                if self.cancel_check():
                    self.checkpoint_manager.mark_cancelled(state)
                    break
        else:
            # Capped concurrent execution
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_unit = {
                    executor.submit(self._execute_unit_with_retries, unit): unit
                    for unit in pending_units
                }
                for future in as_completed(future_to_unit):
                    if self.cancel_check():
                        self.checkpoint_manager.mark_cancelled(state)
                        # Cancel pending futures
                        for f in future_to_unit:
                            f.cancel()
                        break

                    result = future.result()
                    self.checkpoint_manager.record_unit_completed(state, result)

        total_elapsed = time.monotonic() - start_time
        self._write_final_summaries(state, total_elapsed)
        return state

    def _execute_unit_with_retries(self, unit: WorkUnit) -> UnitResult:
        """Execute a single work unit with retry handling for infrastructure failures."""
        retry_count = 0
        max_retries = unit.max_retries if unit.retryable else 0

        while True:
            result = self._execute_single_attempt(unit, retry_count)
            if result.outcome == Outcome.PASS:
                return result

            # Check if failure is retryable
            if is_retryable_outcome(result.outcome) and retry_count < max_retries:
                retry_count += 1
                # Small exponential backoff
                time.sleep(min(0.2 * (2 ** retry_count), 2.0))
                continue

            # Non-retryable failure or exhausted retries
            return result

    def _execute_single_attempt(self, unit: WorkUnit, retry_count: int) -> UnitResult:
        """Perform one execution attempt for a work unit."""
        started_at = datetime.now(timezone.utc).isoformat()

        # 1. Dependency check
        if unit.dependencies:
            deps_ok, missing = check_dependencies(unit.dependencies)
            if not deps_ok:
                completed_at = datetime.now(timezone.utc).isoformat()
                return UnitResult(
                    unit_id=unit.unit_id,
                    outcome=Outcome.DEPENDENCY_MISSING,
                    status="FAILED",
                    exit_code=-1,
                    elapsed_s=0.0,
                    retry_count=retry_count,
                    stdout="",
                    stderr=f"Missing dependencies: {', '.join(missing)}",
                    error_message=f"Missing dependencies: {', '.join(missing)}",
                    peak_memory_bytes=None,
                    output_checksums={},
                    metrics=None,
                    started_at=started_at,
                    completed_at=completed_at,
                )

        # 2. Memory budget check
        mem_ok, mem_reason, _ = check_memory_budget(
            unit.estimated_memory_mb,
            self.manifest.resource_policy.max_memory_mb,
        )
        if not mem_ok:
            completed_at = datetime.now(timezone.utc).isoformat()
            return UnitResult(
                unit_id=unit.unit_id,
                outcome=Outcome.MEMORY_FAILURE,
                status="FAILED",
                exit_code=-1,
                elapsed_s=0.0,
                retry_count=retry_count,
                stdout="",
                stderr=mem_reason,
                error_message=mem_reason,
                peak_memory_bytes=None,
                output_checksums={},
                metrics=None,
                started_at=started_at,
                completed_at=completed_at,
            )

        # 3. Disk budget check
        disk_ok, disk_reason, _ = check_disk_budget(
            self.output_dir,
            unit.estimated_disk_mb,
            self.manifest.resource_policy.min_disk_free_mb,
        )
        if not disk_ok:
            completed_at = datetime.now(timezone.utc).isoformat()
            return UnitResult(
                unit_id=unit.unit_id,
                outcome=Outcome.DISK_FAILURE,
                status="FAILED",
                exit_code=-1,
                elapsed_s=0.0,
                retry_count=retry_count,
                stdout="",
                stderr=disk_reason,
                error_message=disk_reason,
                peak_memory_bytes=None,
                output_checksums={},
                metrics=None,
                started_at=started_at,
                completed_at=completed_at,
            )

        # 4. Execute isolated subprocess
        timeout_s = unit.timeout_s or self.manifest.resource_policy.default_timeout_s
        proc_result = run_isolated_process(
            unit.command,
            timeout_s=timeout_s,
            cwd=str(self.output_dir),
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        # 5. Classify outcome
        outcome, status, error_msg = self._classify_execution(unit, proc_result)

        # 6. Verify expected outputs and compute checksums
        output_checksums: Dict[str, str] = {}
        if outcome == Outcome.PASS:
            for out_rel in unit.expected_outputs:
                out_path = Path(out_rel)
                if not out_path.is_absolute():
                    out_path = self.output_dir / out_rel
                if not out_path.exists():
                    outcome = Outcome.CORRECTNESS_FAILURE
                    status = "FAILED"
                    error_msg = f"Declared output missing: {out_rel}"
                    break
                try:
                    output_checksums[out_rel] = compute_sha256(out_path)
                except Exception as exc:
                    outcome = Outcome.DISK_FAILURE
                    status = "FAILED"
                    error_msg = f"Failed to checksum output {out_rel}: {exc}"
                    break

        return UnitResult(
            unit_id=unit.unit_id,
            outcome=outcome,
            status=status,
            exit_code=proc_result.exit_code,
            elapsed_s=proc_result.elapsed_s,
            retry_count=retry_count,
            stdout=proc_result.stdout,
            stderr=proc_result.stderr,
            error_message=error_msg,
            peak_memory_bytes=proc_result.peak_rss_bytes,
            output_checksums=output_checksums,
            metrics=None,  # Only actual validated metrics; never placeholders
            started_at=started_at,
            completed_at=completed_at,
        )

    def _classify_execution(
        self,
        unit: WorkUnit,
        res: ProcessExecutionResult,
    ) -> Tuple[Outcome, str, Optional[str]]:
        """Classify child process outcome into distinct terminal categories."""
        if res.timed_out:
            return (
                Outcome.TIMEOUT,
                "TIMEOUT",
                f"Work unit timed out after {unit.timeout_s:.1f}s (process tree terminated)",
            )

        if res.exit_code == 0:
            return Outcome.PASS, "COMPLETED", None

        # Analyze error text and return code
        combined_err = f"{res.stderr}\n{res.stdout}".lower()

        if "memoryerror" in combined_err or "out of memory" in combined_err or res.exit_code in (137, -9):
            return Outcome.MEMORY_FAILURE, "FAILED", "Child process terminated due to out-of-memory"

        if (
            "connectionerror" in combined_err
            or "timeouterror" in combined_err
            or "network is unreachable" in combined_err
            or "socket.gaierror" in combined_err
        ):
            return Outcome.NETWORK_FAILURE, "FAILED", "Network infrastructure failure detected"

        if "no space left on device" in combined_err or "disk full" in combined_err or "errno 28" in combined_err:
            return Outcome.DISK_FAILURE, "FAILED", "Filesystem disk space failure detected"

        if "modulenotfounderror" in combined_err or "importerror" in combined_err or "no module named" in combined_err:
            return Outcome.DEPENDENCY_MISSING, "FAILED", f"Missing dependency in child environment: {res.stderr[:200]}"

        if "assertionerror" in combined_err or res.exit_code in (1, 2):
            return Outcome.CORRECTNESS_FAILURE, "FAILED", f"Correctness assertion failure (exit code {res.exit_code})"

        return Outcome.UNKNOWN_FAILURE, "FAILED", f"Non-zero exit code {res.exit_code}: {res.stderr[:200]}"

    def _write_final_summaries(self, state: CampaignState, total_elapsed_s: float) -> None:
        """Write campaign_summary.json and campaign_summary.md atomically."""
        summary_data = {
            "schema_version": "simulation_campaign_summary_v1",
            "campaign_id": self.manifest.campaign_id,
            "code_commit": self.manifest.code_commit,
            "configuration_hash": self.manifest.configuration_hash,
            "seed": self.manifest.seed,
            "is_complete": state.is_complete,
            "is_partial": state.is_partial,
            "cancelled": state.cancelled,
            "total_units": len(self.manifest.units),
            "total_elapsed_s": total_elapsed_s,
            "summary_by_outcome": state.summary,
            "units": [
                state.completed_units[u.unit_id].to_dict()
                if u.unit_id in state.completed_units
                else {
                    "unit_id": u.unit_id,
                    "outcome": Outcome.NOT_RUN.value,
                    "status": "NOT_RUN",
                    "exit_code": None,
                    "elapsed_s": 0.0,
                    "retry_count": 0,
                    "stdout": "",
                    "stderr": "",
                    "error_message": "Unit was not reached or executed before campaign termination",
                    "peak_memory_bytes": None,
                    "output_checksums": {},
                    "metrics": None,
                    "started_at": "",
                    "completed_at": "",
                }
                for u in self.manifest.units
            ],
            "environment": self.manifest.environment,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        json_path = self.output_dir / "campaign_summary.json"
        write_atomic_json(json_path, summary_data)

        md_path = self.output_dir / "campaign_summary.md"
        md_content = self._render_markdown_summary(summary_data)
        self._write_atomic_text(md_path, md_content)

    def _render_markdown_summary(self, data: Dict[str, Any]) -> str:
        """Render human-readable markdown report of the campaign."""
        lines = [
            f"# Simulation Campaign Summary: {data['campaign_id']}",
            "",
            f"- **Status**: {'COMPLETE' if data['is_complete'] else 'PARTIAL'}",
            f"- **Code Commit**: `{data['code_commit']}`",
            f"- **Configuration Hash**: `{data['configuration_hash'][:16]}...`",
            f"- **Total Units**: {data['total_units']}",
            f"- **Total Elapsed Time**: {data['total_elapsed_s']:.2f}s",
            f"- **Cancelled**: {data['cancelled']}",
            f"- **Generated At**: `{data['generated_at']}`",
            "",
            "## Outcome Breakdown",
            "",
            "| Outcome | Count |",
            "| :--- | :--- |",
        ]
        for outcome_name, count in data["summary_by_outcome"].items():
            lines.append(f"| `{outcome_name}` | {count} |")

        lines.extend([
            "",
            "## Work Units",
            "",
            "| Unit ID | Outcome | Status | Elapsed (s) | Retries | Peak RSS | Error Details |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for u in data["units"]:
            peak = f"{u['peak_memory_bytes'] / (1024 * 1024):.1f} MB" if u.get("peak_memory_bytes") else "-"
            err = (u.get("error_message") or "-").replace("|", "\\|").replace("\n", " ")
            if len(err) > 60:
                err = err[:57] + "..."
            lines.append(
                f"| `{u['unit_id']}` | **`{u['outcome']}`** | {u['status']} | {u['elapsed_s']:.2f} | "
                f"{u['retry_count']} | {peak} | {err} |"
            )

        lines.append("")
        return "\n".join(lines)

    def _write_atomic_text(self, path: Path, text: str) -> None:
        import tempfile
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


def run_campaign_manifest(
    manifest: CampaignManifest,
    output_dir: Path | str,
    *,
    resume: bool = True,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> CampaignState:
    """Convenience helper to initialize and run a campaign manifest."""
    runner = SimulationCampaignRunner(
        manifest=manifest,
        output_dir=output_dir,
        cancel_check=cancel_check,
    )
    return runner.run(resume=resume)
