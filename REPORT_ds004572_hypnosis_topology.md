# ds004572 (sham/real hypnosis induction) — full 52-subject cohort

**Verdict up front:** scaled from n=1 to the **full 52-subject cohort** (620
windows), the baseline-vs-experience channel-mean topology contrast is now
**significant under the pseudoreplication-resistant subject-blocked
permutation test (p<0.001 on all four metrics) AND the mixed-effects model
(q_abs p≈2×10⁻²²), with a medium-to-large effect size (Cohen's d≈0.75 on
q_abs/f_dress/defect_density, d≈0.51 on q_net).** This is the honest opposite
of the earlier n=1 pass, where the same contrast collapsed to subject-blocked
p=1.0 — the effect is real and survives the correct unit of analysis, not a
pseudoreplication artifact.

**Critical interpretive caveat (stated up front, not buried):** this contrast
is *baseline rest vs. the induced-experience blocks*, pooling all four
experience conditions. It does **not** isolate hypnosis from the several
things that co-vary with "being in an experience block" — eyes state, task
engagement, arousal, time-on-task. The dataset's 2×2 design (real vs. sham
induction × hypnosis vs. relaxation framing) is exactly what could separate
"induction technique" from "verbal framing," but that split needs per-subject
condition-order metadata not encoded in the task names and is **not done
here**. So: a real, well-powered topology difference between rest and induced
experience — not yet attributable specifically to hypnosis.

## 1. What changed from the n=1 pass

| | n=1 pass (earlier) | n=52 cohort (this pass) |
|---|---|---|
| windows | 20 | 620 (208 baseline, 412 experience) |
| subject-blocked p (q_abs) | 1.0 | **<0.0002** (0/5000 permutations) |
| mixed-effects p (q_abs) | not run | **2.2×10⁻²²** |
| Cohen's d (q_abs) | n/a | **0.755** |

## 2. Full cohort result (subject-blocked permutation + mixed-effects, 5000 perms)

| metric | subject-blocked p | mixed-effects p | Cohen's d |
|---|---|---|---|
| q_net | <0.0002 | 9.5×10⁻¹¹ | 0.508 |
| q_abs | <0.0002 | 2.2×10⁻²² | 0.755 |
| f_dress | <0.0002 | 3.2×10⁻²² | 0.756 |
| defect_density | <0.0002 | 1.3×10⁻²² | 0.760 |

Both the aggregate-then-permute test (each of 52 subjects contributes one
point) and the mixed-effects model (all 620 windows, random intercept per
subject) agree — the effect is not carried by a few high-window subjects. All
MixedLM fits converged (no ConvergenceWarning captured).

## 3. Multiple-comparisons note

Four correlated topology metrics × one contrast. q_abs/f_dress/defect_density
are near-collinear (all ≈d=0.75) and move together; q_net is weaker (d=0.51).
Even under a conservative Bonferroni factor of 4, every p stays far below
0.05. The finding is not a multiple-comparisons artifact.

## 4. Method scope

This is the **cheap channel-mean topology** metric
(`compute_real_topology_for_window`, a correlation-threshold heuristic run per
window during streaming), not the montage-aware spatial/phase-grid topology.
The cheap metric is what the 52-subject scaling powered; a diagnostic
full-battery (connectivity/phase/spatial/surrogate-null) spot-check on a
subsample remains available via `tools/run_capability_battery.py` and is not
re-run across the whole cohort here (by design — the subject-blocked test only
needs the per-window q-metrics).

## 5. Onboarding (unchanged)

Config-only generic-registry entry (`baseline1/2→baseline`,
`experience1-4→experience`; `induction1-4` left unmapped as transition
periods). Streamed via `tools/stream_process_openneuro_dataset.py`. Data:
`outputs/btc_icft/ds004572/cohort_stats.json`.
