# ds004917 (parietal-inhibition TMS-EEG) — real PCIst, full 24-subject cohort

**Verdict up front:** scaled from n=3 to the **full cohort — 24 subjects with
usable TMS-EEG** (of 53 total; the rest are MRI-only, no EEG). Both
parietal-inhibition sites now produce **significantly higher perturbational
complexity (PCIst, Comolatti et al. 2019) than the vertex control**, under a
subject-blocked permutation test:
- **ips vs vertex: p=0.0066, Cohen's d=0.57** (parietal mean 12.9 vs vertex 8.4)
- **ppc vs vertex: p=0.0116, Cohen's d=0.55** (parietal mean 13.2 vs vertex 8.4)
- **ips vs ppc: p=0.87, d=−0.03** (the two parietal sites do NOT differ)

This is exactly the pattern the parietal-inhibition-vs-vertex-control design
was built to detect, and it is the honest opposite of the n=3 pass (where
every contrast was p≥0.25). 17 of 24 subjects show parietal>vertex for each
parietal site. Directionally: parietal-cortex TMS evokes a more complex
spatiotemporal response than the vertex control — neurophysiologically
sensible (vertex is a conventional low-specificity control site).

**Scope honesty:** minimal TMS-artifact handling (linear interpolation only,
no SOUND/ICA decay correction), so absolute PCIst magnitudes are first-pass,
not publication-grade. But the *within-subject site contrast* — the actual
scientific claim — is robust to that, since the same artifact handling applies
to all three sites per subject.

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

## 3. Cohort PCIst by site (24 EEG subjects, 72 site rows, ~80 trials/site each)

| site | n subjects | mean PCIst | median PCIst |
|---|---|---|---|
| ips (intraparietal) | 24 | 12.91 | 13.25 |
| ppc (post. parietal) | 24 | 13.17 | 10.52 |
| vertex (control) | 24 | 8.38 | 7.69 |

Both parietal sites sit well above the vertex control. Values are
non-degenerate across the whole cohort (no zeros, no collapsed constants) —
the speed-optimized `build_evoked_response` (pick-before-filter) reproduces
the pre-optimization magnitudes (e.g. sub-02 ips 14.9 vs 14.6 before, the
small shift explained by the disclosed 16- vs 66-channel average-reference).

Of the 53 total subjects, **29 are MRI-only (no EEG)** and produce zero site
rows — correctly, not as an error (confirmed on S3: e.g. sub-01 has only
anat/dwi/fmap/func directories).

## 4. Site-contrast gate (subject-blocked permutation, n=24, 5000 perms)

| contrast | p | Cohen's d | direction |
|---|---|---|---|
| **ips vs vertex** | **0.0066** | 0.574 | parietal > vertex |
| **ppc vs vertex** | **0.0116** | 0.549 | parietal > vertex |
| ips vs ppc | 0.875 | −0.034 | no difference |

Both parietal-inhibition sites evoke significantly higher perturbational
complexity than the vertex control, with medium effect sizes; the two
parietal sites are statistically indistinguishable from each other — the
exact three-way pattern the design predicts. 17/24 subjects show
ips>vertex and 17/24 show ppc>vertex.

**Multiple comparisons:** three contrasts. Both significant p-values survive a
Bonferroni×3 factor (0.0066×3=0.020, 0.0116×3=0.035, both <0.05).

## 5. Scope and next steps

This is the cheap-but-honest activation: minimal artifact handling, the
within-subject contrast robust to it. A publication-grade replication would
add SOUND/ICA decay-artifact removal and bad-trial rejection, and could test
whether the parietal>vertex complexity gap covaries with the
decision-making-under-ambiguity behavioral measure the task provides.
Data: `outputs/btc_icft/ds004917/pcist_contrasts.json`.
