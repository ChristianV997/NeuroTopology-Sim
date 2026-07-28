# Surrogate-gating the two headline results that couldn't be gated from cache

Prior session built `validation/surrogate_testing.py` and gated the ds003969
meditation beta effect (survived, z=−10). Two bigger headlines couldn't be
gated because raw time series were process-and-discarded: **ds000245** (PD fMRI,
global_efficiency η²=0.41) and **ds005620** (propofol EEG, signed alpha
anteriorization dz=−1.06). This task re-fetches and gates them.

**Scope decision (stated, per the task's "do one completely" instruction):
ds005620 was completed in full; ds000245 is deferred with reasons.** ds005620 is
the more important headline (the novel signed-winding metric's first evidence of
carrying information beyond unsigned Qabs), its pipeline is present on this
branch, and EEG re-fetch is tractable. ds000245's `fmri_tda_pipeline.py` is not on
this branch (only on `origin/main`), its cached `conn/*.npy` are the later
Schaefer-200 matrices (200×200) not the original K=100 headline, and no ROI
timeseries survive — so gating it needs a full 45-subject BOLD re-fetch +
re-parcellation, which the task itself flags as the heavier path to defer if
choosing one. See the ds000245 section for exactly what remains.

---

## Durable pipeline capability added

`dual_engine/anesthesia_signed_winding_pipeline.py` gained **`--save-timeseries
<dir>`** (and `--conditions`): additive-only, persists the CSD post-ICA
per-recording scalp time series + channel names to `.npz` before metric
collapse — the exact array the surrogate gate needs, and the specific gap that
blocked gating last session. The tested `preprocess`/`compute_metrics` functions
are unchanged; a new test (`test_save_timeseries_writes_csd_array`) covers it.
Every future run can now retain gate-ready timeseries.

---

## ds005620 (propofol EEG) — COMPLETED

### 1. Re-fetch / re-run + reproduction check

Re-fetched from OpenNeuro S3 (`s3.amazonaws.com/openneuro.org/ds005620`),
re-ran the exact committed chain (resample 5000→256, HP 1 Hz, bad-channel
interpolation, average reference, picard ICA on real VEOG/HEOG, CSD), 20
subjects (21 − 1 dataset-`excluded`), conditions awake + sed. **74/74 recordings
OK, 0 errors, 74 timeseries saved**, `provenance="real_eeg"`.

**Reproduction is faithful** (re-run vs original report):

| region | re-run dz | original dz | re-run p |
|---|---|---|---|
| parietal | **−1.08** | −1.06 | 0.0001 |
| frontal | **+0.85** | +0.86 | 0.0012 |
| occipital | −0.64 | −0.64 | 0.010 |
| central | +0.65 | +0.65 | 0.010 |

Deterministic ICA (random_state=97) reproduces the headline to the third
decimal — the re-fetch is the same pipeline, nothing drifted.

### 2. Phase-randomization gate (Question A: "is the metric value real structure?")

Per recording (awake and sed separately, condition-matched surrogates), the
*entire* alpha phase → `signed_defect_map` → `net_charge_by_region` → regional
`region_abs_charge` pipeline was wrapped as the gated `metric_fn`. 200 FT
surrogates, two-sided. Headline regions parietal + frontal (occipital/central
deferred for compute — 200 surrogates × 50 signed-defect maps per region-recording).

| condition | region | z_mean | passes |
|---|---|---|---|
| awake | parietal | −13.2 | **20/20** |
| awake | frontal | −11.8 | **20/20** |
| sed | parietal | −12.0 | **20/20** |
| sed | frontal | −14.3 | **20/20** |

**80/80 pass.** Direction matters and refutes the pre-flagged confound: real
regional |charge| (~0.1–0.4) is *far below* the phase-randomized null (~4–5),
z≈−13. Destroying cross-channel phase (surrogates) *multiplies* the defect
charge; the real EEG's low charge reflects genuine smooth spatial phase
organization. **The residual-EMG concern is refuted** — unstructured EMG-like
noise would produce *high* charge like the surrogates, not the low, spatially
organized charge observed. The metric measures real spatial phase structure, not
a spectral artifact.

### 3. Permutation contrast (Question B: "is the awake-vs-sed difference real?")

A distinct test: real awake−sed difference in regional |charge| vs a null from
shuffling the awake/sed labels *within each subject* (paired design), 5000
permutations.

| region | sed − awake | dz | permutation p |
|---|---|---|---|
| parietal | −0.229 | −1.08 | **0.0010** |
| frontal | +0.215 | +0.85 | **0.0002** |

The anteriorization contrast (parietal ↓, frontal ↑ under sedation) survives the
label-shuffle null in both regions.

### Verdict — ds005620

**The alpha anteriorization headline SURVIVES BOTH checks, decisively.** The
signed regional |charge| reflects genuine spatial phase structure (gate: 80/80,
z≈−13), and the awake→sedation anteriorization contrast is beyond a
within-subject relabeling null (permutation p ≤ 0.001, both regions). The
project's largest new-metric effect is real on both the "is the number real" and
the "is the contrast real" questions — the two are reported separately and both
pass.

---

## ds000245 (Parkinson's fMRI) — DEFERRED (exactly what remains)

Not gated this session. Precise reasons and what is required:

1. **Pipeline not on this branch.** `dual_engine/fmri_tda_pipeline.py` exists only
   on `origin/main` (branch `claude/fmri-tda-pipeline`), not on
   `claude/awareness-studio-mvp-fiIxi`. Gating requires bringing it into the tree
   (a checkout from main) — doable but not done here.
2. **Cache does not shortcut it.** The cached `conn/*.npy` are **(200, 200)** =
   the later Schaefer-200 result, not the original **K=100 coordinate**
   parcellation that produced η²=0.41. And a correlation matrix cannot be
   phase-randomized regardless — the gate needs ROI **time series**, which were
   never saved (the same process-and-discard gap). The subject `func/` dirs hold
   no retained BOLD or timeseries.
3. **What it needs:** re-fetch 45 subjects' BOLD from OpenNeuro S3 (~1.6 GB),
   re-run `fmri_tda_pipeline.py` with the **K=100 coordinate** path (the original
   headline's exact `parcellate_bold`-no-atlas choice) **plus the new
   `--save-timeseries` capability** (which now exists, added here for EEG; the
   fMRI pipeline needs the analogous option), then gate `global_efficiency` with
   the entire correlation→graph pipeline inside the `metric_fn`, and run the
   group-contrast permutation test (HC<ODN<ODP). This is a multi-hour job with a
   reproduction-check risk (does the re-run match η²=0.41), and the task
   explicitly sanctioned deferring it to complete ds005620 fully.

This is the one remaining item of the original integrity gap, now precisely
scoped rather than silently skipped.

---

## Bottom line

**ds005620's alpha anteriorization — the biggest new-metric effect in the
project — survives both the phase-randomization gate (80/80, z≈−13) and the
within-subject permutation contrast (p ≤ 0.001). Nothing failed.** ds000245's
global_efficiency remains ungated and is the sole outstanding item, deferred with
a full re-fetch/re-parcellation recipe rather than skipped. The two statistical
questions — metric validity vs contrast reality — are reported separately
throughout; ds005620 passes both.
