# OpenClaw Skill: sciencer-pr-manager

## Purpose

Reports PR readiness status for ScienceR-Dsim development branches.
Never auto-merges, auto-closes, or auto-pushes.

## What this skill reads

- Current branch status via `git status` and `git log`.
- Test results from `pytest tests/ -q`.
- Governance validation from `make validate-governance`.

## Safe commands

- `python -m pytest tests/ -q`
- `make validate-governance`
- `make test-root`

## Hard boundaries

- Never runs `git push` automatically.
- Never runs `git merge` automatically.
- Never creates or closes GitHub PRs automatically.
- Never approves or dismisses PR reviews automatically.
- All git write operations require explicit human approval.

## Human-review gate

After all pipeline checks pass, the skill reports:
`next_action: human_pr_review_required`

Human operator must inspect PR, approve review, and manually merge.

## Relationship to P18.3 real execution gate

The real execution gate (`make ds005620-real-execution-gate`) is always a
prerequisite before any PR touching real-data pipelines. The PR manager
checks gate status but never bypasses it.
