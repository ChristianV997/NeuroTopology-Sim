# ds005620 (propofol sedation) — sed/sed2 label fix + 21-subject channel-mean re-run

**Verdict up front:** this report covers two things: (1) a **real, pre-existing
data-wrangling bug fixed** — the registry's `task_to_state` map had a phantom
`"sedated"` key that matched no real task, silently blanking *every* sedation
window; the real task labels are `sed`/`sed2`, now both mapped to `sedated`;
and (2) the honest result of re-running the cheap channel-mean topology on the
recovered 21-subject cohort: **awake-vs-sedated shows NO significant
difference on this metric** (all four metrics subject-blocked p>0.5,
mixed-effects p>0.25, |Cohen's d|<0.14).

**This null does not contradict the original validated ds005620 finding.** The
project's headline propofol result (`REPORT_ds005620_*`, `REPORT_anesthesia_signed_winding.md`)
used the **montage-aware signed phase-grid topology** (Qz sign-flip, spatial
winding) — a far more sensitive instrument than the channel-mean
correlation-threshold heuristic (`compute_real_topology_for_window`) run in
the cheap streaming path here. The honest reading: **the cheap metric is not
sensitive enough to separate propofol states, even where the sensitive metric
is.** That is a useful calibration fact about the cheap metric, not a
retraction of the propofol effect.

## 1. The bug (real, pre-existing, now fixed)

`configs/btc_icft/dataset_onboarding_registry.json` mapped
`{"awake":"awake", "sedated":"sedated"}`. But the dataset's real BIDS task
labels (confirmed from `label_candidates.json`: `Counter({'sed':77,
'awake':56, 'sed2':49})`) contain **no task literally called "sedated"** — so
the `"sedated"` key matched nothing, and every `sed`/`sed2` window was built
with `state_label=None` (silently dropped from any awake-vs-sedated contrast).
The bug predates this session — it was present verbatim in the first ds005620
windower and carried through every consolidation. Fixed to
`{"awake":"awake", "sed":"sedated", "sed2":"sedated"}` (both sedation labels
merged to one `sedated` state — a human decision under `no_label_inference`).

**Recovery confirmed:** the re-run produced **286 sedated + 118 awake windows**
across 21 subjects — where the broken mapping would have produced **0
sedated**.

## 2. Result on the recovered cohort (channel-mean topology)

| metric | subject-blocked p | mixed-effects p | converged | Cohen's d |
|---|---|---|---|---|
| q_net | 0.93 | 0.83 | yes | −0.059 |
| q_abs | 0.68 | 0.37 | yes | −0.121 |
| f_dress | 0.53 | 0.26 | yes | −0.137 |
| defect_density | 0.64 | 0.32 | yes | −0.131 |

No metric separates awake from sedated on the channel-mean heuristic. Effect
sizes are negligible (|d|<0.14). All MixedLM fits converged.

## 3. Why this is reported as a clean null, not hidden

The point of the fix was to *recover* the sedation windows so the contrast
could be run at all. Having run it, the cheap metric shows nothing — and that
is reported plainly. The scientifically correct next step (not done here) is
to run the **sensitive** montage-aware signed-topology metric on this now-
correctly-labeled cohort, which is where the original propofol effect lives.
Data: `outputs/btc_icft/ds005620/cohort_stats.json`.
