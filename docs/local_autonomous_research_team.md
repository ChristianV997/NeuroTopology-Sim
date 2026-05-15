# Local Autonomous Research Team Runtime (P23)

## Purpose

P23 adds the first safe local autonomous research operations layer to
ScienceR-Dsim. It runs only allowlisted safe commands, mirrors outputs into
Obsidian, optionally uses Ollama if available, and preserves all real-data
and human-review boundaries.

**Safe claim**: This PR adds a local autonomous research operations layer that
runs only allowlisted safe commands, mirrors outputs into Obsidian, optionally
uses Ollama if available, and preserves all real-data and human-review
boundaries.

## Architecture

```
OpenClaw (outer dispatcher)
    ↓
tools/local_agents/research_loop.py  (P23 loop)
    ↓
tools/local_agents/command_guard.py  (policy evaluation)
    ↓
tools/local_agents/safe_runner.py    (subprocess, guarded)
    ↓
ScienceR-Dsim pipelines              (mock/planning/validation only)
    ↓
tools/local_agents/obsidian_sync.py  (mirror to vault)
tools/local_agents/ollama_client.py  (optional local LLM)
```

## Commands

```bash
# Dry-run (plan only, no commands executed):
make local-agent-loop-dry-run

# Run one iteration:
make local-agent-loop-once

# Check policy (list allowlist/blocklist):
make local-agent-policy-check

# Sync outputs to Obsidian vault:
make sync-obsidian VAULT=<vault_root>
```

## CLI

```bash
python -m tools.local_agents.research_loop --dry-run
python -m tools.local_agents.research_loop --once --out outputs/local_agent_loop
python -m tools.local_agents.research_loop --max-commands 5 --vault ~/vault
python -m tools.local_agents.research_loop --use-ollama --ollama-model llama3
```

Options:
- `--dry-run` — plan only; no commands executed
- `--once` — run only the first command
- `--max-commands N` — stop after N commands
- `--out <dir>` — output directory (default: `outputs/local_agent_loop`)
- `--vault <path>` — Obsidian vault root (optional)
- `--policy <path>` — custom command_policy.json
- `--timeout-s N` — per-command timeout
- `--continue-on-error` — record failures but continue
- `--use-ollama` — query Ollama for status summaries (optional)
- `--ollama-model <name>` — Ollama model (default: llama3)
- `--json` — print JSON summary to stdout
- `--strict` — exit nonzero on any failure

## What the loop runs (safe commands only)

| Command | Safe? | Executes real data? |
|---|---|---|
| `make ds005620-e2e-mock` | yes | No |
| `make validate-ds005620-e2e` | yes | No |
| `make validate-ds005620-contracts` | yes | No |
| `make ds005620-generated-language-check` | yes | No |
| `make ds005620-real-artifact-plan` | yes | No |
| `make ds005620-real-execution-gate` | yes | No |
| `make real-data-source-matrix` | yes | No |
| `make validate-real-data-source-matrix` | yes | No |
| `make multi-dataset-autonomous-iteration-dry-run` | yes | No |

## Guardrails

All hardcoded `false`:

- `executes_real_data`
- `downloads_data`
- `auto_confirms_peer_review`
- `auto_runs_mne_extraction`
- `auto_runs_level_m_extraction`
- `auto_runs_level_t_extraction`
- `auto_runs_real_benchmark`
- `auto_declares_label_mapping`
- `infers_labels`
- `fabricates_targets`
- `weakens_p18_3_gate`
- `weakens_p20_operator`
- `weakens_p21_iteration`
- `weakens_ontology_quarantine`
- `weakens_language_firewall`
- `auto_pushes_git`
- `auto_merges_pr`
- `auto_closes_pr`

Forbidden command substrings (always blocked):
`--execute --peer-reviewed-contract-confirmed`, `dandi download`,
`openneuro download`, `wget`, `curl`, `aws s3 cp`, `s3://`, `rm -rf`,
`git push`, `git merge`, `run_ds005620_real_benchmark`,
`run_eeg_level_m_signal`, `run_eeg_level_t_signal`, `extract_mne_signal_blocks`

## Agent roles

See `configs/local_agents/agent_roster.json` for the 8 agent roles:

| Role | Auto-run? | Needs human review? |
|---|---|---|
| mock_runner | yes | No |
| validator | yes | No |
| artifact_planner | yes | No |
| gate_inspector | yes | Yes |
| obsidian_syncer | yes | No |
| matrix_builder | yes | No |
| real_data_executor | **no** | **Yes** |
| safety_watcher | yes | No |

`real_data_executor` is **never auto-run**.

## OpenClaw skills

Six skills in `.openclaw/skills/`:

- `sciencer-runtime` — safe command dispatcher
- `sciencer-ontology-guard` — ontology scope monitor
- `sciencer-dataset-operator` — per-dataset readiness inspector
- `sciencer-pr-manager` — PR status reporter (never auto-merges)
- `obsidian-ledger` — vault syncer
- `safety-watcher` — policy violation monitor

## Outputs

`outputs/local_agent_loop/`:

| File | Contents |
|---|---|
| `loop_state.json` | Overall loop state: counts, status |
| `loop_next_action.json` | next_action, next_command, warnings |
| `loop_guardrails.json` | All guardrails (all false) |
| `loop_step_results.json` | Per-step results |
| `loop_report.md` | Human-readable report |
| `loop_events.jsonl` | Append-only event log |

## What this layer never does

- Never executes real DS005620 or any other dataset benchmark automatically.
- Never downloads data (no dandi, no openneuro, no wget, no curl).
- Never runs MNE extraction automatically.
- Never runs real Level M or Level T feature extraction automatically.
- Never confirms peer review on behalf of a human operator.
- Never declares a binary label mapping.
- Never infers labels.
- Never fabricates targets.
- Never weakens the P18.3 execution gate.
- Never weakens the P20 build operator.
- Never weakens the P21 autonomous iteration loop.
- Never weakens ontology quarantine or language firewall.
- Never emits empirical claims.
- Never auto-pushes to git, auto-merges PRs, or auto-closes issues.
- Never requires Ollama installed (optional only).
- Never adds cloud API dependencies.
- Never requires API keys.
- Never runs a background daemon.
