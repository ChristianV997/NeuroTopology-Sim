"""Locate the repository root so `tools.literature_evidence` (a
repo-root package) can be imported from within Awareness Studio's
separate `src/`-rooted package layout.

Independently implemented -- does not import
`awareness_studio.web.research_ops.find_repository_root` (a sibling
module outside this package's owned paths); the two happen to solve the
same problem the same way by convention (`.git` at the boundary), not
by sharing code.
"""
from __future__ import annotations

import sys
from pathlib import Path


class RepositoryRootNotFoundError(RuntimeError):
    """Raised when the repo root containing tools/literature_evidence
    cannot be located -- never silently falls back to a guess."""


def find_repository_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "tools" / "literature_evidence").is_dir():
            return candidate
    raise RepositoryRootNotFoundError(
        "could not locate a repository root containing tools/literature_evidence "
        f"above {current}"
    )


def ensure_repo_root_importable() -> Path:
    """Idempotently add the repo root to sys.path so `import
    tools.literature_evidence` resolves, then return that root."""
    root = find_repository_root()
    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
    return root

