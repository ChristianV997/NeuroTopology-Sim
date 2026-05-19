"""
Status module for the local continuous operations runner (P25).

Aggregates runner state, local agent status, and dataset next actions.

CLI:
    python -m tools.local_ops.status \
        --out outputs/local_ops/local_ops_status.json \
        --local-agent-root outputs/local_agents \
        --btc-root outputs/btc_icft

stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Optional


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_ops_status(
    output_root: str | Path = "outputs/local_ops",
    local_agent_root: str | Path = "outputs/local_agents",
    btc_root: str | Path = "outputs/btc_icft",
) -> dict:
    """Build comprehensive status dict for the local ops runner."""
    out = Path(output_root)
    lag = Path(local_agent_root)
    btc = Path(btc_root)

    # Runner state
    runner_state = _load_json(out / "local_ops_state.json") or {}
    last_run_status = runner_state.get("status", "not_run")
    last_run_time = runner_state.get("generated_at", "never")
    next_action = runner_state.get("next_action", "run_local_ops_once")
    manual_required = runner_state.get("manual_required", False)
    human_review_required = runner_state.get("human_review_required", False)

    # Local agent status
    la_status = _load_json(lag / "local_agent_status.json") or {}
    la_health = _load_json(lag / "local_agent_healthcheck.json") or {}
    la_next = _load_json(lag / "research_loop_next_action.json") or {}

    local_agent_health = {
        "ok": la_health.get("ok", None),
        "policy_ok": la_health.get("policy_ok", None),
        "unsafe_command_blocks_ok": la_health.get("unsafe_command_blocks_ok", None),
        "make_targets_available": la_health.get("make_targets_available", None),
        "ollama_available": la_health.get("ollama_available", False),
    }

    # Dataset next actions
    mds_next = _load_json(btc / "multi_dataset_real_execution" / "next_actions.json") or {}
    iter_next = _load_json(btc / "multi_dataset_autonomous_iteration" / "iteration_next_actions.json") or {}
    ds_iter_next = _load_json(btc / "ds005620_autonomous_iteration" / "iteration_next_action.json") or {}

    dataset_next_actions: dict = {}
    if mds_next:
        dataset_next_actions.update({k: v for k, v in mds_next.items() if isinstance(v, str)})
    if iter_next:
        dataset_next_actions.update({k: v for k, v in iter_next.items() if isinstance(v, str)})
    if ds_iter_next:
        ds_action = ds_iter_next.get("next_action", "not_available")
        if isinstance(ds_action, str):
            dataset_next_actions["DS005620"] = ds_action

    # Determine blocked_by
    blocked_by: list[str] = []
    if la_status.get("blocked_by"):
        blocked_by.extend(la_status["blocked_by"])

    warnings: list[str] = []
    if not la_status:
        warnings.append("local_agent_status.json not yet generated; run: make local-agent-status")
    if not la_health:
        warnings.append("local_agent_healthcheck.json not yet generated; run: make local-agent-healthcheck")

    # If last run returned a next_action, prefer it; otherwise use la_status
    if last_run_status == "not_run":
        next_action = la_status.get("next_action", "run_local_ops_once")

    return {
        "ok": True,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "last_run_status": last_run_status,
        "last_run_time": last_run_time,
        "next_action": next_action,
        "blocked_by": blocked_by,
        "manual_required": manual_required,
        "human_review_required": human_review_required,
        "dataset_next_actions": dataset_next_actions,
        "local_agent_health": local_agent_health,
        "warnings": warnings,
        "guardrails": {
            "executes_real_data": False,
            "downloads_data": False,
            "auto_confirms_peer_review": False,
            "auto_pushes_git": False,
            "auto_merges_pr": False,
        },
    }


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local ops status (P25)")
    p.add_argument("--out", default="outputs/local_ops/local_ops_status.json")
    p.add_argument("--output-root", default="outputs/local_ops")
    p.add_argument("--local-agent-root", default="outputs/local_agents")
    p.add_argument("--btc-root", default="outputs/btc_icft")
    args = p.parse_args(argv)

    status = build_ops_status(
        output_root=args.output_root,
        local_agent_root=args.local_agent_root,
        btc_root=args.btc_root,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
