# Local Continuous Operations Runner (P25)

## Purpose

P25 adds a finite, lock-protected local continuous operations runner that
repeatedly executes only allowlisted safe planning/validation/sync commands
and stops at real-data, human-review, and GitHub boundaries.

**Safe claim**: P25 adds a finite, lock-protected local continuous operations
runner that repeatedly executes only allowlisted safe planning/validation/sync
commands and stops at real-data, human-review, and GitHub boundaries.

---

## Why this follows P24

P24 (scheduler-ready local agent runtime) provided:
- Command guard CLI
- Status / healthcheck outputs
- Obsidian sync via direct CLI
- Scheduler design examples (cron/systemd/launchd/OpenClaw)

P25 builds on top by adding:
- A runner that can be invoked repeatedly in a finite loop
- Lockfile to prevent overlapping runs
- Retention of previous run outputs
- Aggregated status across runner and local agent subsystems
- Deployment install plan

---

## Execution Modes

### One-shot mode

```bash
make local-ops-run-once
# or
python -m tools.local_ops.runner --mode once
```

Executes one safe cycle: healthcheck → local agent loop → status → Obsidian sync.

### Loop mode

```bash
make local-ops-run-loop MAX_ITERATIONS=3 INTERVAL_SECONDS=1800
# or
python -m tools.local_ops.runner --mode loop --max-iterations 3 --interval-seconds 1800
```

Repeats up to `max_iterations` times with `interval_seconds` between iterations.
Always requires explicit `--max-iterations`. No infinite loop.

### Dry-run mode

```bash
make local-ops-run-loop-dry-run
# or
python -m tools.local_ops.runner --mode dry-run
```

Writes the plan and simulates results without executing any commands.

---

## Lockfile Behavior

- Lock file: `outputs/local_ops/local_ops_lock.json`
- A second runner invocation while a lock is held returns `status: locked` immediately
- A stale lock (older than TTL, default 2h) is replaced with a warning
- Lock is released at normal completion and in failure paths (via `finally`)
- Use `--no-lock` to skip locking (unsafe for concurrent use)

---

## Retention Behavior

- Before each live run, current outputs are archived to `outputs/local_ops/runs/<timestamp>/`
- Only the last 25 run archives are kept by default
- Archives are never deleted from outside `outputs/local_ops/runs/`
- `rm -rf` is never used — `shutil.rmtree` is bounded to `runs/` subdirectory only

---

## Healthcheck Behavior

```bash
make local-ops-healthcheck
# or
python -m tools.local_ops.healthcheck
```

Checks:
- Command policy valid
- Local ops policy has no real-execution commands
- All dangerous example commands are blocked
- `outputs/local_ops/` writable
- `outputs/local_agents/` writable
- Obsidian vault path writable/creatable
- All required Makefile targets present
- No real-execution commands in local-ops Makefile targets
- Ollama available (optional — never blocks)

Output: `outputs/local_ops/local_ops_healthcheck.json`

---

## Status

```bash
make local-ops-status
# or
python -m tools.local_ops.status
```

Aggregates:
- Last runner state
- Local agent status
- Local agent healthcheck
- Research loop next action
- Dataset next actions (multi-dataset + DS005620)

Output: `outputs/local_ops/local_ops_status.json`

---

## Scheduler Install Plan

```bash
make local-ops-install-plan
# or
python -m tools.local_ops.install_plan
```

Writes cron/systemd/launchd/OpenClaw example templates.
**Does not install anything.**

Output:
- `outputs/local_ops/install_plan.json`
- `outputs/local_ops/install_plan.md`

### Cron example

```cron
0 * * * * cd /path/to/ScienceR-Dsim && make local-ops-run-once >> /var/log/local_ops.log 2>&1
```

### systemd example

```ini
[Service]
Type=oneshot
ExecStart=/usr/bin/make local-ops-run-once
WorkingDirectory=/path/to/ScienceR-Dsim
```

### launchd example

```xml
<key>ProgramArguments</key>
<array>
  <string>/usr/bin/make</string>
  <string>-C</string>
  <string>/path/to/ScienceR-Dsim</string>
  <string>local-ops-run-once</string>
</array>
```

### OpenClaw trigger example

```
Trigger event: { "type": "schedule", "target": "local-ops-run-once" }
```

OpenClaw evaluates via `command_guard` before dispatching. All forbidden substrings
are rejected at dispatch time.

---

## Makefile Targets

| Target | Purpose |
|---|---|
| `local-ops-run-once` | Run one safe cycle |
| `local-ops-run-loop-dry-run` | Dry-run (no commands executed) |
| `local-ops-run-loop` | Finite loop (requires MAX_ITERATIONS) |
| `local-ops-healthcheck` | Run P25 healthcheck |
| `local-ops-status` | Aggregate system status |
| `local-ops-install-plan` | Generate scheduler templates |

Variables:
- `VAULT` — Obsidian vault path (default: `obsidian`)
- `MAX_ITERATIONS` — loop iterations (default: 3)
- `INTERVAL_SECONDS` — seconds between iterations (default: 1800)

---

## Outputs

`outputs/local_ops/`:

| File | Contents |
|---|---|
| `local_ops_state.json` | Runner state: status, counts, next_action |
| `local_ops_plan.json` | Run plan: mode, commands, guardrails |
| `local_ops_results.json` | Per-command results |
| `local_ops_next_action.json` | Next recommended action |
| `local_ops_report.md` | Human-readable report |
| `local_ops_events.jsonl` | Append-only event log |
| `local_ops_lock.json` | Lockfile (present during run, removed after) |
| `local_ops_status.json` | Aggregated system status |
| `local_ops_healthcheck.json` | Healthcheck results |
| `install_plan.json` | Scheduler plan (machine-readable) |
| `install_plan.md` | Scheduler plan (human-readable) |
| `runs/<timestamp>/` | Archived previous run outputs |

---

## Guardrails

All hardcoded `false` — cannot be activated by the runner:

- `executes_real_data`: `false`
- `downloads_data`: `false`
- `auto_confirms_peer_review`: `false`
- `auto_pushes_git`: `false`
- `auto_merges_pr`: `false`
- `auto_closes_pr`: `false`
- `auto_runs_real_benchmark`: `false`
- `infers_labels`: `false`
- `fabricates_targets`: `false`
- `implements_daemon`: `false`
- `auto_installs_cron`: `false`

---

## What Remains Manual

These steps are **never automated** and always require a human operator:

- `peer_review_before_real_execution`
- `label_contract_declaration`
- `git_push_and_pr_merge`
- `dataset_activation_declaration`
- `real_benchmark_invocation`
- `cron_systemd_launchd_install`

---

## Real-data Boundary

The runner never:
- Downloads OpenNeuro, DANDI, PhysioNet, S3, or web data
- Runs MNE extraction
- Runs Level M or Level T real feature extraction
- Runs P18.1 real benchmark execution
- Auto-confirms peer review

The `--execute --peer-reviewed-contract-confirmed` flag is permanently in the
forbidden command list and is blocked at the `_is_command_forbidden()` layer
before reaching `command_guard`.

---

## GitHub Boundary

The runner never:
- Auto-pushes to any git remote
- Auto-merges pull requests
- Auto-closes issues or PRs
- Creates or deletes branches

GitHub write operations always require human action.

---

#local-ops #sciencer-dsim
