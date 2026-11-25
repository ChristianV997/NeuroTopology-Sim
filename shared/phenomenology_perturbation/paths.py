"""Path protections for optional artifact pointers (reuse BIDS-style rules)."""

from __future__ import annotations

import re
from typing import Optional

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def unsafe_reason(relpath: object) -> Optional[str]:
    """Return why a relative path is unsafe, or None if structurally acceptable."""
    if not isinstance(relpath, str):
        return "PATH_NOT_TEXT"
    if relpath == "" or relpath != relpath.strip():
        return "PATH_EMPTY_OR_PADDED"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in relpath):
        return "PATH_CONTROL_CHARACTER"
    if relpath.startswith("/") or _DRIVE_RE.match(relpath) or "\\" in relpath:
        return "PATH_UNSAFE"
    if any(segment in ("", ".", "..") for segment in relpath.split("/")):
        return "PATH_UNSAFE"
    return None


def safe_relative_path(relpath: object) -> str:
    """Return a validated relative path or raise ValueError."""
    reason = unsafe_reason(relpath)
    if reason is not None:
        raise ValueError(f"unsafe relative path ({reason}): {relpath!r}")
    assert isinstance(relpath, str)
    return relpath
