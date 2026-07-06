"""
Workboard builder for the local ops action queue (P26).

Reads action_queue.json and produces workboard.json + workboard.md organized
into columns (Now / Next / Blocked / Manual / Agent Ready / Done-Superseded)
grouped by owner and priority.

CLI:
    python -m tools.local_ops.workboard \
        --queue outputs/local_ops/action_queue.json \
        --out outputs/local_ops

stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Optional


_COLUMNS = ("Now", "Next", "Blocked", "Manual", "Agent Ready", "Done/Superseded")


def _assign_column(action: dict) -> str:
    status = action.get("status", "proposed")
    priority = action.get("priority", "P2")

    if status == "superseded":
        return "Done/Superseded"
    if status == "blocked":
        return "Blocked"
    if status == "manual_only" or action.get("manual_required", False):
        return "Manual"
    if status == "ready_for_agent":
        if priority == "P0":
            return "Now"
        if priority == "P1":
            return "Next"
        return "Agent Ready"
    if status == "ready_for_human":
        return "Manual"
    # proposed
    if priority == "P0":
        return "Now"
    if priority == "P1":
        return "Next"
    return "Agent Ready"


def build_workboard(actions: list[dict]) -> dict:
    board: dict = {col: [] for col in _COLUMNS}
    for a in actions:
        col = _assign_column(a)
        board[col].append(a)

    # Also produce a by-owner view
    by_owner: dict = {}
    for a in actions:
        owner = a.get("owner", "unknown")
        by_owner.setdefault(owner, []).append(a)

    return {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "columns": {col: [_row(a) for a in board[col]] for col in _COLUMNS},
        "by_owner": {owner: [_row(a) for a in items] for owner, items in by_owner.items()},
        "guardrails": {
            "executes_real_data": False,
            "downloads_data": False,
            "auto_submits_issues": False,
            "auto_creates_prs": False,
        },
    }


def _row(a: dict) -> dict:
    return {
        "action_id": a.get("action_id", ""),
        "title": a.get("title", ""),
        "priority": a.get("priority", "P2"),
        "owner": a.get("owner", ""),
        "status": a.get("status", "proposed"),
        "category": a.get("category", ""),
        "score": a.get("score", 0.0),
        "manual_required": a.get("manual_required", False),
        "safe_to_auto_run": a.get("safe_to_auto_run", False),
    }


def render_workboard_md(board: dict) -> str:
    lines = [
        "# Local Ops Workboard (P26)",
        "",
        f"- generated_at: `{board['generated_at']}`",
        "",
        "## Columns",
        "",
    ]
    columns = board.get("columns", {})
    for col in _COLUMNS:
        items = columns.get(col, [])
        lines += [f"### {col}", ""]
        if not items:
            lines.append("_(empty)_")
            lines.append("")
            continue
        # Sort by priority then title
        rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        items_sorted = sorted(items, key=lambda a: (rank.get(a.get("priority", "P2"), 9), a.get("title", "")))
        for a in items_sorted:
            lines.append(
                f"- [{a['priority']}] **{a['title']}** — owner `{a['owner']}`, status `{a['status']}`"
            )
        lines.append("")

    lines += ["## By Owner", ""]
    by_owner = board.get("by_owner", {})
    for owner in sorted(by_owner.keys()):
        items = by_owner[owner]
        lines += [f"### {owner}", ""]
        if not items:
            lines.append("_(none)_")
            lines.append("")
            continue
        for a in items:
            lines.append(
                f"- [{a['priority']}] **{a['title']}** (status=`{a['status']}`)"
            )
        lines.append("")

    lines += [
        "## Guardrails",
        "",
    ]
    for k, v in board.get("guardrails", {}).items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "---",
        "#local-ops #workboard #sciencer-dsim",
    ]
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local ops workboard (P26)")
    p.add_argument("--queue", default="outputs/local_ops/action_queue.json")
    p.add_argument("--out", default="outputs/local_ops")
    args = p.parse_args(argv)

    queue_path = Path(args.queue)
    if queue_path.exists():
        data = json.loads(queue_path.read_text(encoding="utf-8"))
        actions = data.get("actions", [])
    else:
        actions = []

    board = build_workboard(actions)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "workboard.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
    (out / "workboard.md").write_text(render_workboard_md(board), encoding="utf-8")
    print(f"workboard.json → {out / 'workboard.json'}")
    print(f"workboard.md   → {out / 'workboard.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
