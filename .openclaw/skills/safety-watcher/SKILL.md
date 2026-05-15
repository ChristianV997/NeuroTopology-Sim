# OpenClaw Skill: safety-watcher

## Purpose

Monitors all local agent loop events for policy violations, guardrail
breaches, and boundary crossings. Escalates to human operator if any
blocked command is attempted or any guardrail state changes.

## What this skill monitors

- Every event in `outputs/local_agent_loop/loop_events.jsonl`
- Any command containing blocklist substrings
- Any guardrail set to `true` (should never happen)
- Any attempt to run real-data extraction commands
- Any attempt to push to git or merge a PR

## Forbidden command substrings (hard-blocked)

- `--execute --peer-reviewed-contract-confirmed`
- `dandi download`
- `openneuro download`
- `wget`
- `curl`
- `aws s3 cp`
- `s3://`
- `rm -rf`
- `git push`
- `git merge`
- `run_ds005620_real_benchmark`
- `run_eeg_level_m_signal`
- `run_eeg_level_t_signal`
- `extract_mne_signal_blocks`

## Safe commands

- `make local-agent-policy-check`
- `python tools/local_agents/research_loop.py --dry-run`

## Escalation protocol

If any violation is detected:
1. Record violation in `loop_events.jsonl` as `event: "safety_violation"`.
2. Write warning to `loop_next_action.json`.
3. Stop further loop execution.
4. Report `next_action: human_safety_review_required`.

Human operator must inspect the event log and clear the violation before
the loop resumes.
