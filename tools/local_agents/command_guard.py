"""
Command policy guard for the local agent research loop (P23).

Maintains an allowlist of safe commands and a blocklist of forbidden
substrings. Every command is evaluated before execution.

stdlib only. No subprocess calls in this module.
"""
from __future__ import annotations

import json
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
    "make sync-obsidian",
    "make validate-governance",
    "make test-root",
    "make smoke",
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
