"""
Scheduler plan generator for the local agent research loop (P24).

Produces a scheduler_plan.json and scheduler_report.md with cron, systemd,
launchd, and OpenClaw trigger examples. Does NOT implement a daemon.

CLI:
    python -m tools.local_agents.scheduler_plan --out outputs/local_agents

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


_PLAN_VERSION = "p24.0"

_GUARDRAILS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "auto_pushes_git": False,
    "auto_merges_pr": False,
    "auto_closes_pr": False,
    "infers_labels": False,
    "fabricates_targets": False,
    "implements_daemon": False,
}

_FORBIDDEN_COMMANDS = [
    "--execute --peer-reviewed-contract-confirmed",
    "dandi download",
    "openneuro download",
    "wget",
    "curl",
    "aws s3 cp",
    "git push",
    "git merge",
    "rm -rf",
    "run_ds005620_real_benchmark",
    "run_eeg_level_m_signal",
    "run_eeg_level_t_signal",
]

_HUMAN_REQUIRED_BOUNDARIES = [
    "peer_review_before_real_execution",
    "label_contract_declaration",
    "git_push_and_pr_merge",
    "dataset_activation_declaration",
    "real_benchmark_invocation",
]

_CRON_EXAMPLE = """# Run local agent loop once per hour (safe planning/validation only)
# Add to crontab with: crontab -e
0 * * * * cd /path/to/ScienceR-Dsim && make local-agent-loop-once >> /var/log/local_agent.log 2>&1

# Dry-run every 15 minutes (no commands executed)
*/15 * * * * cd /path/to/ScienceR-Dsim && make local-agent-loop-dry-run >> /var/log/local_agent_dry.log 2>&1
"""

_SYSTEMD_EXAMPLE = """# /etc/systemd/system/local-agent-loop.service
[Unit]
Description=ScienceR-Dsim local agent research loop
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/ScienceR-Dsim
ExecStart=/usr/bin/make local-agent-loop-once
User=researcher
StandardOutput=journal
StandardError=journal

# /etc/systemd/system/local-agent-loop.timer
[Unit]
Description=Run local-agent-loop-once every hour

[Timer]
OnBootSec=5min
OnUnitActiveSec=60min
Unit=local-agent-loop.service

[Install]
WantedBy=timers.target

# Enable with: systemctl enable --now local-agent-loop.timer
"""

_LAUNCHD_EXAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sciencer.local-agent-loop</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/make</string>
        <string>-C</string>
        <string>/path/to/ScienceR-Dsim</string>
        <string>local-agent-loop-once</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/tmp/local_agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/local_agent_err.log</string>
</dict>
</plist>
<!-- Load with: launchctl load ~/Library/LaunchAgents/com.sciencer.local-agent-loop.plist -->
"""

_OPENCLAW_EXAMPLE = """# OpenClaw trigger design (reference only; not implemented here)
#
# When OpenClaw receives a trigger from the operator, it dispatches:
#   make local-agent-loop-once
#
# OpenClaw evaluates the command via command_guard before execution.
# All forbidden command substrings are rejected at dispatch time.
#
# Trigger event: { "type": "schedule", "target": "local-agent-loop-once" }
# Response: loop state + next_action written to outputs/local_agents/
#
# Human operator then reviews:
#   outputs/local_agents/research_loop_next_action.json
#   outputs/local_agents/local_agent_status.json
"""

_DOCKER_NOTE = """# Docker / containerized deployment is a future phase (not yet implemented).
#
# When implemented, the container will:
#   - Run as a non-root user
#   - Mount outputs/ as a volume
#   - Execute make local-agent-loop-once on each trigger
#   - Never expose real data credentials
#   - Never auto-push to GitHub
#
# No Docker support is added in this PR.
"""


def build_scheduler_plan() -> dict:
    return {
        "plan_version": _PLAN_VERSION,
        "safe_to_schedule": True,
        "recommended_interval_minutes": 60,
        "command": "make local-agent-loop-once",
        "dry_run_command": "make local-agent-loop-dry-run",
        "cron_example": _CRON_EXAMPLE.strip(),
        "systemd_example": _SYSTEMD_EXAMPLE.strip(),
        "launchd_example": _LAUNCHD_EXAMPLE.strip(),
        "openclaw_trigger_design": _OPENCLAW_EXAMPLE.strip(),
        "docker_future_note": _DOCKER_NOTE.strip(),
        "daemon_implemented": False,
        "guardrails": dict(_GUARDRAILS),
        "forbidden_commands": list(_FORBIDDEN_COMMANDS),
        "human_required_boundaries": list(_HUMAN_REQUIRED_BOUNDARIES),
    }


def build_scheduler_report(plan: dict) -> str:
    lines = [
        "# Local Agent Scheduler Plan (P24)",
        "",
        "This document describes how to safely schedule the local autonomous research loop.",
        "No background daemon is implemented in this release.",
        "",
        "## Why no daemon yet",
        "",
        "The loop is designed to be safe to run via cron, systemd, or OpenClaw triggers.",
        "A daemon would add complexity without adding safety. The current design:",
        "- Runs one iteration per invocation",
        "- Writes outputs to outputs/local_agents/",
        "- Stops at all real-data and human-review boundaries",
        "",
        "## Recommended schedule",
        "",
        f"- Command: `{plan['command']}`",
        f"- Dry-run: `{plan['dry_run_command']}`",
        f"- Interval: every {plan['recommended_interval_minutes']} minutes",
        f"- Safe to schedule: `{plan['safe_to_schedule']}`",
        "",
        "## Cron example",
        "",
        "```cron",
        plan["cron_example"],
        "```",
        "",
        "## systemd timer example",
        "",
        "```ini",
        plan["systemd_example"],
        "```",
        "",
        "## macOS launchd example",
        "",
        "```xml",
        plan["launchd_example"],
        "```",
        "",
        "## OpenClaw trigger design",
        "",
        "```",
        plan["openclaw_trigger_design"],
        "```",
        "",
        "## Docker future phase",
        "",
        "```",
        plan["docker_future_note"],
        "```",
        "",
        "## Guardrails",
        "",
        "All hardcoded `false`:",
        "",
    ]
    for k, v in plan["guardrails"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Human-required boundaries",
        "",
        "These steps are **never automated** and always require human action:",
        "",
    ]
    for boundary in plan["human_required_boundaries"]:
        lines.append(f"- `{boundary}`")
    lines += ["", "---", "", "#local-agent #scheduler #sciencer-dsim"]
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local agent scheduler plan (P24)")
    p.add_argument("--out", default="outputs/local_agents", help="Output directory")
    args = p.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plan = build_scheduler_plan()
    report = build_scheduler_report(plan)

    plan_path = out / "scheduler_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    report_path = out / "scheduler_report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"scheduler_plan.json → {plan_path}")
    print(f"scheduler_report.md → {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
