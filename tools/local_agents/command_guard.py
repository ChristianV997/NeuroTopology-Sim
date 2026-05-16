"""
Command policy guard for the local agent research loop (P23/P24).

Maintains an allowlist of safe commands and a blocklist of forbidden
substrings. Every command is evaluated before execution.

CLI (P24):
    python -m tools.local_agents.command_guard --check-defaults
    python -m tools.local_agents.command_guard --command "make ds005620-e2e-mock"
    python -m tools.local_agents.command_guard --json-out outputs/local_agents/policy_check.json

stdlib only. No subprocess calls in this module.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_DEFAULT_ALLOWLIST_PREFIXES: list[str] = [
    # Mock/validation pipeline
    "make ds005620-e2e-mock",
    "make validate-ds005620-e2e",
    "make validate-ds005620-e2e-json",
    "make validate-ds005620-contracts",
    "make ds005620-ci-evidence-report",
    "make ds005620-build-manifest",
    "make ds005620-ontology-eval-mock",
    "make ds005620-export-evidence",
    "make ds005620-paper-skeleton",
    "make ds005620-inspect-runtime",
    "make ds005620-generated-language-check",
    "make ds005620-preflight",
    "make ds005620-real-artifact-plan",
    "make ds005620-real-execution-gate",
    "make ds005620-autonomous-iteration",
    "make ds005620-autonomous-iteration-dry-run",
    "make real-data-source-matrix",
    "make multi-dataset-real-readiness",
    "make multi-dataset-autonomous-iteration",
    "make multi-dataset-autonomous-iteration-dry-run",
    "make validate-real-data-source-matrix",
    "make local-agent-policy-check",
    "make local-agent-loop-dry-run",
    "make local-agent-loop-once",
    "make local-agent-status",
    "make local-agent-healthcheck",
    "make local-agent-scheduler-plan",
    "make sync-obsidian",
    "make validate-governance",
    "make test-root",
    "make smoke",
    "make ds005620-generated-artifact-check",
    "make ontology-language-check",
    "make github-governance-check",
    # P25 local ops runner targets
    "make local-ops-run-once",
    "make local-ops-run-loop-dry-run",
    "make local-ops-run-loop",
    "make local-ops-healthcheck",
    "make local-ops-status",
    "make local-ops-install-plan",
    # Python module invocations (planning, validation, inspection — no real data)
    "python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts",
    "python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --dry-run",
    "python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution",
    "python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration --dry-run",
    "python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration",
    # Validation tools
    "python tools/validate_ds005620_artifacts.py",
    "python tools/validate_ds005620_contracts.py",
    "python tools/validate_ds005620_e2e_execution.py",
    "python tools/validate_ds005620_generated_language.py",
    "python tools/validate_multi_dataset_real_execution_matrix.py",
    "python tools/validate_eeg_signal_artifacts.py",
    "python tools/validate_ontology_claim_language.py",
    # Tests
    "python -m pytest tests/ -q",
    "python -m pytest tests/",
    "pytest tests/",
    # Local agent tools
    "python -m tools.local_agents.research_loop --dry-run",
    "python tools/local_agents/research_loop.py --dry-run",
]

_DEFAULT_BLOCKLIST_SUBSTRINGS: list[str] = [
    # Real data execution flags
    "--execute --peer-reviewed-contract-confirmed",
    # Download tools
    "dandi download",
    "openneuro download",
    "wget",
    "curl",
    "aws s3 cp",
    "s3://",
    "gs://",
    # Destructive shell
    "rm -rf",
    "rm -r",
    # Git write operations — never auto-push/merge/close PRs
    "git push",
    "git merge",
    "git reset --hard",
    "git reset --soft",
    "git checkout --",
    "git rebase",
    "git force",
    "git branch -D",
    "git branch -d",
    # Privilege escalation
    "sudo",
    "su -",
    # Database write
    "drop table",
    "delete from",
    "truncate",
    # Python exec patterns
    "__import__",
    "exec(",
    "eval(",
    # MNE real extraction (blocked — real data)
    "run_eeg_level_m_signal",
    "run_eeg_level_t_signal",
    "extract_mne_signal_blocks",
    "run_ds005620_real_benchmark",
]


@dataclass
class CommandPolicy:
    """Policy configuration for the command guard."""
    allowlist_prefixes: list = field(default_factory=lambda: list(_DEFAULT_ALLOWLIST_PREFIXES))
    blocklist_substrings: list = field(default_factory=lambda: list(_DEFAULT_BLOCKLIST_SUBSTRINGS))
    allow_unlisted_safe: bool = False
    dry_run_always: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "CommandPolicy":
        return cls(
            allowlist_prefixes=list(d.get("allowlist_prefixes", _DEFAULT_ALLOWLIST_PREFIXES)),
            blocklist_substrings=list(d.get("blocklist_substrings", _DEFAULT_BLOCKLIST_SUBSTRINGS)),
            allow_unlisted_safe=bool(d.get("allow_unlisted_safe", False)),
            dry_run_always=bool(d.get("dry_run_always", False)),
        )

    @classmethod
    def load(cls, path: str | Path) -> "CommandPolicy":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Policy file not found: {p}")
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls.from_dict(d.get("command_policy", d))


@dataclass
class CommandDecision:
    """Result of evaluating a command against policy."""
    command: str
    allowed: bool
    reason: str
    category: str
    matched_blocklist: str = ""
    matched_allowlist: str = ""


def evaluate_command(command: str, policy: Optional[CommandPolicy] = None) -> CommandDecision:
    """Evaluate command against policy. Returns CommandDecision."""
    if policy is None:
        policy = CommandPolicy()

    cmd = command.strip()

    # Check blocklist first — always wins regardless of allowlist
    for bad in policy.blocklist_substrings:
        if bad.lower() in cmd.lower():
            return CommandDecision(
                command=cmd,
                allowed=False,
                reason=f"Blocked: matches blocklist substring '{bad}'",
                category="blocked_policy",
                matched_blocklist=bad,
            )

    # Check allowlist
    for prefix in policy.allowlist_prefixes:
        if cmd.startswith(prefix) or cmd == prefix:
            return CommandDecision(
                command=cmd,
                allowed=True,
                reason=f"Allowed: matches allowlist prefix '{prefix}'",
                category="allowed_policy",
                matched_allowlist=prefix,
            )

    # Not in either list
    if policy.allow_unlisted_safe:
        return CommandDecision(
            command=cmd,
            allowed=True,
            reason="Allowed: not in blocklist and allow_unlisted_safe=True",
            category="allowed_unlisted",
        )

    return CommandDecision(
        command=cmd,
        allowed=False,
        reason="Blocked: command not in allowlist (allow_unlisted_safe=False)",
        category="blocked_not_allowlisted",
    )


# ---------------------------------------------------------------------------
# P24 CLI
# ---------------------------------------------------------------------------

_BLOCKED_EXAMPLES = [
    "wget https://openneuro.org/data.zip",
    "curl -O https://dandiarchive.org/data.tar",
    "dandi download https://dandiarchive.org/dandiset/000001",
    "git push origin main",
    "git merge feature-branch",
    "rm -rf /data",
    "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --execute --peer-reviewed-contract-confirmed",
    "aws s3 cp s3://bucket/data.zip .",
    "sudo apt install something",
]

_ALLOWED_EXAMPLES = [
    "make ds005620-e2e-mock",
    "make validate-ds005620-contracts",
    "make ds005620-real-artifact-plan",
    "make real-data-source-matrix",
    "make local-agent-loop-dry-run",
]


def check_policy_defaults(policy: Optional[CommandPolicy] = None) -> dict:
    """Run default policy validation. Returns result dict with ok, violations, warnings."""
    if policy is None:
        policy = CommandPolicy()

    violations: list[str] = []
    warnings: list[str] = []

    if not policy.allowlist_prefixes:
        violations.append("allowlist_prefixes is empty")
    if not policy.blocklist_substrings:
        violations.append("blocklist_substrings is empty")

    blocked_examples_passed = True
    for cmd in _BLOCKED_EXAMPLES:
        dec = evaluate_command(cmd, policy)
        if dec.allowed:
            violations.append(f"Dangerous command not blocked: {cmd!r}")
            blocked_examples_passed = False

    allowed_examples_passed = True
    for cmd in _ALLOWED_EXAMPLES:
        dec = evaluate_command(cmd, policy)
        if not dec.allowed:
            warnings.append(f"Expected safe command not allowed: {cmd!r}")
            allowed_examples_passed = False

    # Verify key blocklist substrings present
    required_blocklist = ["wget", "curl", "dandi download", "git push", "git merge", "rm -rf"]
    for bad in required_blocklist:
        if bad not in policy.blocklist_substrings:
            violations.append(f"Required blocklist substring missing: {bad!r}")

    ok = len(violations) == 0
    return {
        "ok": ok,
        "allowed_count": len(policy.allowlist_prefixes),
        "blocked_count": len(policy.blocklist_substrings),
        "blocked_examples_passed": blocked_examples_passed,
        "allowed_examples_passed": allowed_examples_passed,
        "guardrails": {
            "executes_real_data": False,
            "downloads_data": False,
            "auto_confirms_peer_review": False,
            "auto_pushes_git": False,
            "auto_merges_pr": False,
        },
        "violations": violations,
        "warnings": warnings,
    }


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Command policy guard CLI (P24)")
    p.add_argument("--policy", default=None, help="Path to command_policy.json")
    p.add_argument("--check-defaults", action="store_true", default=False,
                   help="Validate default policy configuration")
    p.add_argument("--command", default=None, help="Evaluate a specific command")
    p.add_argument("--json-out", default=None, help="Write JSON result to this path")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)

    policy: Optional[CommandPolicy] = None
    policy_path = args.policy or "configs/local_agents/command_policy.json"
    try:
        if Path(policy_path).exists():
            policy = CommandPolicy.load(policy_path)
        else:
            policy = CommandPolicy()
    except Exception as exc:
        print(f"ERROR loading policy: {exc}", file=sys.stderr)
        return 2

    result: dict = {"ok": True, "policy_path": policy_path}

    if args.command:
        dec = evaluate_command(args.command, policy)
        result = {
            "ok": dec.allowed,
            "policy_path": policy_path,
            "command": args.command,
            "allowed": dec.allowed,
            "reason": dec.reason,
            "category": dec.category,
            "matched_blocklist": dec.matched_blocklist,
            "matched_allowlist": dec.matched_allowlist,
            "violations": [] if dec.allowed else [dec.reason],
            "warnings": [],
        }
        exit_code = 0 if dec.allowed else 1
    elif args.check_defaults:
        check = check_policy_defaults(policy)
        result = {"policy_path": policy_path, **check}
        exit_code = 0 if check["ok"] else 1
    else:
        check = check_policy_defaults(policy)
        result = {"policy_path": policy_path, **check}
        exit_code = 0 if check["ok"] else 1

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
