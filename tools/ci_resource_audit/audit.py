"""Read-only cross-platform resource audit for local and CI diagnostics."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .log_parser import FAILURE_CLASSES


AUDIT_SCHEMA = "NeuroTopology.CIResourceAudit.v1"
DEFAULT_MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024
_OPTIONAL_PACKAGES = ("psutil", "docker", "numpy", "scipy", "pytest", "mne", "torch", "qutip", "qiskit", "cupy", "pandas")
_CI_VALUE_MARKERS = ("CI", "GITHUB_ACTIONS", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW", "RUNNER_OS", "RUNNER_ARCH")


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _disk_usage(path: Path, disk_usage_fn: Callable[[str | os.PathLike[str]], Any], *, display_path: str | None = None) -> dict[str, Any]:
    try:
        usage = disk_usage_fn(path)
        return {"path": display_path if display_path is not None else str(path), "total_bytes": int(usage.total), "used_bytes": int(usage.used), "free_bytes": int(usage.free)}
    except (OSError, AttributeError, TypeError, ValueError):
        return {"path": display_path if display_path is not None else str(path), "total_bytes": None, "used_bytes": None, "free_bytes": None}


def _memory_info() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        return {"total_bytes": int(memory.total), "available_bytes": int(memory.available), "source": "psutil"}
    except (ImportError, OSError, AttributeError, ValueError):
        pass
    if os.name == "posix":
        try:
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii", errors="replace").splitlines():
                key, _, raw = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(raw.strip().split()[0]) * 1024
            if "MemTotal" in values:
                return {"total_bytes": values["MemTotal"], "available_bytes": values.get("MemAvailable"), "source": "proc_meminfo"}
        except (OSError, ValueError, IndexError):
            pass
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong), ("page_file_total", ctypes.c_ulonglong), ("page_file_available", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong), ("virtual_extended", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return {"total_bytes": int(status.total), "available_bytes": int(status.available), "source": "GlobalMemoryStatusEx"}
        except (AttributeError, OSError, TypeError):
            pass
    return {"total_bytes": None, "available_bytes": None, "source": None}


def _package_versions() -> dict[str, str]:
    packages: dict[str, str] = {}
    try:
        for distribution in importlib.metadata.distributions():
            name = distribution.metadata.get("Name") or distribution.metadata.get("name")
            version = distribution.version
            if name and version:
                packages[str(name)] = str(version)
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
        pass
    return dict(sorted(packages.items(), key=lambda item: item[0].lower()))


def _optional_dependencies(installed: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    by_lower = {name.lower(): (name, version) for name, version in installed.items()}
    result: dict[str, dict[str, Any]] = {}
    for package in _OPTIONAL_PACKAGES:
        package_entry = by_lower.get(package.lower())
        try:
            importable = importlib.util.find_spec(package) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            importable = False
        result[package] = {"available": bool(package_entry or importable), "version": package_entry[1] if package_entry else None, "importable": bool(importable)}
    return result


def _docker_status() -> dict[str, Any]:
    executable = shutil.which("docker")
    result: dict[str, Any] = {"cli_available": bool(executable), "executable": executable, "version": None, "daemon_checked": False, "error": None}
    if not executable:
        return result
    try:
        completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=3, check=False)
        if completed.returncode == 0:
            result["version"] = completed.stdout.strip() or completed.stderr.strip() or None
        else:
            result["error"] = (completed.stderr or completed.stdout).strip() or "docker --version failed"
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result


def _github_actions_markers(env: Mapping[str, str]) -> dict[str, Any]:
    in_ci = str(env.get("GITHUB_ACTIONS", "")).lower() == "true" or bool(env.get("CI"))
    values = {name: env.get(name) for name in _CI_VALUE_MARKERS if env.get(name) is not None}
    return {"in_ci": in_ci, "markers": dict(sorted(values.items())), "job_started_marker_present": bool(env.get("GITHUB_JOB"))}


def collect_environment(*, repo_path: str | os.PathLike[str] | None = None, temp_dir: str | os.PathLike[str] | None = None, include_packages: bool = True, include_timestamp: bool = False, disk_usage_fn: Callable[[str | os.PathLike[str]], Any] | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Collect local facts without network calls or state-changing operations."""
    environment = dict(os.environ if env is None else env)
    root = Path(repo_path or Path.cwd())
    temporary = Path(temp_dir or tempfile.gettempdir())
    root_display = os.fspath(repo_path) if repo_path is not None else str(root)
    temporary_display = os.fspath(temp_dir) if temp_dir is not None else str(temporary)
    usage = disk_usage_fn or shutil.disk_usage
    installed = _package_versions() if include_packages else {}
    cache_location = environment.get("PIP_CACHE_DIR")
    if not cache_location:
        cache_location = str(Path(environment.get("LOCALAPPDATA", Path.home())) / "pip" / "Cache") if os.name == "nt" else str(Path.home() / ".cache" / "pip")
    cache_path = Path(cache_location)
    cache_usage = _disk_usage(cache_path, usage) if cache_path.exists() else {"path": str(cache_path), "total_bytes": None, "used_bytes": None, "free_bytes": None}
    try:
        cache_size = sum(path.stat().st_size for path in cache_path.rglob("*") if path.is_file()) if cache_path.exists() else None
    except OSError:
        cache_size = None
    nvidia_packages = {name: version for name, version in installed.items() if any(token in name.lower() for token in ("nvidia", "cuda", "cupy"))}
    report: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "generated_at_utc": _timestamp() if include_timestamp else None,
        "read_only": True,
        "network_accessed": False,
        "mutations": [],
        "operating_system": {"system": platform.system() or None, "release": platform.release() or None, "version": platform.version() or None, "machine": platform.machine() or None, "architecture": f"{struct.calcsize('P') * 8}bit"},
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(), "executable": sys.executable or None},
        "cpu_count": os.cpu_count(),
        "memory": _memory_info(),
        "disk": {"repository": _disk_usage(root, usage, display_path=root_display), "temporary_directory": _disk_usage(temporary, usage, display_path=temporary_display)},
        "pip_cache": {"location": str(cache_path), "size_bytes": cache_size, "disk": cache_usage},
        "docker": _docker_status(),
        "installed_package_versions": installed,
        "optional_dependencies": _optional_dependencies(installed),
        "cuda_nvidia": {"installed_packages": dict(sorted(nvidia_packages.items(), key=lambda item: item[0].lower())), "nvidia_smi_available": bool(shutil.which("nvidia-smi")), "environment": {name: environment.get(name) for name in ("CUDA_HOME", "CUDA_PATH", "CUDA_VISIBLE_DEVICES") if environment.get(name) is not None}},
        "github_actions": _github_actions_markers(environment),
    }
    return report


def classify_resource_state(environment: Mapping[str, Any], *, min_free_disk_bytes: int = DEFAULT_MIN_FREE_DISK_BYTES, min_available_memory_bytes: int | None = None) -> dict[str, Any]:
    """Classify known local resource exhaustion without guessing unknown values."""
    reasons: list[str] = []
    disk = environment.get("disk", {})
    for label in ("repository", "temporary_directory"):
        free = disk.get(label, {}).get("free_bytes") if isinstance(disk, Mapping) else None
        if isinstance(free, (int, float)) and free < min_free_disk_bytes:
            reasons.append(f"{label}_free_bytes_below_threshold")
    memory = environment.get("memory", {})
    available = memory.get("available_bytes") if isinstance(memory, Mapping) else None
    if min_available_memory_bytes is not None and isinstance(available, (int, float)) and available < min_available_memory_bytes:
        reasons.append("available_memory_below_threshold")
    classification = "disk_exhaustion" if any("free_bytes" in reason for reason in reasons) else "memory_exhaustion" if reasons else None
    return {"classification": classification, "reasons": reasons, "thresholds": {"min_free_disk_bytes": min_free_disk_bytes, "min_available_memory_bytes": min_available_memory_bytes}}


def build_environment_report(**kwargs: Any) -> dict[str, Any]:
    environment = collect_environment(**kwargs)
    return {"schema": AUDIT_SCHEMA, "mode": "environment", "environment": environment, "resource_state": classify_resource_state(environment), "failure_classes": list(FAILURE_CLASSES)}


def serialize_report(report: Mapping[str, Any]) -> str:
    """Serialize sorted, finite JSON. Unavailable values remain JSON null."""
    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"


def render_human_summary(report: Mapping[str, Any]) -> str:
    mode = report.get("mode", "environment")
    lines = ["CI resource preflight", f"mode: {mode}"]
    if mode == "log":
        log = report.get("log", {})
        lines.extend([f"classification: {log.get('classification') or 'no_failure_detected'}", f"job_started: {log.get('job_started')}", f"tests_passed: {log.get('tests_passed')}", f"billing_evidence: {log.get('billing_evidence')}", f"generic_timeout_only: {log.get('generic_timeout_only')}"])
    else:
        environment = report.get("environment", {})
        disk = environment.get("disk", {}).get("repository", {})
        memory = environment.get("memory", {})
        lines.extend([f"operating_system: {environment.get('operating_system', {}).get('system')}", f"python: {environment.get('python', {}).get('version')}", f"cpu_count: {environment.get('cpu_count')}", f"disk_free_bytes: {disk.get('free_bytes')}", f"memory_available_bytes: {memory.get('available_bytes')}", f"github_actions: {environment.get('github_actions', {}).get('in_ci')}", f"docker_cli_available: {environment.get('docker', {}).get('cli_available')}"])
    lines.append("read_only: true")
    lines.append("network_accessed: false")
    return "\n".join(lines) + "\n"
