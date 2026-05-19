"""
Local agent healthcheck module (P24).

Runs a series of safety and readiness checks for the local agent runtime.
Never executes real commands or data.

CLI:
    python -m tools.local_agents.healthcheck \
        --root outputs/btc_icft \
        --local-agent-root outputs/local_agents \
        --out outputs/local_agents/local_agent_healthcheck.json

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
]

_REQUIRED_MAKEFILE_TARGETS = [
    "local-agent-policy-check",
    "local-agent-loop-dry-run",
    "local-agent-loop-once",
    "local-agent-status",
    "local-agent-healthcheck",
    "local-agent-scheduler-plan",
    "sync-obsidian",
    "ds005620-autonomous-iteration",
    "real-data-source-matrix",
    "multi-dataset-autonomous-iteration",
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


def _check_no_real_execution_allowlisted() -> dict:
    policy = CommandPolicy()
    real_exec_patterns = [
        "--execute --peer-reviewed-contract-confirmed",
        "dandi download",
        "openneuro download",
        "wget",
        "git push",
        "git merge",
        "run_ds005620_real_benchmark",
    ]
    violations = []
    for prefix in policy.allowlist_prefixes:
        for pattern in real_exec_patterns:
            if pattern in prefix:
                violations.append(f"Allowlist entry contains blocked pattern: {prefix!r}")
    ok = len(violations) == 0
    return {
        "name": "no_real_execution_allowlisted",
        "ok": ok,
        "detail": "No real-execution patterns in allowlist" if ok else str(violations),
    }


def _check_no_github_push_allowlisted() -> dict:
    policy = CommandPolicy()
    gh_patterns = ["git push", "git merge", "gh pr merge", "git reset --hard", "git rebase"]
    violations = []
    for prefix in policy.allowlist_prefixes:
        for pattern in gh_patterns:
            if pattern in prefix:
                violations.append(f"GitHub write pattern in allowlist: {prefix!r}")
    ok = len(violations) == 0
    return {
        "name": "no_github_push_allowlisted",
        "ok": ok,
        "detail": "No GitHub push/merge patterns in allowlist" if ok else str(violations),
    }


def _check_outputs_writable(local_agent_root: Path) -> dict:
    try:
        local_agent_root.mkdir(parents=True, exist_ok=True)
        test_file = local_agent_root / ".healthcheck_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return {"name": "outputs_local_agents_writable", "ok": True, "detail": str(local_agent_root)}
    except Exception as exc:
        return {"name": "outputs_local_agents_writable", "ok": False, "detail": str(exc)}


def _check_obsidian_path(vault: str) -> dict:
    vault_path = Path(vault)
    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        return {"name": "obsidian_vault_writable", "ok": True, "detail": str(vault_path)}
    except Exception as exc:
        return {"name": "obsidian_vault_writable", "ok": False, "detail": str(exc)}


def _check_outputs_btc_icft(root: Path) -> dict:
    exists = root.exists()
    return {
        "name": "outputs_btc_icft_present",
        "ok": True,
        "detail": "present" if exists else "not_available (will be created by pipeline runs)",
    }


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


def _check_language_validation(root: Path) -> dict:
    lang_path = root / "ds005620_generated_language_validation.json"
    if not lang_path.exists():
        return {"name": "language_validation", "ok": True, "detail": "not_yet_run"}
    try:
        data = json.loads(lang_path.read_text(encoding="utf-8"))
        violations = data.get("violations_found", False)
        return {
            "name": "language_validation",
            "ok": not violations,
            "detail": "violations_found" if violations else "clean",
        }
    except Exception as exc:
        return {"name": "language_validation", "ok": False, "detail": str(exc)}


def run_healthcheck(
    root: str | Path = "outputs/btc_icft",
    local_agent_root: str | Path = "outputs/local_agents",
    vault: str = "obsidian",
) -> dict:
    """Run all healthchecks and return result dict."""
    root = Path(root)
    lag_root = Path(local_agent_root)

    checks = [
        _check_command_policy(),
        _check_dangerous_commands_blocked(),
        _check_no_real_execution_allowlisted(),
        _check_no_github_push_allowlisted(),
        _check_outputs_writable(lag_root),
        _check_obsidian_path(vault),
        _check_outputs_btc_icft(root),
        _check_makefile_targets(),
        _check_ollama(),
        _check_language_validation(root),
    ]

    blockers = [c for c in checks if not c["ok"] and c["name"] not in (
        "ollama_available", "outputs_btc_icft_present"
    )]
    warnings = [c for c in checks if not c["ok"] and c not in blockers]

    ollama_check = next((c for c in checks if c["name"] == "ollama_available"), {})
    ok = len(blockers) == 0

    return {
        "ok": ok,
        "checks": checks,
        "blockers": [c["name"] for c in blockers],
        "warnings": [c["name"] for c in warnings],
        "ollama_available": ollama_check.get("available", False),
        "obsidian_writable": next(
            (c["ok"] for c in checks if c["name"] == "obsidian_vault_writable"), False
        ),
        "policy_ok": next(
            (c["ok"] for c in checks if c["name"] == "command_policy_valid"), False
        ),
        "unsafe_command_blocks_ok": next(
            (c["ok"] for c in checks if c["name"] == "dangerous_commands_blocked"), False
        ),
        "make_targets_available": next(
            (c["ok"] for c in checks if c["name"] == "makefile_targets"), False
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
    p = argparse.ArgumentParser(description="Local agent healthcheck (P24)")
    p.add_argument("--root", default="outputs/btc_icft")
    p.add_argument("--local-agent-root", default="outputs/local_agents")
    p.add_argument("--vault", default="obsidian")
    p.add_argument("--out", default="outputs/local_agents/local_agent_healthcheck.json")
    args = p.parse_args(argv)

    result = run_healthcheck(
        root=args.root,
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
