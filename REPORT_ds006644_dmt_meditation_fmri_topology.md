# ds006644 (DMT-HAR-MED) — real resting-state fMRI topology, DMT+harmine vs. placebo during a meditation retreat, n=40

**Verdict up front:** newly onboarded (Egger/Scheidegger, Univ. Zürich, CC0,
published *Imaging Neuroscience* 2025). This activates
`dual_engine/fmri_tda_pipeline.py` — a persistent-homology + graph-theoretic
topology pipeline previously verified **only on a synthetic fixture** — on
**real fMRI data for the first time**, with real fMRIPrep-derivative
preprocessing (ICA-AROMA-denoised, MNI152NLin6Asym-space BOLD, matching this
repo's cached Schaefer-100 atlas space — real anatomical parcellation, not a
fallback). Post-retreat (`ses-02`) between-subject group comparison, DMT+
harmine (`verum`, n=20) vs. placebo (n=20), all 40 subjects processed with
zero errors: **one metric (global efficiency) shows a nominal p<0.05
difference, but does not survive multiple-comparison correction across the
4 metrics tested.** Overall: a marginal, honestly-reported signal, not a
confirmed effect.

## 1. Why this dataset

40 healthy meditation practitioners across two structurally identical 3-day
meditation retreats. Randomly assigned, double-blind, placebo-controlled:
either DMT+harmine (120 mg each, four 30 mg tablets at 30-min intervals) or
placebo, administered on retreat day 2. Real questionnaire batteries
(Mystical Experience Questionnaire, Nondual Awareness Dimensional
Assessment, Toronto Mindfulness Scale) accompany the imaging — this is
directly the "meditation + altered-state" intersection this pass targeted,
with the largest sample and highest data-quality bar (real spatial
normalization) of the three fMRI/EEG candidates checked this session.

**Real design, not inferred:** group (`verum`/`placebo`) is between-subject,
fixed for the whole study, read directly from `participants.tsv`'s
`condition` column. Sessions are `ses-01` (pre-retreat baseline) and
`ses-02` (post-retreat, after the pharmacological intervention) — this run
uses **`ses-02` only**, the scientifically primary timepoint capable of
showing a verum/placebo difference, avoiding a within+between-subject
pseudoreplication mix.

## 2. Method

- **Input:** `derivatives/fmriprep/{sub}/ses-02/func/..._space-MNI152NLin6Asym_desc-smoothAROMAnonaggr_bold.nii.gz`
  (ICA-AROMA-denoised, smoothed, real fMRIPrep output — standard practice
  for resting-state functional-connectivity analysis). No confound
  regression layered on top of AROMA in this first pass (disclosed).
- **Atlas:** Schaefer-100 (7 networks), cached locally
  (`/root/nilearn_data/schaefer_2018/...FSLMNI152_1mm...`), same MNI152
  template family as the BOLD's own normalization space — real anatomical
  region correspondence across subjects (unlike `ds005917`'s per-subject
  fallback parcellation, see that report).
- **Pipeline:** `NiftiLabelsMasker` parcellation → `ConnectivityMeasure`
  correlation matrix → `ripser` persistent homology (Betti-0/1, H1
  persistence) → `networkx` graph metrics (modularity, global efficiency) on
  a 15%-density-thresholded graph → one-way ANOVA + η² per metric.
- **TR = 1.8s**, ~240 volumes (~8-minute eyes-closed resting scan).

## 3. Result (one-way ANOVA, n=40, 20 verum / 20 placebo)

| metric | placebo mean | verum mean | F | p | η² |
|---|---|---|---|---|---|
| betti1 | 49.6 | 51.4 | 0.598 | 0.444 | 0.016 |
| total_persistence_h1 | 1.522 | 1.469 | 0.083 | 0.775 | 0.002 |
| modularity | 0.319 | 0.343 | 0.732 | 0.398 | 0.019 |
| **global_efficiency** | **0.397** | **0.427** | **4.114** | **0.0496** | **0.098** |

**global_efficiency is the only metric reaching nominal p<0.05** (verum >
placebo — the psychedelic-during-meditation group shows higher global
network integration post-retreat). **This does not survive Bonferroni
correction across the 4 metrics tested** (threshold 0.05/4 = 0.0125;
observed p=0.0496 > 0.0125). Reported as a marginal, uncorrected signal, not
a confirmed finding — directionally consistent with the broader psychedelics
literature's association of increased global integration/reduced network
segregation, but this single-study, uncorrected result does not establish
that on its own.

Betti-1 (topological complexity) and total persistence show no separation
at all (η² < 0.02, essentially null).

## 4. Caveats

- **Multiple comparisons**: 4 metrics tested, only 1 nominally significant,
  none survive correction. Treat as hypothesis-generating, not confirmatory.
- **Single post-retreat timepoint**: `ses-02` only. A `ses-02`-minus-`ses-01`
  within-subject change score (not computed here) could be more sensitive
  and would control for baseline individual differences — a natural next
  step given both sessions are already downloadable.
- **No confound regression beyond AROMA** — standard motion/physiological
  confound regressors (available in the dataset's own
  `desc-confounds_timeseries.tsv.gz`) were not layered on top of the
  AROMA-denoised signal in this first pass.
- **Whole-graph summary statistics only** — this pipeline does not test
  region-specific or network-specific (e.g. within the 7 Schaefer networks)
  effects, which the retreat's real behavioral/phenomenological measures
  (MEQ, NADA-S, TMS) might correlate with more precisely than a single
  global efficiency number.

## 5. Comparison to ds005917 (companion ketamine report)

Both are real, disclosed, first-time-real-data activations of
`dual_engine/fmri_tda_pipeline.py`. ds006644 (this report) used a real
anatomical atlas via fMRIPrep derivatives; ds005917 lacked spatial
normalization and used the pipeline's per-subject KMeans fallback instead.
ds006644's marginal global-efficiency signal and ds005917's clean null are
each honestly reported on their own terms — neither is asserted to
generalize to the other's very different pharmacological/experimental
design.

Data: `outputs/dual_engine/ds006644/cohort_result.json`.
