"""Target-root safety: every acquisition plan/execution must write only
under an allowed, already-gitignored local workspace directory --
`outputs/` or `data/` (both covered by `.gitignore`'s `outputs/`,
`data/raw/`, and `data/ds[0-9]{6}*` patterns) -- never into a tracked
source directory (`adapters/`, `dataset_importers/`, `core/`, ...), and
never outside the repository entirely.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

_REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_TARGET_ROOT_PREFIXES: tuple[str, ...] = ("outputs/", "data/")


class TargetRootError(ValueError):
    """Raised when a target_root is not a safe, contained local path."""


def validate_target_root(target_root: Union[str, Path]) -> Path:
    """Fail closed unless `target_root` is a relative repository path under
    `outputs/` or `data/`, contains no `..` escape segment, and resolves to
    a path actually inside the repository root. Returns the resolved
    absolute `Path` on success."""
    raw = str(target_root).strip()
    if not raw:
        raise TargetRootError("target_root is required")
    if raw.startswith("/") or raw.startswith("~"):
        raise TargetRootError(f"target_root must be a relative repository path, got absolute path {raw!r}")

    parts = Path(raw).parts
    if ".." in parts:
        raise TargetRootError(f"target_root must not contain '..' path segments: {raw!r}")

    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        raise TargetRootError(
            f"target_root must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {raw!r} (rule 13/14)"
        )

    resolved = (_REPO_ROOT / raw).resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError as exc:
        raise TargetRootError(f"target_root resolves outside the repository root: {raw!r}") from exc

    return resolved
