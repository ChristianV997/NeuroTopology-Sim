# Overnight unattended run status

Plan: /root/.claude/plans/today-is-my-last-wobbly-lampson.md
Branch: claude/consciousness-transitions-tests-ggx7ph

This file is appended to after every checkpoint (commit). Read top-to-bottom for latest state.

## P0.1 — DONE (commit 1bbf487)
Fixed `artifact_score` in `sciencer_d/btc_icft/level_m/features.py`: was dividing by
`|signal_mean|`, which is ~0 for z-normalized signal (the real-EEG path always feeds
z-normalized data) — caused every real window to saturate to artifact_score=1.0.
Now divides by signal std (scale-invariant, doesn't degenerate). Added 2 regression
tests (smooth zero-mean signal must score low, alternating +1/-1 must score high).
Full suite: 1622 passed, 9 skipped (pre-existing skips, unrelated).
