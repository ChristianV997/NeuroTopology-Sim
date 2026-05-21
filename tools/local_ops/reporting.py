"""
Report generator for the local continuous operations runner (P25).

Produces local_ops_report.md from a run state dict.

stdlib only.
"""
from __future__ import annotations

from typing import Optional


_NEVER_DOES = [
    "Executes real dataset benchmarks automatically",
    "Downloads OpenNeuro, DANDI, PhysioNet, or S3 data",
    "Runs MNE extraction automatically",
    "Runs Level M or Level T real feature extraction",
    "Auto-confirms peer review on behalf of a human",
    "Infers labels or fabricates targets",
    "Weakens ontology quarantine or language firewall",
    "Auto-pushes to git or auto-merges PRs",
    "Auto-closes GitHub issues or PRs",
    "Requires or stores cloud API keys",
    "Installs a background daemon",
    "Runs infinitely without explicit max_iterations",
]

_ALWAYS_MANUAL = [
    "peer_review_before_real_execution",
    "label_contract_declaration",
    "git_push_and_pr_merge",
    "dataset_activation_declaration",
    "real_benchmark_invocation",
]


def build_ops_report(
    runner_version: str,
    mode: str,
    iterations_completed: int,
    safe_commands_succeeded: int,
    safe_commands_failed: int,
    commands_blocked: int,
    status: str,
    next_action: str,
    dataset_next_actions: Optional[dict] = None,
    obsidian_synced: bool = False,
    warnings: Optional[list] = None,
    guardrails: Optional[dict] = None,
) -> str:
    """Render local_ops_report.md content."""
    if warnings is None:
        warnings = []
    if dataset_next_actions is None:
        dataset_next_actions = {}
    if guardrails is None:
        guardrails = {}

    lines = [
        "# Local Continuous Operations Runner (P25)",
        "",
        "## Summary",
        "",
        f"- runner_version: `{runner_version}`",
        f"- mode: `{mode}`",
        f"- status: `{status}`",
        f"- iterations_completed: `{iterations_completed}`",
        f"- safe_commands_succeeded: `{safe_commands_succeeded}`",
        f"- safe_commands_failed: `{safe_commands_failed}`",
        f"- commands_blocked: `{commands_blocked}`",
        f"- obsidian_synced: `{obsidian_synced}`",
        "",
        "## Current Next Action",
        "",
        f"`{next_action}`",
        "",
    ]

    if dataset_next_actions:
        lines += [
            "## Dataset Readiness Summary",
            "",
        ]
        for ds, action in dataset_next_actions.items():
            lines.append(f"- `{ds}`: `{action}`")
        lines.append("")

    if warnings:
        lines += [
            "## Warnings",
            "",
        ]
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines += [
        "## Guardrails",
        "",
        "All hardcoded `false` — these can never be activated by the runner:",
        "",
    ]
    if guardrails:
        for k, v in guardrails.items():
            lines.append(f"- `{k}`: `{v}`")
    else:
        lines.append("- (see configs/local_ops/local_ops_policy.json)")
    lines.append("")

    lines += [
        "## What This Runner Never Does",
        "",
    ]
    for item in _NEVER_DOES:
        lines.append(f"- {item}")
    lines.append("")

    lines += [
        "## What Remains Manual",
        "",
        "These steps always require a human operator:",
        "",
    ]
    for boundary in _ALWAYS_MANUAL:
        lines.append(f"- `{boundary}`")
    lines.append("")

    lines += [
        "## How to Schedule Externally",
        "",
        "See `outputs/local_ops/install_plan.md` for cron, systemd, launchd, and OpenClaw examples.",
        "The runner is not installed automatically.",
        "",
        "---",
        "#local-ops #sciencer-dsim",
    ]
    return "\n".join(lines)
