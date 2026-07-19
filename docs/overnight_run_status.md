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

## P0.2 — DONE (commit e581371)
Fixed row_id collisions: `data/bids_ingest.py::BIDSEEGRecord` now carries `acq_label`
(from mne_bids `bp.acquisition` / fallback filename parser). row_id in
`ds005620_windows_real.py` now includes session+acq and a short hash of the relative
path as a hard uniqueness guarantee. Regression test reproduces the exact
acq-EC/acq-EO collision seen on real data. Full suite: 1623 passed, 9 skipped.

## P0.3 — DONE (commit 18e0168)
Fixed P9->P10 handoff: `features_m.csv` now writes real per-window rows (matching
Level T's `REQUIRED_M_COLUMNS`) instead of a single aggregate summary row.
`metrics_m.json` stays aggregate-only. Verified end-to-end: `run_ds005620_m_real
--real` output is now successfully consumable by
`ds005620_real_topology.load_level_m_window_features` (previously raised
ValueError: Missing required columns). Full suite: 1623 passed, 9 skipped.

## P0.4 + P0.5 — DONE (commit d906ed1)
The most serious bug: DS005620 "real" Level T topology was 100% fabricated (sha256
hash of row_id/metadata text, zero dependence on actual EEG signal) AND the --real CLI
flag was wired to unconditionally call the hash-based fixture path regardless of flags
(`mock_fixture=True` hardcoded). Implemented `compute_real_topology_for_window`: reads
real per-channel signal (new `pick="all"` mode on `read_window_signal`, previously only
mean/first-channel reduction existed) and computes topology via
`eeg_signal_topology.compute_topology_from_channels` (reused from the generic pipeline,
not reimplemented). CLI now requires exactly one of --real/--mock-fixture.
Verified end-to-end: 12 real windows -> 12 distinct q_abs values (previously: hash
noise). Regression test proves output tracks signal, not row_id text.
Full suite: 1625 passed, 9 skipped.
