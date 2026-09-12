"""Bounded local execution with explicit states and resumable manifests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence

from .finite import FiniteJSONError, load_finite_json, write_atomic_json
from .lineage_adapter import extract_lineage
from .models import ExecutionState, RunnerConfig, WorkUnit

MANIFEST_NAME = "execution_manifest.json"
SCHEMA_VERSION = "NeuroTopologySim.BoundedExecution.v1"


def _hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _truncate(handle: Any, limit: int) -> tuple[str, bool]:
    handle.flush()
    handle.seek(0)
    data = handle.read(limit + 1)
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


def _is_python(argv: Sequence[str]) -> bool:
    return bool(argv) and Path(argv[0]).name.lower().startswith(("python", "py"))


def _network_guard() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="nts_no_network_"))
    (directory / "sitecustomize.py").write_text(
        "import socket\n"
        "class NetworkDisabledError(OSError): pass\n"
        "def _blocked(*args, **kwargs): raise NetworkDisabledError('network disabled by bounded runner')\n"
        "socket.socket = _blocked\n"
        "socket.create_connection = _blocked\n",
        encoding="utf-8",
    )
    return directory


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


def _environment(config: RunnerConfig, guard: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PYTHONHASHSEED": str(config.deterministic_seed if config.deterministic_seed is not None else 0), "TZ": "UTC", "LC_ALL": "C", "LANG": "C", "SOURCE_DATE_EPOCH": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "NTS_NETWORK_DISABLED": "1" if config.network_disabled else "0"})
    env.update({str(key): str(value) for key, value in config.environment.items()})
    if guard is not None:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(guard) + (os.pathsep + existing if existing else "")
    return env


def _validate_output(unit: WorkUnit, root: Path) -> tuple[ExecutionState, dict[str, str | None], list[str]]:
    checksums: dict[str, str | None] = {}
    errors: list[str] = []
    unit_dir = unit.output_dir.resolve()
    manifest_path = unit_dir / "unit_manifest.json"
    if not _contained(root, unit_dir):
        return ExecutionState.BLOCKED, {name: None for name in unit.expected_outputs}, ["output directory escapes output root"]
    for relative in unit.expected_outputs:
        candidate = (unit_dir / relative).resolve()
        if not _contained(root, candidate):
            errors.append(f"output escapes output root: {relative}")
            checksums[relative] = None
            continue
        if not candidate.is_file():
            errors.append(f"missing expected output: {relative}")
            checksums[relative] = None
            continue
        checksums[relative] = _checksum(candidate)
        if candidate.suffix.lower() == ".json":
            try:
                load_finite_json(candidate)
            except FiniteJSONError as exc:
                errors.append(str(exc))
    partial_manifest = False
    if not manifest_path.is_file():
        errors.append("missing unit_manifest.json")
    else:
        try:
            payload = load_finite_json(manifest_path)
            partial_manifest = isinstance(payload, Mapping) and (payload.get("complete") is False or str(payload.get("status", "")).lower() in {"partial", "incomplete", "interrupted"})
            if not isinstance(payload, Mapping) or payload.get("work_unit_id") != unit.unit_id or payload.get("complete") is not True:
                errors.append("unit_manifest.json is not a complete manifest for this work unit")
        except FiniteJSONError as exc:
            errors.append(str(exc))
    if errors:
        return (ExecutionState.PARTIAL if partial_manifest else ExecutionState.FAILED), {name: None for name in checksums}, errors
    return ExecutionState.PASS, checksums, []


def _disk_usage(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _base_unit_record(unit: WorkUnit, config: RunnerConfig) -> dict[str, Any]:
    return {"unit_id": unit.unit_id, "workload_id": unit.workload_id, "state": ExecutionState.NOT_RUN.value, "command": list(unit.argv), "command_identity": _hash(list(unit.argv)), "code_revision": config.code_revision, "configuration": dict(unit.config), "seed": unit.seed if unit.seed is not None else config.deterministic_seed, "input_references": list(unit.input_references), "output_directory": str(unit.output_dir), "output_references": {}, "checksums": {}, "resource_telemetry": {}, "limitations": []}


def _valid_resume(record: Mapping[str, Any], unit: WorkUnit, root: Path) -> bool:
    if record.get("state") != ExecutionState.PASS.value or record.get("unit_id") != unit.unit_id:
        return False
    if not _contained(root, unit.output_dir.resolve()):
        return False
    state, checksums, _ = _validate_output(unit, root)
    return state is ExecutionState.PASS and checksums == record.get("checksums")


def _execute_unit(unit: WorkUnit, config: RunnerConfig, root: Path) -> dict[str, Any]:
    record = _base_unit_record(unit, config)
    try:
        root_resolved = root.resolve()
        output_dir = unit.output_dir.resolve()
        if not _contained(root_resolved, output_dir):
            record.update({"state": ExecutionState.BLOCKED.value, "limitations": ["output directory escapes explicit output root"]})
            return record
        expected = {(output_dir / relative).resolve() for relative in unit.expected_outputs}
        if any(not _contained(root_resolved, path) for path in expected):
            record.update({"state": ExecutionState.BLOCKED.value, "limitations": ["expected output escapes explicit output root"]})
            return record
        allowed = config.allowed_commands.get(unit.workload_id)
        if allowed is None or tuple(unit.argv) != tuple(allowed):
            record.update({"state": ExecutionState.BLOCKED.value, "limitations": ["command is not an exact allowlisted argv"]})
            return record
        if config.network_disabled and not _is_python(unit.argv):
            record.update({"state": ExecutionState.BLOCKED.value, "limitations": ["network-disabled mode only permits Python workloads with socket guard"]})
            return record
        output_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        record.update({"state": ExecutionState.INFRASTRUCTURE_FAILURE.value, "limitations": [str(exc)]})
        return record
    guard = _network_guard() if config.network_disabled else None
    stdout_file = tempfile.TemporaryFile()
    stderr_file = tempfile.TemporaryFile()
    start = time.perf_counter()
    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    memory_exceeded = False
    peak_memory: int | None = None
    try:
        kwargs: dict[str, Any] = {"stdout": stdout_file, "stderr": stderr_file, "stdin": subprocess.DEVNULL, "shell": False, "env": _environment(config, guard), "cwd": str(output_dir)}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(list(unit.argv), **kwargs)
        timeout = min(unit.timeout_s or config.default_timeout_s, config.runtime_budget_s or float("inf"))
        memory_module = None
        if config.memory_budget_bytes is not None:
            try:
                import psutil  # type: ignore
                memory_module = psutil
            except Exception as exc:
                record.update({"state": ExecutionState.INFRASTRUCTURE_FAILURE.value, "limitations": [f"memory budget requested but psutil is unavailable: {exc}"]})
                _terminate_tree(process)
                return record
        deadline = time.perf_counter() + timeout
        while process.poll() is None:
            if memory_module is not None:
                try:
                    tree = memory_module.Process(process.pid)
                    observed = tree.memory_info().rss + sum(child.memory_info().rss for child in tree.children(recursive=True))
                    peak_memory = max(peak_memory or 0, int(observed))
                    if observed > config.memory_budget_bytes:
                        memory_exceeded = True
                        _terminate_tree(process)
                        break
                except Exception:
                    pass
            if time.perf_counter() >= deadline:
                timed_out = True
                _terminate_tree(process)
                break
            time.sleep(0.02)
    except (OSError, ValueError) as exc:
        record.update({"state": ExecutionState.INFRASTRUCTURE_FAILURE.value, "limitations": [f"process launch failed: {exc}"]})
        return record
    finally:
        elapsed = time.perf_counter() - start
        stdout, stdout_truncated = _truncate(stdout_file, config.stdout_limit)
        stderr, stderr_truncated = _truncate(stderr_file, config.stderr_limit)
        stdout_file.close(); stderr_file.close()
        if guard is not None:
            shutil.rmtree(guard, ignore_errors=True)
    record["resource_telemetry"] = {"elapsed_s": elapsed, "disk_usage_bytes": _disk_usage(root), "memory_budget_bytes": config.memory_budget_bytes, "memory_observed_bytes": peak_memory}
    record["stdout"] = stdout; record["stderr"] = stderr
    record["stdout_truncated"] = stdout_truncated; record["stderr_truncated"] = stderr_truncated
    record["exit_code"] = process.returncode if process is not None else None
    record["timed_out"] = timed_out
    if timed_out:
        record["state"] = ExecutionState.TIMEOUT.value
        record["limitations"] = ["timeout terminated the process group; outputs are incomplete and checksums are null"]
        record["checksums"] = {name: None for name in unit.expected_outputs}
        return record
    if memory_exceeded:
        record["state"] = ExecutionState.FAILED.value
        record["limitations"] = ["memory budget exceeded; process group terminated"]
        record["checksums"] = {name: None for name in unit.expected_outputs}
        return record
    if config.disk_budget_bytes is not None and record["resource_telemetry"]["disk_usage_bytes"] > config.disk_budget_bytes:
        record["state"] = ExecutionState.FAILED.value
        record["limitations"] = ["disk budget exceeded"]
        record["checksums"] = {name: None for name in unit.expected_outputs}
        return record
    if process is None or process.returncode != 0:
        record["state"] = ExecutionState.FAILED.value
        record["limitations"] = ["workload exited non-zero; outputs are not valid evidence"]
        record["checksums"] = {name: None for name in unit.expected_outputs}
        return record
    state, checksums, errors = _validate_output(unit, root)
    record["state"] = state.value; record["checksums"] = checksums
    record["output_references"] = {name: str((unit.output_dir / name).resolve()) for name in unit.expected_outputs}
    record["limitations"] = errors
    if state is not ExecutionState.PASS:
        record["checksums"] = {name: None for name in unit.expected_outputs}
    return record


def run_plan(units: Sequence[WorkUnit], config: RunnerConfig, *, resume: bool = True, ledger_reference: str | Path | None = None) -> dict[str, Any]:
    """Execute a declared plan and atomically persist state after each unit."""
    root = config.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if len({unit.unit_id for unit in units}) != len(units):
        raise ValueError("work unit IDs must be unique and stable")
    manifest_path = root / MANIFEST_NAME
    prior: dict[str, Any] = {}
    if resume and manifest_path.is_file():
        try:
            loaded = load_finite_json(manifest_path)
            if isinstance(loaded, Mapping):
                prior = {str(item.get("unit_id")): dict(item) for item in loaded.get("units", []) if isinstance(item, Mapping) and item.get("unit_id")}
        except FiniteJSONError:
            prior = {}
    unit_records = {unit.unit_id: _base_unit_record(unit, config) for unit in units}
    manifest: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "output_root": str(root), "state_machine": [state.value for state in ExecutionState], "runner": {"code_revision": config.code_revision, "network_disabled": config.network_disabled, "shell": False, "deterministic_environment": True, "stdout_limit": config.stdout_limit, "stderr_limit": config.stderr_limit}, "units": list(unit_records.values()), "lineage": None, "limitations": []}
    write_atomic_json(manifest_path, manifest)
    for unit in units:
        if resume and _valid_resume(prior.get(unit.unit_id, {}), unit, root):
            unit_records[unit.unit_id] = dict(prior[unit.unit_id]); unit_records[unit.unit_id]["resumed"] = True
        elif any(unit_records.get(dep, {}).get("state") != ExecutionState.PASS.value for dep in unit.dependencies):
            unit_records[unit.unit_id].update({"state": ExecutionState.NOT_RUN.value, "limitations": ["dependency did not complete successfully"]})
        else:
            unit_records[unit.unit_id] = _execute_unit(unit, config, root)
        manifest["units"] = [unit_records[item.unit_id] for item in units]
        write_atomic_json(manifest_path, manifest)
    manifest["lineage"] = extract_lineage(root)
    manifest["summary"] = {state.value: sum(1 for item in manifest["units"] if item["state"] == state.value) for state in ExecutionState}
    write_atomic_json(manifest_path, manifest)
    return manifest
