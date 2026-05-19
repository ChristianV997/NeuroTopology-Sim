# Local Agent Scheduler Plan (P24)

This document describes how to safely schedule the local autonomous research
loop. No background daemon is implemented in this release.

## Why no daemon

The loop is designed to be safe to run via cron, systemd, or OpenClaw triggers.
A daemon would add complexity without adding safety. The current design:

- Runs one iteration per invocation
- Writes outputs to `outputs/local_agents/`
- Stops at all real-data and human-review boundaries

## Generating the plan

```bash
make local-agent-scheduler-plan
# OR
python -m tools.local_agents.scheduler_plan --out outputs/local_agents
```

Produces:
- `outputs/local_agents/scheduler_plan.json` — machine-readable plan
- `outputs/local_agents/scheduler_report.md` — human-readable Markdown

## Recommended schedule

- Command: `make local-agent-loop-once`
- Dry-run: `make local-agent-loop-dry-run`
- Interval: every 60 minutes
- Safe to schedule: `true`

## Cron example

```cron
# Run local agent loop once per hour (safe planning/validation only)
0 * * * * cd /path/to/ScienceR-Dsim && make local-agent-loop-once >> /var/log/local_agent.log 2>&1

# Dry-run every 15 minutes (no commands executed)
*/15 * * * * cd /path/to/ScienceR-Dsim && make local-agent-loop-dry-run >> /var/log/local_agent_dry.log 2>&1
```

## systemd timer example

```ini
# /etc/systemd/system/local-agent-loop.service
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
```

## macOS launchd example

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
</dict>
</plist>
<!-- Load with: launchctl load ~/Library/LaunchAgents/com.sciencer.local-agent-loop.plist -->
```

## OpenClaw trigger design

When OpenClaw receives a trigger from the operator, it dispatches:
`make local-agent-loop-once`

OpenClaw evaluates the command via `command_guard` before execution.
All forbidden command substrings are rejected at dispatch time.

Human operator then reviews:
- `outputs/local_agents/research_loop_next_action.json`
- `outputs/local_agents/local_agent_status.json`

## Guardrails

All hardcoded `false` — no override possible at schedule time:

- `executes_real_data`: `false`
- `downloads_data`: `false`
- `auto_confirms_peer_review`: `false`
- `auto_pushes_git`: `false`
- `auto_merges_pr`: `false`
- `auto_closes_pr`: `false`
- `implements_daemon`: `false`

## Human-required boundaries

These steps are **never automated** and always require human action:

- `peer_review_before_real_execution`
- `label_contract_declaration`
- `git_push_and_pr_merge`
- `dataset_activation_declaration`
- `real_benchmark_invocation`

---

#local-agent #scheduler #sciencer-dsim
