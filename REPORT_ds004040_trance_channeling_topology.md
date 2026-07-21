# ds004040 (Trance channeling EEG study) — rest vs. trance, full 13-subject cohort

**Verdict up front:** newly onboarded (CC0, EEG-only, Cannard/Delorme/Wahbeh,
Institute of Noetic Sciences). State comes from the recording's own
rest/trance block-boundary event markers — not a task label, and not
`trial_type` (every row's `trial_type` is the literal string "STATUS", a
BIDS marker-channel artifact; the real state lives in the `value` column as
`rest1_start`/`rest1_end`/`trance1_start`/`trance1_end`, etc.). Across all
**13 subjects, 2 sessions each, 468 windows (234 rest, 234 trance)**, the
rest-vs-trance channel-mean topology contrast is a **clean null** on every
metric: subject-blocked p ranges 0.22–0.72, mixed-effects p ranges 0.74–0.96,
all effect sizes negligible (|d| < 0.011).

## 1. Why this dataset

`ds004040` is a rare open EEG dataset of **trance channeling** — practitioners
voluntarily entering a self-reported dissociative/mediumship trance state,
contrasted against interleaved rest blocks in the same recording session.
It is not jhana, cessation, or classical Buddhist meditation depth (the
datasets originally sought for those specific claims turned out not to be
deposited on OpenNeuro — see the session's scouting record), but it is a
real, adequately-documented, non-ordinary contemplative/altered state of
consciousness with a genuine within-subject rest-vs-state contrast, recorded
by the same lab (Delorme/SCCN-adjacent) that produced the already-onboarded
`ds001787` meditation dataset.

**Honest label handling:** `trial_type` is always "STATUS" in the real data
— using it directly (as the shared `trial_type`-driven windower pattern does
for other datasets) would produce zero usable labels. The real state comes
from parsing the `value` column's `<label>_start`/`<label>_end` pairs; any
unpaired marker (a `_start` without a matching `_end` in the same file, or
vice versa) is dropped, not fabricated into an interval (`no_label_inference`).
None occurred in this dataset — the pairing was clean across all 13
subjects × 2 sessions × 6 blocks each.

## 2. Result (subject-blocked permutation + mixed-effects, 5000 perms)

| metric | subject-blocked p | mixed-effects p | converged | Cohen's d |
|---|---|---|---|---|
| q_net | 0.362 | 0.736 | yes | −0.010 |
| q_abs | 0.718 | 0.962 | yes | 0.002 |
| f_dress | 0.219 | 0.851 | yes | 0.008 |
| defect_density | 0.594 | 0.952 | yes | 0.002 |

No metric separates rest from trance on the cheap channel-mean heuristic.
Effect sizes are essentially zero (|d| < 0.011 — an order of magnitude
smaller than even the null propofol result on the same metric, `d` ≈ 0.06–0.14
in `REPORT_ds005620_scaled_channel_mean_topology.md`). All MixedLM fits
converged, though each carries a boundary-parameter convergence warning
(captured via the Phase 3 `convergence_warning` field, not suppressed) —
consistent with a near-zero random-effect variance, itself consistent with
the null: there's little between-state signal for the model to fit.

## 3. Interpretation — genuine null, not an artifact

Unlike `ds005620` (where the null was traced to a registry bug that silently
dropped all sedated windows, later fixed), this null is not explained by any
known data-wrangling defect: labels are clean, windows are balanced 1:1,
and the pairing logic was verified against the real `events.tsv` structure
(see `tests/test_ds004040_real_level_m.py`). Two honest readings:

1. **The cheap channel-mean metric may again not be sensitive enough** — the
   same instrument that showed a clean null on propofol sedation (a state
   with a well-established, large EEG signature) also shows a null here.
   This is a second data point calibrating the cheap metric's limits, not
   independent evidence against a real trance-related topology change.
2. **Trance channeling, as operationalized in this study, may not produce a
   detectable channel-mean topology shift** at all, independent of metric
   sensitivity — self-reported dissociative trance is phenomenologically
   distinct from jhana/absorption states and may not share their
   (hypothesized) topological signature.

This report does not adjudicate between the two; it reports the honest null
either way, matching this session's established discipline.

## 4. Caveats

- **Cheap channel-mean metric only** — the same heuristic used for every
  other scaled dataset this session, not the montage-aware spatial-topology
  instrument that detects the propofol effect on the same kind of null.
- **n=13** is modest but adequate for a within-subject-rich design (468
  windows, 36 per subject) — the subject-blocked test is the binding
  constraint here, not raw window count.
- **This is not the originally-sought jhana/cessation dataset.** It is the
  closest real, OpenNeuro-hosted, EEG-native altered-state-of-consciousness
  dataset found after an exhaustive S3 scan of the full public catalog
  (`ds001000`–`ds008200`) turned up no OpenNeuro deposit for the specific
  jhana/cessation/meditative-depth papers originally targeted.

Data: `outputs/btc_icft/ds004040/cohort_stats.json`.
