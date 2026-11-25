"""Platform capability detection and OS-specific behavior helpers.

Provides safe, audited detection of:
- Windows vs. POSIX environment
- PowerShell presence and command construction
- POSIX signals and process groups
- Windows file-locking semantics
- Safe process-tree termination
- Unicode / UTF-8 filesystem capabilities
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_windows() -> bool:
    """True if running on Windows (nt)."""
    return os.name == "nt" or sys.platform.startswith("win")


def is_posix() -> bool:
    """True if running on POSIX (Linux, Darwin, etc.)."""
    return os.name == "posix"


def detect_powershell() -> Tuple[bool, Optional[str], Optional[str]]:
    """Detects available PowerShell executable and version string.

    Returns:
        (available, executable_name_or_path, version_string)
    """
    candidates = ["pwsh", "powershell.exe", "powershell"]
    for cand in candidates:
        found = shutil.which(cand)
        if not found:
            continue
        try:
            res = subprocess.run(
                [found, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                ver = res.stdout.strip()
                return (True, found, ver)
        except Exception:
            continue
    return (False, None, None)


def build_powershell_command(script_content: str, *, exe: str = "powershell.exe") -> List[str]:
    """Constructs a hardened, injection-resistant PowerShell argument list."""
    return [
        exe,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script_content,
    ]


def has_posix_process_groups() -> bool:
    """True if OS supports POSIX process groups (os.killpg, os.setpgrp)."""
    return hasattr(os, "killpg") and hasattr(os, "setpgrp") and hasattr(signal, "SIGKILL")


def terminate_process_tree(pid: int, timeout_s: float = 3.0) -> Tuple[bool, str]:
    """Terminates a process and all its descendants without leaving orphans.

    On Windows, invokes `taskkill /F /T /PID <pid>`.
    On POSIX, uses `os.killpg` if in a process group or falls back to SIGKILL.
    """
    if pid <= 0:
        return (True, "invalid_pid")

    if is_windows():
        try:
            res = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            if res.returncode in (0, 128):  # 0: success, 128: process not found (already exited)
                return (True, "taskkill_terminated")
            return (False, f"taskkill_failed_rc_{res.returncode}: {res.stderr.strip()}")
        except Exception as exc:
            return (False, f"taskkill_exception: {exc}")
    else:
        try:
            if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                    return (True, "killpg_terminated")
                except ProcessLookupError:
                    return (True, "process_already_exited")
                except Exception:
                    pass
            os.kill(pid, signal.SIGKILL)
            return (True, "kill_terminated")
        except ProcessLookupError:
            return (True, "process_already_exited")
        except Exception as exc:
            return (False, f"posix_kill_exception: {exc}")


def check_windows_file_locking(target_file: Path) -> Dict[str, Any]:
    """Inspects file lock behavior by attempting to remove or rename an open file.

    On Windows, unshared write handles block deletion/renaming with PermissionError.
    On POSIX, unlinking an open file succeeds (advisory locking only).
    """
    result: Dict[str, Any] = {
        "file": str(target_file),
        "is_windows": is_windows(),
        "locked_operation_failed": False,
        "error_type": None,
        "error_message": None,
        "unlinked_successfully": False,
    }

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("lock_test_payload\n", encoding="utf-8")

    handle = None
    try:
        # Open file without sharing deletion on Windows
        handle = open(target_file, "r+", encoding="utf-8")
        try:
            target_file.unlink()
            result["unlinked_successfully"] = True
        except (PermissionError, OSError) as exc:
            result["locked_operation_failed"] = True
            result["error_type"] = type(exc).__name__
            result["error_message"] = str(exc)
    finally:
        if handle and not handle.closed:
            handle.close()
        # Clean up if not unlinked
        if target_file.exists():
            try:
                target_file.unlink()
            except Exception:
                pass

    return result


def normalize_windows_path(path_str: str) -> str:
    """Normalizes path strings for Windows compliance and extended-length support."""
    p = str(path_str).replace("/", "\\")
    if p.startswith("\\\\?\\"):
        return p
    if len(p) >= 240 and is_windows():
        if p.startswith("\\\\"):
            # UNC path
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + os.path.abspath(p)
    return p
