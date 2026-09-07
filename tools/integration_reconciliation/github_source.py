"""GitHub metadata as a plain, offline data source.

This module never makes an HTTP request. It reads a pre-fetched JSON
snapshot (schema below) and exposes lookups over it. The snapshot is
produced *outside* this tool -- by whatever already-authorized GitHub
client the operator is using (e.g. the `gh` CLI, or a GitHub App/MCP
client) -- and handed to `scripts/verify_integration_reconciliation.py`
via `--github-snapshot`. This keeps the reconciliation tool itself free of
any network dependency, so its unit tests never need one (requirement:
"network access must not be required for unit tests").

Snapshot schema (``NTS.GitHubReconciliationSnapshot.v1``)::

    {
      "schema": "NTS.GitHubReconciliationSnapshot.v1",
      "fetched_at": "<iso8601, informational only>",
      "pull_requests": [
        {
          "number": 210,
          "head_ref": "claude/ecosystem-integration",
          "head_sha": "...",
          "base_ref": "main",
          "base_sha": "...",
          "state": "open",            # "open" | "closed"
          "draft": true,
          "merged": false,
          "mergeable_state": "unstable",
          "checks": {"core-tests": "failure", "awareness-tests": "success"}
        },
        ...
      ]
    }

Every field beyond ``number``/``head_ref`` is optional in a snapshot; a
missing field surfaces as an explicit null with an "absent from snapshot"
evidence note, never as a fabricated default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

SNAPSHOT_SCHEMA = "NTS.GitHubReconciliationSnapshot.v1"


def load_snapshot_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_snapshot_from_dict(data)


def load_snapshot_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or "pull_requests" not in data:
        raise ValueError("GitHub snapshot must be a dict with a 'pull_requests' list")
    if not isinstance(data["pull_requests"], list):
        raise ValueError("GitHub snapshot 'pull_requests' must be a list")
    return data


def empty_snapshot() -> dict[str, Any]:
    return {"schema": SNAPSHOT_SCHEMA, "fetched_at": None, "pull_requests": []}


def find_pr_by_branch(snapshot: dict[str, Any], head_ref: str) -> Optional[dict[str, Any]]:
    for pr in snapshot.get("pull_requests", []):
        if pr.get("head_ref") == head_ref:
            return pr
    return None


def find_pr_by_number(snapshot: dict[str, Any], number: int) -> Optional[dict[str, Any]]:
    for pr in snapshot.get("pull_requests", []):
        if pr.get("number") == number:
            return pr
    return None


def normalize_checks(checks: Optional[dict[str, Any]]) -> dict[str, dict[str, Optional[str]]]:
    """Normalize legacy flat conclusions and rich check evidence."""
    if not checks:
        return {}
    normalized: dict[str, dict[str, Optional[str]]] = {}
    for name, value in checks.items():
        if isinstance(value, dict):
            normalized[name] = {
                "status": value.get("status", "completed"),
                "conclusion": value.get("conclusion"),
                "failure_signature": value.get("failure_signature"),
            }
        else:
            normalized[name] = {
                "status": "completed",
                "conclusion": str(value),
                "failure_signature": None,
            }
    return normalized


def checks_all_passing(checks: Optional[dict[str, Any]]) -> Optional[bool]:
    """None when there is no check data at all; False if any recorded
    conclusion is not "success" (covers "failure", "cancelled", "timed_out",
    a still-pending job reported as e.g. "neutral"/"skipped" is treated as
    non-passing too, since "passing" must mean every recorded check
    actually succeeded); True only when every recorded conclusion is
    exactly "success"."""
    if not checks:
        return None
    normalized = normalize_checks(checks)
    return all(
        fields.get("conclusion") == "success"
        for fields in normalized.values()
    )


def mergeable_from_state(mergeable_state: Optional[str]) -> Optional[bool]:
    """GitHub's `mergeable_state` is a richer enum than a plain boolean;
    only "clean" unambiguously means "yes, this can merge with no
    conflicts and no failing required checks". "dirty"/"conflicting" is an
    unambiguous no. Everything else ("unstable", "blocked", "behind",
    "unknown", None) is reported as None -- an unresolved state, not a
    guess in either direction."""
    if mergeable_state == "clean":
        return True
    if mergeable_state in {"dirty", "conflicting"}:
        return False
    return None
