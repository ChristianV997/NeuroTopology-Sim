"""Cross-platform lexical path-containment checks.

The check is intentionally lexical and deterministic.  Runtime callers that
open files should additionally resolve symlinks before opening them.
"""

from __future__ import annotations

import ntpath
import posixpath
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PathContainment:
    root: str
    candidate: str
    contained: bool
    style: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "candidate": self.candidate,
            "contained": self.contained,
            "style": self.style,
            "reason": self.reason,
        }


def _style(root: str, candidate: str) -> str:
    if re.match(r"^[A-Za-z]:[\\/]", root) or re.match(r"^[A-Za-z]:[\\/]", candidate):
        return "windows"
    if "\\" in root or "\\" in candidate or root.startswith("\\\\") or candidate.startswith("\\\\"):
        return "windows"
    return "posix"


def check_path_containment(root: str, candidate: str, *, allow_equal: bool = False) -> PathContainment:
    """Check that ``candidate`` is a strict child of ``root`` by path style."""
    if not isinstance(root, str) or not isinstance(candidate, str) or not root or not candidate:
        return PathContainment(str(root), str(candidate), False, "unknown", "root and candidate are required")
    style = _style(root, candidate)
    module = ntpath if style == "windows" else posixpath
    root_norm = module.normcase(module.normpath(module.abspath(root)))
    candidate_norm = module.normcase(module.normpath(module.abspath(candidate)))
    try:
        common = module.commonpath([root_norm, candidate_norm])
    except ValueError:
        return PathContainment(root, candidate, False, style, "root and candidate are on different roots")
    same = candidate_norm == root_norm
    contained = common == root_norm and (allow_equal or not same)
    if contained:
        reason = "candidate is contained"
    elif same:
        reason = "candidate equals root; a distinct child is required"
    else:
        reason = "candidate escapes configured root"
    return PathContainment(root, candidate, contained, style, reason)
