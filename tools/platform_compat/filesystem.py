"""Filesystem helpers for platform-neutral tempdirs, atomic writes, and capability probing.

Features:
- Robust temporary directory management with Windows lock-retry cleanup.
- Atomic JSON writes via temporary sibling files and os.replace.
- Non-destructive detection of symlink and hardlink capabilities.
- Structured capability classification (AVAILABLE, PERMISSION_DENIED, UNSUPPORTED, FAILED).
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Generator, Optional

from .paths import IS_WINDOWS
from .types import CapabilityResult, CapabilityStatus


def _remove_readonly(func: Any, path: str, excinfo: Any) -> None:
    """Error handler for shutil.rmtree to clear read-only flag on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


@contextlib.contextmanager
def safe_temp_dir(
    prefix: str = "neurotopo_compat_",
    base_dir: str | Path | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> Generator[Path, None, None]:
    """Create a temporary directory with guaranteed cleanup and Windows retry logic."""
    base = str(base_dir) if base_dir else None
    temp_path_str = tempfile.mkdtemp(prefix=prefix, dir=base)
    temp_dir = Path(temp_path_str).resolve()
    try:
        yield temp_dir
    finally:
        if temp_dir.exists():
            for attempt in range(max_retries):
                try:
                    if hasattr(shutil, "rmtree") and sys.version_info >= (3, 12):
                        # Python 3.12+ supports on_exc
                        def on_exc_handler(func: Any, path: str, exc: Any) -> None:
                            try:
                                os.chmod(path, stat.S_IWRITE)
                                func(path)
                            except Exception:
                                pass
                        shutil.rmtree(temp_dir, onexc=on_exc_handler)
                    else:
                        shutil.rmtree(temp_dir, onerror=_remove_readonly)
                    break
                except (OSError, PermissionError):
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        # Best-effort final attempt
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except Exception:
                            pass


def atomic_write_json(
    target_path: str | Path,
    data: Any,
    indent: int = 2,
    allow_nan: bool = False,
    ensure_parents: bool = True,
) -> Path:
    """Atomically serialize and write data to a JSON file using a sibling temp file and os.replace.

    Guarantees:
    - Target file is never left in a partially written or corrupted state.
    - Rejects NaN and Infinity when allow_nan=False.
    - Cleans up sibling temp file on any exception.
    """
    target = Path(target_path).resolve()

    if target.is_dir():
        raise IsADirectoryError(f"Cannot write JSON to directory path: {target}")

    if ensure_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    elif not target.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {target.parent}")

    # Serialize in memory first to validate JSON structure
    json_content = json.dumps(data, indent=indent, allow_nan=allow_nan)

    # Sibling temp file on same volume/filesystem to ensure atomic rename
    unique_id = uuid.uuid4().hex[:12]
    temp_file = target.parent / f".tmp_{target.name}_{unique_id}"

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(json_content)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replacement
        os.replace(temp_file, target)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass

    return target


def safe_read_json(target_path: str | Path) -> Any:
    """Read and parse JSON from file path."""
    p = Path(target_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found or is not a regular file: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def detect_symlink_capability(test_dir: Path | None = None) -> CapabilityResult:
    """Detect whether creating symbolic links is permitted and functional."""
    def probe(work_dir: Path) -> CapabilityResult:
        src = work_dir / "symlink_src.txt"
        dst = work_dir / "symlink_dst.txt"
        src.write_text("symlink_test_payload", encoding="utf-8")
        try:
            os.symlink(src, dst)
            # Verify symlink resolves
            if dst.is_symlink() and dst.read_text(encoding="utf-8") == "symlink_test_payload":
                return CapabilityResult(
                    name="symlinks",
                    status=CapabilityStatus.AVAILABLE,
                    details="Symbolic link creation and resolution succeeded.",
                    platform_specific=IS_WINDOWS,
                )
            return CapabilityResult(
                name="symlinks",
                status=CapabilityStatus.FAILED,
                details="Symlink was created but failed resolution check.",
            )
        except PermissionError as exc:
            # On Windows without Developer Mode or SeCreateSymbolicLinkPrivilege
            details = (
                "Symlinks require elevated privileges or Windows Developer Mode."
                if IS_WINDOWS else "Symlink creation denied by filesystem permissions."
            )
            return CapabilityResult(
                name="symlinks",
                status=CapabilityStatus.PERMISSION_DENIED,
                details=details,
                error_type="PermissionError",
                platform_specific=IS_WINDOWS,
                metadata={"winerror": getattr(exc, "winerror", None)},
            )
        except OSError as exc:
            # [WinError 1314]: A required privilege is not held by the client
            winerror = getattr(exc, "winerror", None)
            if winerror == 1314:
                return CapabilityResult(
                    name="symlinks",
                    status=CapabilityStatus.PERMISSION_DENIED,
                    details="Windows requires Developer Mode or Administrator privileges to create symlinks.",
                    error_type="WinError 1314",
                    platform_specific=True,
                    metadata={"winerror": 1314},
                )
            return CapabilityResult(
                name="symlinks",
                status=CapabilityStatus.UNSUPPORTED,
                details=f"Filesystem does not support symlinks: {exc}",
                error_type=type(exc).__name__,
            )
        finally:
            if dst.is_symlink() or dst.exists():
                try:
                    dst.unlink(missing_ok=True)
                except OSError:
                    pass
            if src.exists():
                try:
                    src.unlink(missing_ok=True)
                except OSError:
                    pass

    if test_dir is not None:
        return probe(test_dir)
    with safe_temp_dir(prefix="symlink_probe_") as tmp:
        return probe(tmp)


def detect_hardlink_capability(test_dir: Path | None = None) -> CapabilityResult:
    """Detect whether creating hard links is permitted and functional."""
    def probe(work_dir: Path) -> CapabilityResult:
        src = work_dir / "hardlink_src.txt"
        dst = work_dir / "hardlink_dst.txt"
        src.write_text("hardlink_test_payload", encoding="utf-8")
        try:
            os.link(src, dst)
            # Verify hardlink shares inode / content
            stat_src = src.stat()
            stat_dst = dst.stat()
            if stat_src.st_ino == stat_dst.st_ino or dst.read_text(encoding="utf-8") == "hardlink_test_payload":
                return CapabilityResult(
                    name="hardlinks",
                    status=CapabilityStatus.AVAILABLE,
                    details="Hard link creation succeeded.",
                    platform_specific=False,
                )
            return CapabilityResult(
                name="hardlinks",
                status=CapabilityStatus.FAILED,
                details="Hard link created but stat check did not match.",
            )
        except PermissionError:
            return CapabilityResult(
                name="hardlinks",
                status=CapabilityStatus.PERMISSION_DENIED,
                details="Hard link creation denied by filesystem permissions.",
                error_type="PermissionError",
            )
        except OSError as exc:
            return CapabilityResult(
                name="hardlinks",
                status=CapabilityStatus.UNSUPPORTED,
                details=f"Filesystem does not support hard links: {exc}",
                error_type=type(exc).__name__,
            )
        finally:
            if dst.exists():
                try:
                    dst.unlink(missing_ok=True)
                except OSError:
                    pass
            if src.exists():
                try:
                    src.unlink(missing_ok=True)
                except OSError:
                    pass

    if test_dir is not None:
        return probe(test_dir)
    with safe_temp_dir(prefix="hardlink_probe_") as tmp:
        return probe(tmp)


def detect_file_permissions(test_dir: Path | None = None) -> CapabilityResult:
    """Detect basic file permission semantics (read, write, read-only modification)."""
    def probe(work_dir: Path) -> CapabilityResult:
        f = work_dir / "perm_test.txt"
        try:
            f.write_text("permission_check", encoding="utf-8")
            can_read = os.access(f, os.R_OK)
            can_write = os.access(f, os.W_OK)

            # Test setting read-only
            os.chmod(f, stat.S_IREAD)
            is_readonly = not os.access(f, os.W_OK)

            # Restore writable
            os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
            restored = os.access(f, os.W_OK)

            f.unlink(missing_ok=True)

            if can_read and can_write and is_readonly and restored:
                return CapabilityResult(
                    name="file_permissions",
                    status=CapabilityStatus.AVAILABLE,
                    details="Filesystem correctly enforces read, write, and read-only attributes.",
                )
            return CapabilityResult(
                name="file_permissions",
                status=CapabilityStatus.AVAILABLE,
                details="Basic read/write functional, permission flags partially mapped.",
                metadata={"can_read": can_read, "can_write": can_write, "is_readonly": is_readonly},
            )
        except Exception as exc:
            return CapabilityResult(
                name="file_permissions",
                status=CapabilityStatus.FAILED,
                details=f"Permission probe failed: {exc}",
                error_type=type(exc).__name__,
            )

    if test_dir is not None:
        return probe(test_dir)
    with safe_temp_dir(prefix="perm_probe_") as tmp:
        return probe(tmp)
