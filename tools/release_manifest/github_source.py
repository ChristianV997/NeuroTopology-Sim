"""Optional GitHub-side snapshot loader.

This package never makes a network call itself. GitHub-side facts
(PR number/state/draft/merged/head_sha/base_ref/checks/body) come only
from an optional, pre-fetched JSON snapshot file the caller supplies.
If no snapshot is supplied, every PR-derived field in the manifest is
``Evidence(None, "no github snapshot supplied")`` and the schema-level
``github_state`` field is explicitly ``"unavailable"`` -- never inferred,
never silently treated as "no PR exists".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import PRSnapshot


def load_pr_snapshot(snapshot_path: Optional[Path]) -> Optional[PRSnapshot]:
    """Load a :class:`PRSnapshot` from a JSON file, or ``None`` if
    ``snapshot_path`` is ``None``. Raises no exception for a missing/
    unreadable/malformed file -- callers must treat that identically to
    "no snapshot supplied" (``github_state="unavailable"``), never as a
    crash or a silently-assumed-merged state."""
    if snapshot_path is None:
        return None
    try:
        raw = json.loads(Path(snapshot_path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return PRSnapshot(
        number=raw.get("number"),
        state=raw.get("state"),
        draft=raw.get("draft"),
        merged=raw.get("merged"),
        head_sha=raw.get("head_sha"),
        base_ref=raw.get("base_ref") or raw.get("base"),
        checks=raw.get("checks") or {},
        body=raw.get("body"),
    )


def github_state_of(snapshot: Optional[PRSnapshot]) -> str:
    return "available" if snapshot is not None else "unavailable"
