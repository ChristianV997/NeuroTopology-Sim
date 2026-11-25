"""Platform capability audit engine and reporting utility.

Executes a non-destructive audit of filesystem, subprocess, path, and dependency
capabilities. Produces a structured, deterministic report.
"""
from __future__ import annotations

import datetime
import platform
import sys
from pathlib import Path
from typing import Optional

from .dependencies import classify_dependencies
from .filesystem import (
    atomic_write_json,
    detect_file_permissions,
    detect_hardlink_capability,
    detect_symlink_capability,
    safe_temp_dir,
)
from .paths import IS_WINDOWS, normalize_path, to_extended_length_path
from .subprocess_ops import run_guarded_subprocess
from .types import CapabilityResult, CapabilityStatus, PlatformAuditReport


def probe_unicode_path_support() -> CapabilityResult:
    """Probe whether filesystem correctly handles Unicode file and directory paths."""
    unicode_name = "test_π_β_δ_τ_Ω"
    try:
        with safe_temp_dir(prefix="unicode_probe_") as tmp:
            sub = tmp / unicode_name
            sub.mkdir()
            test_file = sub / "данные_файл.json"
            test_file.write_text('{"unicode": "✓"}', encoding="utf-8")

            if test_file.exists() and "✓" in test_file.read_text(encoding="utf-8"):
                return CapabilityResult(
                    name="unicode_paths",
                    status=CapabilityStatus.AVAILABLE,
                    details="Filesystem supports UTF-8 directory and file names.",
                    metadata={"sample_path": str(test_file)},
                )
            return CapabilityResult(
                name="unicode_paths",
                status=CapabilityStatus.FAILED,
                details="Unicode file created but content/existence verification failed.",
            )
    except Exception as exc:
        return CapabilityResult(
            name="unicode_paths",
            status=CapabilityStatus.FAILED,
            details=f"Unicode path creation failed: {exc}",
            error_type=type(exc).__name__,
        )


def probe_long_path_support() -> CapabilityResult:
    """Probe support for long paths exceeding MAX_PATH (260 characters)."""
    # Create a nested path > 260 chars
    nested_segment = "nested_long_path_directory_segment_abcde_12345"
    depth = 7
    try:
        with safe_temp_dir(prefix="long_path_probe_") as tmp:
            curr = tmp
            for i in range(depth):
                curr = curr / f"{nested_segment}_{i}"

            ext_path_str = to_extended_length_path(str(curr))
            curr.mkdir(parents=True, exist_ok=True)
            test_file = curr / "long_leaf.txt"
            test_file.write_text("long_path_ok", encoding="utf-8")

            total_len = len(str(test_file))
            if test_file.exists() and total_len >= 260:
                return CapabilityResult(
                    name="long_paths",
                    status=CapabilityStatus.AVAILABLE,
                    details=f"Extended length path succeeded ({total_len} chars).",
                    metadata={"path_length": total_len},
                )
            elif test_file.exists():
                return CapabilityResult(
                    name="long_paths",
                    status=CapabilityStatus.AVAILABLE,
                    details=f"Path created successfully ({total_len} chars).",
                    metadata={"path_length": total_len},
                )
            return CapabilityResult(
                name="long_paths",
                status=CapabilityStatus.FAILED,
                details="Long path file creation did not verify.",
            )
    except OSError as exc:
        # Long path limitation hit
        winerror = getattr(exc, "winerror", None)
        return CapabilityResult(
            name="long_paths",
            status=CapabilityStatus.UNSUPPORTED,
            details=f"OS or filesystem rejected long path (length > 260): {exc}",
            error_type=type(exc).__name__,
            platform_specific=IS_WINDOWS,
            metadata={"winerror": winerror},
        )


def probe_atomic_write_support() -> CapabilityResult:
    """Probe atomic write and JSON persistence."""
    try:
        with safe_temp_dir(prefix="atomic_probe_") as tmp:
            f = tmp / "target.json"
            atomic_write_json(f, {"status": "ok", "count": 42})
            if f.is_file():
                return CapabilityResult(
                    name="atomic_json_writes",
                    status=CapabilityStatus.AVAILABLE,
                    details="Atomic JSON write and replace succeeded.",
                )
            return CapabilityResult(
                name="atomic_json_writes",
                status=CapabilityStatus.FAILED,
                details="Target file was not created.",
            )
    except Exception as exc:
        return CapabilityResult(
            name="atomic_json_writes",
            status=CapabilityStatus.FAILED,
            details=f"Atomic write failed: {exc}",
            error_type=type(exc).__name__,
        )


def probe_subprocess_support() -> CapabilityResult:
    """Probe subprocess spawning and execution."""
    try:
        res = run_guarded_subprocess([sys.executable, "-c", "print('subproc_ok')"], timeout=5.0)
        if res.returncode == 0 and "subproc_ok" in res.stdout:
            return CapabilityResult(
                name="subprocess_execution",
                status=CapabilityStatus.AVAILABLE,
                details="Guarded subprocess execution and output capture succeeded.",
                metadata={"duration_seconds": res.duration_seconds},
            )
        return CapabilityResult(
            name="subprocess_execution",
            status=CapabilityStatus.FAILED,
            details=f"Subprocess failed with code {res.returncode}: {res.stderr}",
        )
    except Exception as exc:
        return CapabilityResult(
            name="subprocess_execution",
            status=CapabilityStatus.FAILED,
            details=f"Subprocess execution raised exception: {exc}",
            error_type=type(exc).__name__,
        )


def audit_platform_capabilities(output_path: str | Path | None = None) -> PlatformAuditReport:
    """Run full platform audit and optionally write atomic JSON report."""
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    capabilities: dict[str, CapabilityResult] = {
        "symlinks": detect_symlink_capability(),
        "hardlinks": detect_hardlink_capability(),
        "file_permissions": detect_file_permissions(),
        "unicode_paths": probe_unicode_path_support(),
        "long_paths": probe_long_path_support(),
        "atomic_json_writes": probe_atomic_write_support(),
        "subprocess_execution": probe_subprocess_support(),
    }

    dependencies = classify_dependencies()

    report = PlatformAuditReport(
        timestamp=now_ts,
        platform=platform.platform(),
        os_name=platform.system(),
        os_release=platform.release(),
        python_version=platform.python_version(),
        is_windows=IS_WINDOWS,
        is_posix=not IS_WINDOWS,
        capabilities=capabilities,
        dependencies=dependencies,
    )

    if output_path is not None:
        atomic_write_json(output_path, report.to_dict())

    return report
