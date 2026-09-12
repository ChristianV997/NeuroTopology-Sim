"""Fail-closed local deterministic simulation adapter."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from .finite import FiniteJSONError, dumps_finite, load_finite_json, write_atomic_json
from .lineage_adapter import lineage_summary
from .models import AdapterRequest, AdapterResult, AdapterState

SCHEMA_VERSION = "NeuroTopologySim.ValidatedSolverAdapter.v1"
EXECUTION_REPORT = "adapter_execution.json"
RUN_RECORD = "RunRecord.json"
ARTIFACT_MANIFEST = "artifact_manifest.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contained(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _truncate(handle: Any, limit: int) -> tuple[str, bool]:
    handle.flush(); handle.seek(0)
    data = handle.read(limit + 1)
    return data[:limit].decode("utf-8", errors="replace"), len(data) > limit


def _terminate_tree(process: subprocess.Popen[bytes], grace_s: float = 0.5) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=grace_s)
            return
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=grace_s)
            return
        except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
            pass
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        process.kill()


def _python_command(command: tuple[str, ...]) -> bool:
    return bool(command) and Path(command[0]).name.lower().startswith(("python", "py"))


def _network_guard() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="nts_adapter_no_network_"))
    (directory / "sitecustomize.py").write_text(
        "import socket\n"
        "class NetworkDisabledError(OSError): pass\n"
        "def _blocked(*args, **kwargs): raise NetworkDisabledError('network disabled by solver adapter')\n"
        "socket.socket = _blocked\n"
        "socket.create_connection = _blocked\n",
        encoding="utf-8",
    )
    return directory


def _environment(request: AdapterRequest, guard: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PYTHONHASHSEED": str(request.seed), "SOURCE_DATE_EPOCH": "0", "TZ": "UTC", "LC_ALL": "C", "LANG": "C", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NTS_NETWORK_DISABLED": "1" if request.network_disabled else "0"})
    if guard is not None:
        env["PYTHONPATH"] = str(guard) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _run_id(request: AdapterRequest) -> str:
    return request.run_id or _digest({"workload_id": request.workload_id, "command": list(request.command), "code_commit": request.code_commit, "configuration": request.configuration, "seed": request.seed, "input_identity": request.input_identity})[:16]


def _base_report(request: AdapterRequest, run_id: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "state": AdapterState.BLOCKED.value, "run_id": run_id, "workload_id": request.workload_id, "command": list(request.command), "command_identity": _digest(list(request.command)), "code_commit": request.code_commit, "configuration": dict(request.configuration), "seed": request.seed, "input_identity": request.input_identity, "provenance": dict(request.provenance), "evidence_class": request.evidence_class, "output_root": str(request.output_root.resolve()), "resource_budget": {"timeout_s": request.resource_budget.timeout_s, "max_stdout_bytes": request.resource_budget.max_stdout_bytes, "max_stderr_bytes": request.resource_budget.max_stderr_bytes, "max_output_bytes": request.resource_budget.max_output_bytes, "max_memory_bytes": request.resource_budget.max_memory_bytes}, "scientific_pass": False, "formal_bayes_factor": None, "checksums": {}, "limitations": [], "lineage": None}


def _validate_request(request: AdapterRequest) -> list[str]:
    errors: list[str] = []
    if not request.workload_id or request.workload_id not in request.allowed_commands:
        errors.append("no local adapter implementation is registered for workload_id")
    elif tuple(request.command) != tuple(request.allowed_commands[request.workload_id]):
        errors.append("command does not exactly match the explicit allowlist")
    if not request.command:
        errors.append("command must be non-empty")
    for name, value in (("code_commit", request.code_commit), ("input_identity", request.input_identity), ("evidence_class", request.evidence_class)):
        if not str(value).strip():
            errors.append(f"{name} is required")
    for name in ("source", "data_mode"):
        if not str(request.provenance.get(name, "")).strip():
            errors.append(f"provenance.{name} is required")
    if request.provenance.get("data_mode") in {"empirical", "empirical_local", "real"} and not request.provenance.get("dataset_id"):
        errors.append("empirical provenance requires an explicit dataset_id")
    if request.resource_budget.timeout_s <= 0 or request.resource_budget.max_stdout_bytes < 0 or request.resource_budget.max_stderr_bytes < 0:
        errors.append("resource budget values are invalid")
    if not request.expected_outputs or any(not item or Path(item).is_absolute() for item in request.expected_outputs):
        errors.append("expected outputs must be non-empty relative paths")
    return errors


def _output_checks(request: AdapterRequest, root: Path) -> tuple[AdapterState, dict[str, str | None], list[str]]:
    checksums: dict[str, str | None] = {}
    errors: list[str] = []
    expected = tuple(dict.fromkeys((*request.expected_outputs, request.completion_manifest)))
    for relative in expected:
        path = (root / relative).resolve()
        if not _contained(root, path):
            errors.append(f"output escape: {relative}"); checksums[relative] = None; continue
        if not path.is_file():
            errors.append(f"missing output: {relative}"); checksums[relative] = None; continue
        checksums[relative] = _sha256(path)
        if path.suffix.lower() == ".json":
            try:
                load_finite_json(path)
            except FiniteJSONError as exc:
                errors.append(str(exc))
    manifest = root / request.completion_manifest
    partial = False
    if manifest.is_file():
        try:
            payload = load_finite_json(manifest)
            partial = isinstance(payload, Mapping) and (payload.get("complete") is False or str(payload.get("state", "")).upper() == AdapterState.PARTIAL.value)
            if not isinstance(payload, Mapping) or payload.get("complete") is not True:
                errors.append("completion manifest is not complete")
        except FiniteJSONError as exc:
            errors.append(str(exc))
    if errors:
        return (AdapterState.PARTIAL if partial else AdapterState.FAILED), {key: None for key in checksums}, errors
    return AdapterState.PASS, checksums, []


def _canonical_run_record(request: AdapterRequest, run_id: str, elapsed: float, artifacts: Mapping[str, str]) -> dict[str, Any]:
    return {"schema_version": "0.1", "run_id": run_id, "run_kind": "adapter", "created_at": datetime.now(timezone.utc).isoformat(), "elapsed_s": elapsed, "spec_id": request.workload_id, "claim_type": request.evidence_class, "layer": "simulation", "data_mode": request.provenance.get("data_mode"), "dataset_id": request.provenance.get("dataset_id"), "verdict": None, "metrics": {"adapter_state": AdapterState.PASS.value, "scientific_pass": False}, "artifacts": dict(artifacts), "source": "local_validated_simulation_adapter", "steps": [], "evidence_class": request.evidence_class, "formal_bayes_factor": None, "scientific_pass": False, "code_commit": request.code_commit, "configuration": dict(request.configuration), "seed": request.seed, "input_identity": request.input_identity, "provenance": dict(request.provenance), "claim_scope": "engineering_execution_only", "output_root": str(request.output_root.resolve()), "resource_budget": {"timeout_s": request.resource_budget.timeout_s, "max_stdout_bytes": request.resource_budget.max_stdout_bytes, "max_stderr_bytes": request.resource_budget.max_stderr_bytes, "max_output_bytes": request.resource_budget.max_output_bytes, "max_memory_bytes": request.resource_budget.max_memory_bytes}, "network_disabled": request.network_disabled}


def execute_adapter(request: AdapterRequest, *, interrupt_event: Any | None = None) -> AdapterResult:
    """Run one declared local workload and emit canonical records only on PASS."""
    root = request.output_root.resolve()
    run_id = _run_id(request)
    report = _base_report(request, run_id)
    report_path = root / EXECUTION_REPORT
    try:
        errors = _validate_request(request)
        if errors:
            report["state"] = AdapterState.NOT_IMPLEMENTED.value if any("no local adapter implementation" in error for error in errors) else AdapterState.BLOCKED.value
            report["limitations"] = errors
            root.mkdir(parents=True, exist_ok=True)
            write_atomic_json(report_path, report)
            return AdapterResult(AdapterState(report["state"]), report)
        root.mkdir(parents=True, exist_ok=True)
        if not _contained(root, root):
            raise ValueError("output root containment check failed")
        if request.resume and report_path.is_file():
            previous = load_finite_json(report_path)
            if isinstance(previous, Mapping) and previous.get("state") == AdapterState.PASS.value and previous.get("run_id") == run_id:
                state, checksums, _ = _output_checks(request, root)
                if state is AdapterState.PASS and checksums == previous.get("checksums"):
                    previous = dict(previous); previous["resumed"] = True
                    return AdapterResult(AdapterState.PASS, previous)
    except (OSError, ValueError, FiniteJSONError) as exc:
        report["state"] = AdapterState.BLOCKED.value
        report["limitations"] = [str(exc)]
        try:
            root.mkdir(parents=True, exist_ok=True); write_atomic_json(report_path, report)
        except OSError:
            pass
        return AdapterResult(AdapterState.BLOCKED, report)
    for relative in (*request.expected_outputs, request.completion_manifest, RUN_RECORD, ARTIFACT_MANIFEST):
        candidate = (root / relative).resolve()
        if not _contained(root, candidate):
            report["state"] = AdapterState.BLOCKED.value; report["limitations"] = [f"declared output escapes root: {relative}"]; write_atomic_json(report_path, report); return AdapterResult(AdapterState.BLOCKED, report)
    guard = _network_guard() if request.network_disabled and _python_command(request.command) else None
    if request.network_disabled and not _python_command(request.command):
        report["state"] = AdapterState.BLOCKED.value; report["limitations"] = ["network-disabled mode requires a Python workload with socket guard"]; write_atomic_json(report_path, report); return AdapterResult(AdapterState.BLOCKED, report)
    stdout_file = tempfile.TemporaryFile(); stderr_file = tempfile.TemporaryFile(); process: subprocess.Popen[bytes] | None = None
    started = time.perf_counter(); interrupted = False; timed_out = False
    try:
        kwargs: dict[str, Any] = {"stdout": stdout_file, "stderr": stderr_file, "stdin": subprocess.DEVNULL, "shell": False, "cwd": str(root), "env": _environment(request, guard)}
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else: kwargs["start_new_session"] = True
        process = subprocess.Popen(list(request.command), **kwargs)
        deadline = started + request.resource_budget.timeout_s
        while process.poll() is None:
            if interrupt_event is not None and interrupt_event.is_set():
                interrupted = True; _terminate_tree(process); break
            if time.perf_counter() >= deadline:
                timed_out = True; _terminate_tree(process); break
            time.sleep(0.02)
    except KeyboardInterrupt:
        interrupted = True
        if process is not None: _terminate_tree(process)
    except (OSError, ValueError) as exc:
        report["state"] = AdapterState.FAILED.value; report["limitations"] = [f"process launch failed: {exc}"]; write_atomic_json(report_path, report); return AdapterResult(AdapterState.FAILED, report)
    finally:
        elapsed = time.perf_counter() - started
        stdout, stdout_truncated = _truncate(stdout_file, request.resource_budget.max_stdout_bytes)
        stderr, stderr_truncated = _truncate(stderr_file, request.resource_budget.max_stderr_bytes)
        stdout_file.close(); stderr_file.close()
        if guard is not None: shutil.rmtree(guard, ignore_errors=True)
    report.update({"elapsed_s": elapsed, "stdout": stdout, "stderr": stderr, "stdout_truncated": stdout_truncated, "stderr_truncated": stderr_truncated, "exit_code": process.returncode if process is not None else None, "resource_telemetry": {"elapsed_s": elapsed, "output_bytes": sum(path.stat().st_size for path in root.rglob("*") if path.is_file())}, "output_references": {name: str((root / name).resolve()) for name in (*request.expected_outputs, request.completion_manifest)}})
    if timed_out:
        report["state"] = AdapterState.TIMEOUT.value; report["limitations"] = ["process group timed out; incomplete output checksums are null"]; report["checksums"] = {name: None for name in (*request.expected_outputs, request.completion_manifest)}; write_atomic_json(report_path, report); return AdapterResult(AdapterState.TIMEOUT, report)
    if interrupted:
        report["state"] = AdapterState.PARTIAL.value; report["limitations"] = ["execution interrupted; canonical record withheld"]; report["checksums"] = {name: None for name in (*request.expected_outputs, request.completion_manifest)}; write_atomic_json(report_path, report); return AdapterResult(AdapterState.PARTIAL, report)
    if process is None or process.returncode != 0:
        report["state"] = AdapterState.FAILED.value; report["limitations"] = ["workload exited non-zero; canonical record withheld"]; report["checksums"] = {name: None for name in (*request.expected_outputs, request.completion_manifest)}; write_atomic_json(report_path, report); return AdapterResult(AdapterState.FAILED, report)
    state, checksums, errors = _output_checks(request, root)
    if request.resource_budget.max_output_bytes is not None and report["resource_telemetry"]["output_bytes"] > request.resource_budget.max_output_bytes:
        state = AdapterState.FAILED; errors.append("output resource budget exceeded"); checksums = {name: None for name in checksums}
    report["state"] = state.value; report["checksums"] = checksums; report["limitations"] = errors
    if state is not AdapterState.PASS:
        write_atomic_json(report_path, report); return AdapterResult(state, report)
    artifacts = {name: str((root / name).resolve()) for name in checksums}
    manifest = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "state": AdapterState.PASS.value, "artifacts": [{"relative_path": name, "sha256": checksums[name], "size_bytes": (root / name).stat().st_size} for name in sorted(checksums)], "relationships": [{"source": RUN_RECORD, "target": name, "relationship": "records"} for name in sorted(checksums)], "evidence_class": request.evidence_class, "scientific_pass": False, "formal_bayes_factor": None}
    run_record = _canonical_run_record(request, run_id, elapsed, {"artifact_manifest": ARTIFACT_MANIFEST, **artifacts})
    write_atomic_json(root / ARTIFACT_MANIFEST, manifest)
    write_atomic_json(root / RUN_RECORD, run_record)
    report["canonical_run_record"] = RUN_RECORD; report["artifact_manifest"] = ARTIFACT_MANIFEST; report["lineage"] = lineage_summary(root); report["state"] = AdapterState.PASS.value; report["resumed"] = False
    write_atomic_json(report_path, report)
    return AdapterResult(AdapterState.PASS, report)
