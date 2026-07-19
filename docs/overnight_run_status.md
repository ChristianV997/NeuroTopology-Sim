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

## P2 — DONE
Built `tools/stream_process_openneuro_dataset.py`: per-subject sync -> real M+T
extraction -> per-subject CSV -> delete raw -> manifest checkpoint (resume-safe).
Scoped to DS005620 only for now (the only dataset with a working real extraction
path); DATASET_PROCESSORS is the plug-in point for others once they have one.
Deviated from the original plan's "Parquet feature store": pyarrow/fastparquet
are not in requirements.txt and this repo's convention is plain CSV everywhere
(features_m.csv, features_t.csv) — used per-subject CSV files instead rather than
adding a new dependency for something CSV already does adequately here.
7/7 tests pass (manifest resume, raw-deletion, failure isolation, --limit).

## P0.6 — DONE
Re-ran the full real pipeline (run_ds005620_m_real --real, run_ds005620_t_real --real)
against the 3 real subjects on disk (data/ds005620/{sub-1010,sub-1016,sub-1017}).
Confirmed all three bugs are fixed on genuine real data:
- artifact_report.json: artifact_dominance=false, mean_artifact_score=0.029 (was: always 1.0)
- leakage_report.json: leakage_detected=false, row_ids_unique=true (was: true/false, collision)
- features_t.csv: 130/130 distinct q_abs values, quality_passed=true, mean_topology_quality=0.999
  (was: hash-of-row_id noise, same for identical-metadata rows regardless of signal)
Minor cosmetic issue noticed (not a correctness bug): write_level_t_topology_outputs
writes the Python list repr "[]" for an empty warnings field instead of an empty
string (Level M's writer joins with "; " instead) -- harmless, just misleading if
grepped for non-empty warnings naively. Not fixed tonight; noted for later cleanup.

## P1 — DONE
Grep-swept level_t/, level_m/, eeg_signal_mt/, pipelines/ for the same two bug
families (hash-fabrication passed off as real; hardcoded mock regardless of
--real flag). Only hit: run_eeg_level_t_signal.py:48 has mock_fixture=True, but
it's correctly gated behind `if mock_fixture:` at the call site (only reached
when the CLI's own --mock-fixture flag is set) -- not a bug, false positive.
No other instances found. The two hashlib hits in level_m/eeg_signal_features.py
and level_t/eeg_signal_topology.py are event_id generation (benign).

## P4 — DONE
Implemented real PCIst (Comolatti et al. 2019 state-transition variant) in
validation/pci_validation.py, independently written (not derived from the
GPLv3 reference implementation -- verified the actual algorithm via the
published paper's method description before implementing, since guessing
wrong would repeat the exact bug class this session has been fixing).
12/12 tests pass, including a comparative sanity check (structured evoked
response scores higher than pure noise). NOT wired into an end-to-end DS002094
run -- no DS002094 real extraction pipeline exists yet in this repo (unlike
DS005620). Building one (TMS-EEG epoch/event-locked window extraction) is
follow-up work, not attempted tonight given remaining time budget.

## P5 — DONE
The P12/P16 label-contract activation packet (sciencer_d/btc_icft/labels/
ds005620_contract_activation.py + pipelines/prepare_ds005620_contract_activation.py)
already implements exactly the "draft, not activated" pattern this task called for
-- contract_activation_allowed is hardcoded False throughout, no code change needed.
Ran it against the real downloaded participants.tsv (21 subjects: columns are age,
sex, awakenings, TMS, tms_count, excluded, bad_after_preprocessing -- note there is
NO subject-level awake/sedated column; that distinction lives in the per-recording
task label (task-awake/task-sed/task-sed2) already used by the M/T pipelines, not
in participants.tsv). Output written to
outputs/btc_icft/ds005620/contract_activation_draft/ (gitignored, local only):
activation_blockers.json confirms all 8 blockers present, contract_activation_allowed
=false, human_review_packet.json has the reviewer checklist. Nothing was activated.
Next step (human, not automated): review report.md there and, if a label mapping is
approved, run the separate contract-activation PR flow this module points to.

## P3 — DONE
Full DS005620 streaming run completed: 21/21 subjects, 0 failures. 1010 total
Level M windows, 1010 total Level T rows, 636K feature store (vs. 83GB raw --
streaming download/process/delete worked as designed, disk never exceeded
~5GB peak). Verified at full scale, not just the 3-subject spot check:
- 1010/1010 row_ids unique across ALL subjects (P0.2 fix holds at scale)
- 1010/1010 distinct q_abs values (P0.5 fix holds at scale -- no hash collisions
  masquerading as distinct-looking values, every window's topology is genuinely
  signal-derived)
- artifact_score: mean=0.034, max=0.266, 0/1010 at the old saturated 1.0
  (P0.1 fix holds at scale)
Output: outputs/btc_icft/ds005620/stream/ (gitignored, local; manifest.json +
per-subject features_m.csv/features_t.csv for all 21 subjects).

## Session summary
All planned work (P0-P5) completed and verified on real data, first at 3-subject
scale then at full 21-subject scale. P6 (other datasets) intentionally not
attempted -- no real extraction pipeline exists for DS002094/ds001787/ds003969/
ds003816/PhysioNet_GABA yet (only DS005620 has one, built/fixed this session);
building one from scratch for TMS-EEG (DS002094, epoch/event-locked windows
around TMS pulses, different shape of problem than DS005620's continuous
windowing) needs its own dedicated pass, not something to rush at the end of
an unattended run. Real PCIst is implemented and tested but not yet wired to
real DS002094 data for that reason.
