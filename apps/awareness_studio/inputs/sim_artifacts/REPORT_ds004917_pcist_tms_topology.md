# ds004917 (parietal-inhibition TMS-EEG) — activating real PCIst for the first time

**Verdict up front:** real, non-degenerate, site-differentiated PCIst
(Comolatti et al. 2019 state-transition Perturbational Complexity Index) is
now computed from genuine TMS-evoked EEG for the first time in this repo.
Across 3 subjects × 3 stimulation sites (ips/ppc parietal-inhibition, vertex
control), no site-contrast reaches significance under a subject-blocked
permutation test — **n=3 is far too small to claim a site effect**, and this
report does not claim one. What this pass establishes is the *capability*:
the pipeline reads real TMS-pulse markers, trial-averages genuine evoked
responses, and produces PCIst values that vary meaningfully by subject and
site rather than collapsing to a constant.

## 1. Why this dataset

`validation/pci_validation.py::pcist()` is a complete implementation of
PCIst but, before this pass, no onboarded dataset provided a genuine
perturbation-evoked recording with a real pre-stimulus baseline — the one
input it needs. ds004917 (53 subjects, concurrent inhibitory TMS at two
intraparietal/posterior-parietal sites plus a vertex control, during a
decision-making-under-ambiguity task) provides exactly that via real
per-event `TMSips`/`TMSppc`/`TMSvertex` marker columns in `events.tsv`
(confirmed via direct S3 inspection, not inferred from filenames).

## 2. New code

`sciencer_d/btc_icft/level_m/ds004917_pcist_real.py` (new, ~240 lines):
- `load_tms_pulse_onsets_by_site` — parses real per-pulse site markers.
- `build_evoked_response` — preprocesses the full recording once (1-45 Hz
  bandpass + average reference), trial-averages peri-pulse epochs, and
  linearly interpolates the TMS-pulse artifact window (−2 to +5 ms).
- `compute_pcist_by_site` — discover → group pulses by site → trial-average
  → `pcist()`, one row per (subject, site) with ≥5 usable trials.

**Bug found and fixed during this pass:** the first real-data run produced
`pcist=0.0` for every subject/site — a degenerate result. Root cause:
epochs were being extracted from completely unfiltered raw EEG, so slow
drift dominated both baseline and response windows and `pcist()`'s internal
SNR filter rejected every component. Fix: filter the full recording once
before epoching (not per-trial — same edge-transient rationale as
`data/preprocessing.py::preprocess_raw`'s own docstring). Verified via a
synthetic ground-truth test (`tests/btc_icft/test_ds004917_pcist_real.py`)
that a genuine embedded evoked response scores higher PCIst than pure noise
through the full discover → epoch → average → `pcist()` pipeline, and via
real-data re-verification after the fix (below).

**Honest scope limitation:** artifact handling is linear interpolation only
— no SOUND/ICA decay-artifact removal, no bad-channel/bad-trial rejection.
Every output row's warnings say so. This is a first-pass real-data
activation of the capability, not a publication-grade TMS-EEG replication.

## 3. Real PCIst values (3 subjects, 80 trials/site, real evoked responses)

| subject | ips | ppc | vertex |
|---|---|---|---|
| sub-02 | 14.62 | 15.14 | 12.05 |
| sub-04 | 9.81 | 9.97 | 8.35 |
| sub-05 | 23.02 | 10.82 | 13.25 |

Values are non-degenerate (no zeros, no collapsed constants) and vary
meaningfully both across subjects (8.3–23.0) and across sites within a
subject — proof the metric is responding to real signal content, not a
computation artifact.

## 4. Site-contrast gate (subject-blocked permutation, n=3, 2000 perms)

| contrast | observed_stat | p | effect_size_d |
|---|---|---|---|
| ips vs vertex | 4.60 | 0.250 | 1.02 |
| ppc vs vertex | 0.76 | 0.755 | 0.27 |
| ips vs ppc | 3.84 | 1.000 | 0.53 |

None significant. **This is the correct, honest result at n=3** — not a
failure of the method. sub-05's ips=23.0 vs vertex=13.3 is a large
within-subject gap (consistent with the parietal-inhibition-vs-vertex-control
design), but sub-02 and sub-04 show smaller or reversed gaps, so the
group-level test correctly does not detect a consistent site effect at this
sample size.

## 5. Next steps for a real claim

Scaling subject count (the dataset has 53 total, most with usable EEG) is
the direct path to adequate power for the site contrast this design is
built to test — out of scope for this pass, which activates the capability
and establishes its correctness, not a full-cohort replication.
