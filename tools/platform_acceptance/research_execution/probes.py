"""System probes and PowerShell command formatting utilities.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from tools.platform_acceptance.research_execution.types import PlatformCapability

_IS_WINDOWS = os.name == "nt"


def ps_single_quote(arg: str) -> str:
    """Escape and wrap an argument inside PowerShell single quotes.

    In PowerShell single-quoted strings, the only escape sequence is ``''`` (two
    consecutive single quotes representing a literal single quote). Backslashes
    are treated literally, preserving Windows paths unchanged.
    """
    escaped = arg.replace("'", "''")
    return f"'{escaped}'"


def build_powershell_command(
    argv: Sequence[str],
    binary: Optional[str] = None,
) -> list[str]:
    """Construct a safe, non-interactive PowerShell invocation for arbitrary argv.

    Uses ``& <exe> <arg1> <arg2>...`` with strict single-quoting.
    """
    if not argv:
        raise ValueError("argv cannot be empty")

    ps_bin = binary
    if not ps_bin:
        ps_bin = "pwsh" if shutil.which("pwsh") else "powershell"

    quoted_args = [ps_single_quote(str(a)) for a in argv]
    command_str = f"& {quoted_args[0]} {' '.join(quoted_args[1:])}".strip()

    return [
        ps_bin,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command_str,
    ]


def probe_powershell() -> tuple[bool, Optional[str], Optional[str]]:
    """Probe for PowerShell availability and extract its version string."""
    candidates = ["pwsh", "powershell", "powershell.exe"]
    found_bin: Optional[str] = None

    for cand in candidates:
        which_path = shutil.which(cand)
        if which_path:
            found_bin = cand
            break

    if not found_bin:
        return False, None, None

    try:
        proc = subprocess.run(
            [found_bin, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode == 0:
            version_str = proc.stdout.strip()
            return True, found_bin, version_str or "unknown"
    except Exception:
        pass

    return False, None, None


def probe_symlink_support() -> bool:
    """Test whether the current process can create filesystem symbolic links."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src = Path(tmp_dir) / "source.txt"
        src.write_text("probe", encoding="utf-8")
        dst = Path(tmp_dir) / "link.txt"
        try:
            os.symlink(src, dst)
            return dst.is_symlink()
        except (OSError, NotImplementedError):
            return False


def probe_file_locking_support() -> bool:
    """Test whether platform file locking primitives are available."""
    if _IS_WINDOWS:
        try:
            import msvcrt
            return hasattr(msvcrt, "locking")
        except ImportError:
            return False
    else:
        try:
            import fcntl
            return hasattr(fcntl, "flock")
        except ImportError:
            return False


def detect_platform_capability() -> PlatformCapability:
    """Probe the host environment and return structured platform capabilities."""
    ps_avail, ps_bin, ps_ver = probe_powershell()
    sym_avail = probe_symlink_support()
    lock_avail = probe_file_locking_support()

    return PlatformCapability(
        os_name=os.name,
        platform_release=platform.platform(),
        is_windows=_IS_WINDOWS,
        powershell_available=ps_avail,
        powershell_binary=ps_bin,
        powershell_version=ps_ver,
        symlink_supported=sym_avail,
        file_locking_supported=lock_avail,
        python_version=sys.version,
    )
