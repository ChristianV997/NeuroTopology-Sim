# Ollama + OpenClaw + Obsidian Setup Guide

## Overview

The local autonomous research team runtime (P23) integrates three optional
external tools:

- **Ollama** — local LLM for status summaries (offline, no API key)
- **OpenClaw** — outer AI dispatcher that invokes research loop commands
- **Obsidian** — knowledge vault for research ledger sync

All three are **optional**. The loop runs fully offline without any of them.

---

## Ollama Setup (Optional)

Ollama provides optional local LLM summaries. The loop always runs without it.

### Install

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com
```

### Pull a model

```bash
ollama pull llama3
# or
ollama pull mistral
```

### Start server

```bash
ollama serve
# Listens on http://localhost:11434 by default
```

### Use with research loop

```bash
python -m tools.local_agents.research_loop --dry-run --use-ollama --ollama-model llama3
```

The loop calls `is_available()` before any Ollama request. If Ollama is not
running, the loop proceeds without it and logs a note.

### Model config

See `configs/local_agents/ollama_models.json` for default models and timeout.

### Guardrails

Ollama is never used to:
- Make empirical claims
- Execute real data
- Infer labels
- Fabricate targets

It is only used for brief status summaries (one sentence).

---

## OpenClaw Setup (Optional)

OpenClaw dispatches AI-driven operator commands to ScienceR-Dsim.

### Skills available

Install the skills by pointing OpenClaw at `.openclaw/skills/`:

| Skill | Purpose |
|---|---|
| `sciencer-runtime` | Safe command dispatcher |
| `sciencer-ontology-guard` | Ontology scope monitor |
| `sciencer-dataset-operator` | Per-dataset readiness |
| `sciencer-pr-manager` | PR status (never auto-merges) |
| `obsidian-ledger` | Vault syncer |
| `safety-watcher` | Policy violation monitor |

### Policy

All commands dispatched by OpenClaw run through `command_guard.py` first.
No command bypasses the policy guard.

### Hard boundary

OpenClaw never:
- Auto-merges PRs
- Auto-pushes branches
- Runs real-data execution
- Downloads datasets
- Confirms peer review

Human approval is always required for git write operations and real execution.

---

## Obsidian Setup (Optional)

Obsidian provides a local knowledge vault for the research ledger.

### Create vault

Open Obsidian and create a new vault at any local path, e.g. `~/research-vault`.

### Sync

```bash
make sync-obsidian VAULT=~/research-vault
# or
python -m tools.local_agents.research_loop --dry-run --vault ~/research-vault
```

### Vault structure after sync

```
~/research-vault/
  ScienceR-Dsim/
    INDEX.md
    datasets/
      DS005620.md
      DS002094.md
      ds001787.md
      ds003969.md
      ds003816.md
      PhysioNet_GABA.md
    loop/
      loop_state.md
    matrix/
      matrix.md
```

### What is synced

- Per-dataset gate status and next action
- Loop state (steps completed, next action)
- Multi-dataset matrix summary

### What is never synced

- Raw EEG files
- Real data
- Private keys or credentials

### Configuration

See `configs/local_agents/obsidian_sync.json` for vault layout options.

---

## All three together

```bash
# 1. Start Ollama (optional)
ollama serve &

# 2. Run the research loop with all integrations
python -m tools.local_agents.research_loop \
    --dry-run \
    --vault ~/research-vault \
    --use-ollama \
    --ollama-model llama3 \
    --out outputs/local_agent_loop \
    --json

# 3. Open Obsidian to review the ledger
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Ollama not available | Loop continues without it; check `ollama serve` |
| Vault path doesn't exist | Create the directory or vault first |
| Command blocked by policy | Check `configs/local_agents/command_policy.json` |
| Loop exits nonzero | Check `outputs/local_agent_loop/loop_next_action.json` |
