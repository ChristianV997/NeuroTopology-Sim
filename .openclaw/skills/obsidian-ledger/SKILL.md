# OpenClaw Skill: obsidian-ledger

## Purpose

Mirrors ScienceR-Dsim pipeline outputs into an Obsidian vault as structured
Markdown notes. Maintains an auto-generated research ledger.

## Safe commands

- `make sync-obsidian`
- `python -m tools.local_agents.research_loop --dry-run --vault <vault_root>`

## Vault structure

```
<vault_root>/
  ScienceR-Dsim/
    INDEX.md                  — master index
    datasets/
      DS005620.md             — per-dataset status
      DS002094.md
      ds001787.md
      ds003969.md
      ds003816.md
      PhysioNet_GABA.md
    loop/
      loop_state.md           — current loop state
    matrix/
      matrix.md               — multi-dataset matrix summary
```

## What this skill never does

- Never modifies source artifacts at `outputs/btc_icft/`.
- Never uploads vault content to any cloud service.
- Never reads private notes from the vault (write-only direction).
- Never syncs real data files into the vault.

## Configuration

See `configs/local_agents/obsidian_sync.json` for vault layout.
Pass `--vault <path>` to the research loop CLI to enable sync.
