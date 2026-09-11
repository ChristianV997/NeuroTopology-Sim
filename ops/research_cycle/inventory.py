"""Inventory of wrapped research-cycle commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.research_cycle import PACK_ID, PACK_VERSION
from ops.research_cycle.catalog import Catalog, probe_step
from ops.research_cycle.json_util import json_safe


def build_inventory(catalog: Catalog, *, repo_root: Path, python: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for step in catalog.all_steps(include_optional=True):
        available, detail = probe_step(step, repo_root=repo_root, python=python)
        rows.append(
            {
                "id": step.id,
                "order": step.order,
                "title": step.title,
                "optional": step.optional,
                "available": available,
                "probe_detail": detail,
                "wraps": list(step.wraps),
                "timeout_s": step.timeout_s,
                "solver": step.solver,
                "network": step.network,
                "required_flags": list(step.required_flags),
            }
        )
    return json_safe(
        {
            "pack_id": PACK_ID,
            "pack_version": PACK_VERSION,
            "catalog_path": str(catalog.path),
            "repo_root": str(repo_root),
            "steps": rows,
            "note": "Availability is an infrastructure probe, not a scientific verdict.",
        }
    )


def render_inventory_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Research-cycle operator inventory",
        "",
        f"- pack: `{inventory.get('pack_id')}` `{inventory.get('pack_version')}`",
        "",
        "| id | available | wraps | timeout_s | optional |",
        "| --- | --- | --- | --- | --- |",
    ]
    for step in inventory.get("steps") or []:
        wraps = ", ".join(step.get("wraps") or []) or "builtin"
        lines.append(
            f"| `{step.get('id')}` | `{step.get('available')}` | {wraps} | `{step.get('timeout_s')}` | `{step.get('optional')}` |"
        )
    lines.extend(["", inventory.get("note") or "", ""])
    return "\n".join(lines)
