"""
Healthcheck for the local continuous operations runner (P25).

Checks safety, policy, path writability, and Makefile target availability.

CLI:
    python -m tools.local_ops.healthcheck --out outputs/local_ops/local_ops_healthcheck.json

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from tools.local_agents.command_guard import CommandPolicy, check_policy_defaults, evaluate_command


_DANGEROUS_COMMANDS = [
    "wget https://example.com/data.zip",
    "curl -O https://openneuro.org/file.tar",
    "dandi download https://dandiarchive.org/dandiset/000001",
    "git push origin main",
    "git merge feature",
    "rm -rf /data",
    "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --execute --peer-reviewed-contract-confirmed",
    "aws s3 cp s3://bucket/file .",
    "sudo rm -rf /",
    "gh pr merge 123",
    "gh pr close 123",
]

_REQUIRED_MAKEFILE_TARGETS = [
    "local-agent-policy-check",
    "local-agent-healthcheck",
    "local-agent-loop-once",
    "local-agent-status",
    "sync-obsidian",
    "local-ops-run-once",
    "local-ops-run-loop-dry-run",
    "local-ops-run-loop",
    "local-ops-healthcheck",
    "local-ops-status",
    "local-ops-install-plan",
]


def _check_command_policy() -> dict:
    try:
        policy_path = Path("configs/local_agents/command_policy.json")
        if policy_path.exists():
            policy = CommandPolicy.load(policy_path)
        else:
            policy = CommandPolicy()
        check = check_policy_defaults(policy)
        return {
            "name": "command_policy_valid",
            "ok": check["ok"],
            "detail": f"violations={check['violations']}, warnings={check['warnings']}",
        }
    except Exception as exc:
        return {"name": "command_policy_valid", "ok": False, "detail": str(exc)}


def _check_local_ops_policy(policy_path: Optional[Path] = None) -> dict:
    """Check that local_ops_policy.json has no forbidden real-execution commands."""
    p = policy_path or Path("configs/local_ops/local_ops_policy.json")
    if not p.exists():
        return {"name": "local_ops_policy_present", "ok": True, "detail": "not_found (will use defaults)"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        seq = data.get("safe_command_sequence", []) + data.get("optional_safe_commands", [])
        real_exec_patterns = [
            "--execute --peer-reviewed-contract-confirmed",
            "dandi download",
            "wget",
            "curl",
            "git push",
            "gh pr merge",
            "run_ds005620_real_benchmark",
        ]
        violations = []
        for cmd in seq:
            for pat in real_exec_patterns:
                if pat in cmd:
                    violations.append(f"Real-execution pattern {pat!r} in command: {cmd!r}")
        ok = len(violations) == 0
        return {
            "name": "local_ops_policy_no_real_execution",
            "ok": ok,
            "detail": "No real-execution commands in policy" if ok else str(violations),
        }
    except Exception as exc:
        return {"name": "local_ops_policy_no_real_execution", "ok": False, "detail": str(exc)}


def _check_dangerous_commands_blocked() -> dict:
    policy = CommandPolicy()
    blocked_all = True
    failures = []
    for cmd in _DANGEROUS_COMMANDS:
        dec = evaluate_command(cmd, policy)
        if dec.allowed:
            blocked_all = False
            failures.append(cmd)
    return {
        "name": "dangerous_commands_blocked",
        "ok": blocked_all,
        "detail": f"All {len(_DANGEROUS_COMMANDS)} dangerous examples blocked" if blocked_all
                  else f"FAILED: {failures}",
    }


def _check_outputs_writable(path: Path, name: str) -> dict:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".healthcheck_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return {"name": name, "ok": True, "detail": str(path)}
    except Exception as exc:
        return {"name": name, "ok": False, "detail": str(exc)}


def _check_vault_writable(vault: str) -> dict:
    vault_path = Path(vault)
    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        return {"name": "vault_writable", "ok": True, "detail": str(vault_path)}
    except Exception as exc:
        return {"name": "vault_writable", "ok": False, "detail": str(exc)}


def _check_makefile_targets() -> dict:
    makefile = Path("Makefile")
    if not makefile.exists():
        return {"name": "makefile_targets", "ok": False, "detail": "Makefile not found"}
    content = makefile.read_text(encoding="utf-8")
    missing = [t for t in _REQUIRED_MAKEFILE_TARGETS if t not in content]
    ok = len(missing) == 0
    return {
        "name": "makefile_targets",
        "ok": ok,
        "detail": f"All {len(_REQUIRED_MAKEFILE_TARGETS)} targets present" if ok
                  else f"Missing: {missing}",
    }


def _check_no_real_execution_in_makefile_ops_targets() -> dict:
    makefile = Path("Makefile")
    if not makefile.exists():
        return {"name": "makefile_ops_safe", "ok": True, "detail": "Makefile not found"}
    content = makefile.read_text(encoding="utf-8")
    real_exec_patterns = [
        "--execute --peer-reviewed-contract-confirmed",
        "dandi download",
        "run_ds005620_real_benchmark",
    ]
    violations = []
    in_ops_block = False
    for line in content.splitlines():
        if line.startswith("local-ops-"):
            in_ops_block = True
        elif line and not line[0].isspace() and not line.startswith("\t"):
            in_ops_block = False
        if in_ops_block:
            for pat in real_exec_patterns:
                if pat in line:
                    violations.append(f"Real-execution pattern {pat!r} in Makefile local-ops target")
    ok = len(violations) == 0
    return {
        "name": "makefile_ops_safe",
        "ok": ok,
        "detail": "No real-execution in local-ops targets" if ok else str(violations),
    }


def _check_ollama() -> dict:
    try:
        from tools.local_agents.ollama_client import OllamaClient
        client = OllamaClient()
        available = client.is_available()
        return {
            "name": "ollama_available",
            "ok": True,
            "detail": "available" if available else "not_running (optional)",
            "available": available,
        }
    except Exception as exc:
        return {"name": "ollama_available", "ok": True, "detail": f"optional: {exc}", "available": False}


def run_healthcheck(
    output_root: str | Path = "outputs/local_ops",
    local_agent_root: str | Path = "outputs/local_agents",
    vault: str = "obsidian",
) -> dict:
    """Run all P25 healthchecks and return result dict."""
    out = Path(output_root)
    lag = Path(local_agent_root)

    checks = [
        _check_command_policy(),
        _check_local_ops_policy(),
        _check_dangerous_commands_blocked(),
        _check_outputs_writable(out, "outputs_local_ops_writable"),
        _check_outputs_writable(lag, "outputs_local_agents_writable"),
        _check_vault_writable(vault),
        _check_makefile_targets(),
        _check_no_real_execution_in_makefile_ops_targets(),
        _check_ollama(),
    ]

    non_blocking_names = {"ollama_available"}
    blockers = [c for c in checks if not c["ok"] and c["name"] not in non_blocking_names]
    warnings = [c for c in checks if not c["ok"] and c not in blockers]

    ollama_check = next((c for c in checks if c["name"] == "ollama_available"), {})

    return {
        "ok": len(blockers) == 0,
        "checks": checks,
        "blockers": [c["name"] for c in blockers],
        "warnings": [c["name"] for c in warnings],
        "ollama_available": ollama_check.get("available", False),
        "policy_ok": next((c["ok"] for c in checks if c["name"] == "command_policy_valid"), False),
        "unsafe_command_blocks_ok": next(
            (c["ok"] for c in checks if c["name"] == "dangerous_commands_blocked"), False
        ),
        "make_targets_available": next(
            (c["ok"] for c in checks if c["name"] == "makefile_targets"), False
        ),
        "local_ops_policy_safe": next(
            (c["ok"] for c in checks if c["name"] == "local_ops_policy_no_real_execution"), False
        ),
        "guardrails": {
            "executes_real_data": False,
            "downloads_data": False,
            "auto_confirms_peer_review": False,
            "auto_pushes_git": False,
            "auto_merges_pr": False,
        },
    }


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local ops healthcheck (P25)")
    p.add_argument("--output-root", default="outputs/local_ops")
    p.add_argument("--local-agent-root", default="outputs/local_agents")
    p.add_argument("--vault", default="obsidian")
    p.add_argument("--out", default="outputs/local_ops/local_ops_healthcheck.json")
    args = p.parse_args(argv)

    result = run_healthcheck(
        output_root=args.output_root,
        local_agent_root=args.local_agent_root,
        vault=args.vault,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
