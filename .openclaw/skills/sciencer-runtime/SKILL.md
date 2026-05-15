# OpenClaw Skill: sciencer-runtime

## Purpose

Dispatches ScienceR-Dsim local pipeline commands via the local autonomous research loop (P23).
All commands run through the policy guard before execution.

## Safe commands this skill may invoke

- `make ds005620-e2e-mock`
- `make validate-ds005620-e2e`
- `make validate-ds005620-contracts`
- `make ds005620-real-artifact-plan`
- `make ds005620-real-execution-gate`
- `make real-data-source-matrix`
- `make multi-dataset-autonomous-iteration-dry-run`
- `make local-agent-loop-dry-run`
- `make local-agent-loop-once`

## What this skill never does

- Never runs real dataset execution automatically.
- Never downloads data (no dandi, no openneuro, no wget, no curl).
- Never confirms peer review.
- Never infers labels.
- Never auto-pushes to git.

## Guardrails

All hardcoded `false`:
- `executes_real_data`
- `downloads_data`
- `auto_confirms_peer_review`
- `auto_runs_mne_extraction`
- `auto_runs_real_benchmark`
- `auto_pushes_git`
- `auto_merges_pr`

## Policy reference

See `configs/local_agents/command_policy.json` for the full allowlist/blocklist.
