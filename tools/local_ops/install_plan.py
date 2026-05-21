"""
Install plan generator for the local continuous operations runner (P25).

Produces install_plan.json and install_plan.md with cron, systemd, launchd,
and OpenClaw trigger examples. Does NOT install anything.

CLI:
    python -m tools.local_ops.install_plan --out outputs/local_ops

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


_PLAN_VERSION = "p25.0"

_GUARDRAILS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "auto_pushes_git": False,
    "auto_merges_pr": False,
    "auto_closes_pr": False,
    "implements_daemon": False,
    "auto_installs_cron": False,
}

_HUMAN_REQUIRED_BOUNDARIES = [
    "peer_review_before_real_execution",
    "label_contract_declaration",
    "git_push_and_pr_merge",
    "dataset_activation_declaration",
    "real_benchmark_invocation",
    "cron_systemd_launchd_install",
]

_CRON_EXAMPLE = """\
# Run local ops once per hour (safe planning/validation only)
# Add to crontab with: crontab -e
0 * * * * cd /path/to/ScienceR-Dsim && make local-ops-run-once >> /var/log/local_ops.log 2>&1

# Dry-run every 15 minutes (no commands executed)
*/15 * * * * cd /path/to/ScienceR-Dsim && make local-ops-run-loop-dry-run >> /var/log/local_ops_dry.log 2>&1"""

_SYSTEMD_EXAMPLE = """\
# /etc/systemd/system/local-ops-runner.service
[Unit]
Description=ScienceR-Dsim local continuous operations runner
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/ScienceR-Dsim
ExecStart=/usr/bin/make local-ops-run-once
User=researcher
StandardOutput=journal
StandardError=journal

# /etc/systemd/system/local-ops-runner.timer
[Unit]
Description=Run local-ops-run-once every hour

[Timer]
OnBootSec=5min
OnUnitActiveSec=60min
Unit=local-ops-runner.service

[Install]
WantedBy=timers.target

# Enable with: systemctl enable --now local-ops-runner.timer"""

_LAUNCHD_EXAMPLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sciencer.local-ops-runner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/make</string>
        <string>-C</string>
        <string>/path/to/ScienceR-Dsim</string>
        <string>local-ops-run-once</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/tmp/local_ops.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/local_ops_err.log</string>
</dict>
</plist>
<!-- Load with: launchctl load ~/Library/LaunchAgents/com.sciencer.local-ops-runner.plist -->"""

_OPENCLAW_EXAMPLE = """\
# OpenClaw trigger design (reference only; not implemented here)
#
# When OpenClaw receives a trigger from the operator, it dispatches:
#   make local-ops-run-once
#
# OpenClaw evaluates via command_guard before execution.
# All forbidden command substrings are rejected at dispatch time.
#
# Trigger event: { "type": "schedule", "target": "local-ops-run-once" }
# Response: state + next_action written to outputs/local_ops/
#
# Human operator reviews:
#   outputs/local_ops/local_ops_next_action.json
#   outputs/local_ops/local_ops_status.json"""

_DOCKER_NOTE = """\
# Docker / containerized deployment is a future phase (not yet implemented).
#
# When implemented, the container will:
#   - Run as a non-root user
#   - Mount outputs/ as a volume
#   - Execute make local-ops-run-once on each trigger
#   - Never expose real data credentials
#   - Never auto-push to GitHub"""


def build_install_plan() -> dict:
    return {
        "plan_version": _PLAN_VERSION,
        "safe_to_schedule": True,
        "recommended_command": "make local-ops-run-once",
        "loop_command": "make local-ops-run-loop MAX_ITERATIONS=3",
        "dry_run_command": "make local-ops-run-loop-dry-run",
        "recommended_interval_minutes": 60,
        "daemon_implemented": False,
        "auto_installed": False,
        "cron_example": _CRON_EXAMPLE.strip(),
        "systemd_example": _SYSTEMD_EXAMPLE.strip(),
        "launchd_example": _LAUNCHD_EXAMPLE.strip(),
        "openclaw_trigger_design": _OPENCLAW_EXAMPLE.strip(),
        "docker_future_note": _DOCKER_NOTE.strip(),
        "guardrails": dict(_GUARDRAILS),
        "human_required_boundaries": list(_HUMAN_REQUIRED_BOUNDARIES),
    }


def build_install_plan_report(plan: dict) -> str:
    lines = [
        "# Local Continuous Operations Runner — Install Plan (P25)",
        "",
        "This document shows how to schedule the local continuous operations runner.",
        "Nothing is installed automatically.",
        "",
        "## Recommended one-shot command",
        "",
        f"```bash",
        plan["recommended_command"],
        "```",
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
    for b in plan["human_required_boundaries"]:
        lines.append(f"- `{b}`")
    lines += ["", "---", "", "#local-ops #scheduler #sciencer-dsim"]
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local ops install plan (P25)")
    p.add_argument("--out", default="outputs/local_ops", help="Output directory")
    args = p.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plan = build_install_plan()
    report = build_install_plan_report(plan)

    plan_path = out / "install_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    report_path = out / "install_plan.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"install_plan.json → {plan_path}")
    print(f"install_plan.md   → {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
