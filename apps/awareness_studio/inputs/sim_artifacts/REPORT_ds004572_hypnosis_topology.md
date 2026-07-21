# ds004572 (sham/real hypnosis induction) — full real-signal capability battery

**Verdict up front:** the full battery (Level-M/T, PLV/PLI/wPLI connectivity,
band-specific Hilbert phase topology, montage-aware spatial topology, a
phase-randomization surrogate gate, and permutation-based group testing) runs
end-to-end on real signal with non-degenerate outputs at every stage. A
baseline-vs-experience topology difference is **significant in a
window-pooled test (p<0.05 on all four metrics) but not in the
subject-blocked test (p=1.0)** at n=1 subject — this is the expected,
honest signature of insufficient subject count, not a real group effect
claim. No effect is claimed here; this pass proves the instrumentation.

## 1. Why this dataset

52-subject sham-hypnosis EEG (Sci Rep 2024): pre-baseline → 4 induced-
experience blocks (crossing real/sham induction × hypnosis/relaxation
framing) → post-baseline, 64ch EasyCap. A genuinely new altered-state
category (induced-suggestion) complementing this repo's existing
meditation/anesthesia coverage, and — via the 2×2 design — a built-in
null-controlled question for future work isolating induction technique from
verbal framing.

## 2. Onboarding (config-only, generic registry path)

`configs/btc_icft/dataset_onboarding_registry.json` entry: `baseline1/2 →
baseline`, `experience1-4 → experience`; `induction1-4` (the induction
period itself, a transition not a stable state) intentionally left
unmapped. No new Python — the existing generic streaming pipeline and
`tools/run_capability_battery.py` handle it entirely from the registry
entry.

## 3. Battery results (sub-01, 20 real windows, 16 channels)

| instrument | result |
|---|---|
| topology quality | mean 0.956 (min 0.832), 10703/11200 valid triangles — passed |
| connectivity | mean PLV 0.337, PLI 0.119, wPLI 0.179 |
| phase-based topology (alpha) | mean Qabs 0.331, phase_grad 1.043 |
| spatial topology (montage-aware) | mean Qabs 1.925 (all 20 windows resolved on the 64ch EasyCap montage) |
| surrogate null gate (50 surrogates/window) | 20/20 windows passed \|z\|≥2 |

All real, signal-derived, non-degenerate — no zeros, no constant-value rows,
every instrument this repo has built and previously validated on
ds005620/ds003969 runs cleanly on this new dataset's real montage and
sampling rate.

## 4. Group significance: baseline vs experience (q_net/q_abs/f_dress/defect_density)

| metric | window-pooled p | subject-blocked p |
|---|---|---|
| q_net | 0.0075 | 1.0 |
| q_abs | 0.023 | 1.0 |
| f_dress | 0.0385 | 1.0 |
| defect_density | 0.031 | 1.0 |

The window-pooled test treats each of sub-01's 20 windows as independent,
which is not a valid claim of a group effect (pseudo-replication — many
windows from one subject). The subject-blocked test, which correctly
accounts for n=1 subject, returns p=1.0 across every metric — the honest
answer at this sample size. **No baseline-vs-experience effect is claimed.**
Scaling subject count is the direct path to a real test of this contrast.

## 5. Scope note

This pass ran the battery on one real subject to prove every instrument
produces genuine, non-degenerate output on this dataset's real montage and
sampling rate — not a multi-subject group-level replication. Microstate
clustering and ML-decoding cross-checks (both available in
`sciencer_d/btc_icft/level_t/`) were not run in this pass.
