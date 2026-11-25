"""GitHub metadata as a plain, offline data source -- never fetched by
this package itself. See docs/release/integration_state_lock.md for the
snapshot schema.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .models import PRSnapshot

SNAPSHOT_SCHEMA = "NTS.IntegrationStateSnapshot.v1"

_FINAL_COMMIT_PATTERN = re.compile(r"final commit[:\s]*`?([0-9a-f]{7,40})`?", re.IGNORECASE)
_INTEGRATED_PR_PATTERN = re.compile(r"#(\d{2,5})")


def load_snapshot_from_file(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_final_commit_claim(body: Optional[str]) -> Optional[str]:
    """Extract a "Final commit: <sha>" style claim from free-text PR body
    text, if present. This is deliberately permissive text matching (the
    exact wording varies across handoffs) -- the *value* it extracts is
    then verified against real git history like any other handoff claim,
    never trusted just because it was successfully parsed."""
    if not body:
        return None
    match = _FINAL_COMMIT_PATTERN.search(body)
    return match.group(1) if match else None


def parse_integrated_pr_numbers(body: Optional[str]) -> tuple[int, ...]:
    """Extract every #NNNN reference from free-text PR body -- a
    best-effort inventory of "PRs this body claims were integrated,"
    cross-checked later against real branch history."""
    if not body:
        return ()
    return tuple(sorted({int(match) for match in _INTEGRATED_PR_PATTERN.findall(body)}))


def pr_snapshot_from_dict(data: dict[str, Any]) -> PRSnapshot:
    body = data.get("body")
    return PRSnapshot(
        number=data.get("number"),
        state=data.get("state"),
        draft=data.get("draft"),
        merged=data.get("merged"),
        head_ref=data.get("head_ref"),
        head_sha=data.get("head_sha"),
        base_ref=data.get("base_ref"),
        base_sha=data.get("base_sha"),
        checks=data.get("checks", {}),
        body_final_commit_claim=data.get("body_final_commit_claim") or parse_final_commit_claim(body),
        integrated_pr_numbers=tuple(data.get("integrated_pr_numbers", ())) or parse_integrated_pr_numbers(body),
    )


def load_pr_snapshot_from_file(path: Path) -> PRSnapshot:
    return pr_snapshot_from_dict(load_snapshot_from_file(path))
