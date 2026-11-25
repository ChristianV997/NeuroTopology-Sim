"""Platform-neutral path normalization, comparison, and extended-length handling.

Guarantees:
- Uniform handling of Windows-style ('\\'), POSIX-style ('/'), and mixed separators.
- Semantic path comparison with platform-appropriate case sensitivity.
- Unicode and extended-length path support ('\\\\?\\' on Windows).
- Directory traversal safety validation.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Union


IS_WINDOWS = sys.platform.startswith("win")
EXTENDED_PATH_PREFIX = "\\\\?\\"
UNC_PREFIX = "\\\\?\\UNC\\"


def to_posix_path(path: str | Path) -> str:
    """Convert any path to POSIX style with forward slashes."""
    p_str = str(path).strip()
    if not p_str:
        return ""
    # Normalize slashes
    posix = p_str.replace("\\", "/")
    # Collapse multiple consecutive slashes except leading '//' (UNC / root)
    if posix.startswith("//"):
        posix = "//" + re.sub(r"/+", "/", posix[2:])
    else:
        posix = re.sub(r"/+", "/", posix)
    return posix


def to_windows_path(path: str | Path) -> str:
    """Convert any path to Windows style with backslashes."""
    p_str = str(path).strip()
    if not p_str:
        return ""
    win = p_str.replace("/", "\\")
    if win.startswith("\\\\"):
        win = "\\\\" + re.sub(r"\\+", lambda _: "\\", win[2:])
    else:
        win = re.sub(r"\\+", lambda _: "\\", win)
    return win


def to_extended_length_path(path: str | Path) -> str:
    """Prepend Windows extended length prefix ('\\\\?\\') if running on Windows and path is absolute."""
    p_str = str(path).strip()
    if not IS_WINDOWS or not p_str:
        return p_str

    if p_str.startswith(EXTENDED_PATH_PREFIX):
        return p_str

    abs_path = os.path.abspath(p_str)
    # Check if UNC network share
    if abs_path.startswith("\\\\"):
        return UNC_PREFIX + abs_path[2:]
    return EXTENDED_PATH_PREFIX + abs_path


def strip_extended_prefix(path: str | Path) -> str:
    """Strip Windows extended-length prefix ('\\\\?\\') if present."""
    p_str = str(path).strip()
    if p_str.startswith(UNC_PREFIX):
        return "\\\\" + p_str[len(UNC_PREFIX):]
    if p_str.startswith(EXTENDED_PATH_PREFIX):
        return p_str[len(EXTENDED_PATH_PREFIX):]
    return p_str


def normalize_path(
    path: str | Path,
    as_posix: bool = False,
    resolve: bool = False,
) -> str:
    """Normalize path separators, relative segments, and redundant slashes."""
    p_str = str(path).strip()
    if not p_str:
        return ""

    has_prefix = p_str.startswith(EXTENDED_PATH_PREFIX)
    clean = strip_extended_prefix(p_str) if has_prefix else p_str

    # Normalize slashes to single separator
    clean = clean.replace("\\", "/")
    # Collapse consecutive slashes (preserving leading // for UNC)
    if clean.startswith("//"):
        clean = "//" + re.sub(r"/+", "/", clean[2:])
    else:
        clean = re.sub(r"/+", "/", clean)

    p = Path(clean)
    if resolve:
        try:
            p = p.resolve()
        except (OSError, RuntimeError):
            pass

    out_str = str(p)
    if as_posix:
        out_str = to_posix_path(out_str)
    elif IS_WINDOWS:
        out_str = to_windows_path(out_str)

    if has_prefix and IS_WINDOWS:
        return to_extended_length_path(out_str)
    return out_str


def compare_paths(
    path_a: str | Path,
    path_b: str | Path,
    case_sensitive: bool | None = None,
) -> bool:
    """Compare two paths for logical equality, respecting platform case-folding."""
    norm_a = normalize_path(path_a, as_posix=True)
    norm_b = normalize_path(path_b, as_posix=True)

    # Determine case sensitivity
    if case_sensitive is None:
        case_sensitive = not IS_WINDOWS

    if not case_sensitive:
        norm_a = norm_a.lower()
        norm_b = norm_b.lower()

    # Normalize trailing slash
    norm_a = norm_a.rstrip("/")
    norm_b = norm_b.rstrip("/")

    # Check direct string match
    if norm_a == norm_b:
        return True

    # Check absolute resolved match if paths exist
    try:
        abs_a = Path(strip_extended_prefix(str(path_a))).resolve()
        abs_b = Path(strip_extended_prefix(str(path_b))).resolve()
        if not case_sensitive:
            return str(abs_a).lower() == str(abs_b).lower()
        return abs_a == abs_b
    except (OSError, RuntimeError):
        return False


def has_unicode_characters(path: str | Path) -> bool:
    """Check if path string contains non-ASCII Unicode characters."""
    p_str = str(path)
    return any(ord(char) > 127 for char in p_str)


def is_safe_relative_path(path: str | Path, base_dir: str | Path | None = None) -> bool:
    """Verify that a path does not escape outside base_dir via '..' segments."""
    try:
        p = Path(path)
        if p.is_absolute():
            if base_dir is None:
                return True
            b = Path(base_dir).resolve()
            return b in p.resolve().parents or p.resolve() == b

        # For relative paths, resolve against base_dir (or current working dir)
        base = Path(base_dir).resolve() if base_dir else Path.cwd()
        resolved = (base / p).resolve()
        return base in resolved.parents or resolved == base
    except (ValueError, OSError, RuntimeError):
        return False
