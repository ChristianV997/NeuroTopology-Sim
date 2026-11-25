"""Deterministic local audits for integration-test Git fixture references."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


def audit_refs(repo: str | Path, refs: Iterable[str]) -> list[dict[str, object]]:
    """Report whether each expected local ref exists, without contacting GitHub.

    A missing ref is reported as ``fixture_inconsistency`` rather than being
    silently synthesized.  Results are sorted by ref name for reproducible
    evidence across Windows and POSIX hosts.
    """
    repo_path = Path(repo)
    results: list[dict[str, object]] = []
    for ref in sorted({str(value) for value in refs}):
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        commit = completed.stdout.strip() or None
        present = completed.returncode == 0 and commit is not None
        results.append(
            {
                "ref": ref,
                "present": present,
                "classification": "available" if present else "fixture_inconsistency",
                "commit": commit,
                "error": completed.stderr.strip() or None,
            }
        )
    return results
