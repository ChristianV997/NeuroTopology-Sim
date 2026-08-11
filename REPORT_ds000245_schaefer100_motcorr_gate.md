# Re-gating ds000245's global_efficiency headline with anatomical parcellation + motion regression

**Run:** `outputs/ds000245_fmri_tda_schaefer100_motcorr/global_efficiency_gate_schaefer100_motcorr.json`
**Tools:** `tools/fetch_ds000245.py` (`--include-anat`) → `tools/run_ds000245_schaefer100_motcorr.py` →
`tools/gate_ds000245_global_efficiency.py`
**Status:** n = 45 subjects (15 CTL / 15 ODN / 15 ODP), 0 errors, 0 excluded for motion.
**Verdict: the CTL < ODN < ODP effect survives proper preprocessing but is meaningfully attenuated.**

---

## Why this run exists

[REPORT_ds000245_global_efficiency_gate.md](REPORT_ds000245_global_efficiency_gate.md) reproduced and gated
ds000245's `global_efficiency` headline (η² = 0.406, matching the claimed 0.41) but flagged two caveats that
block a real neurobiological interpretation:

> The K=100 parcellation is a non-anatomical coordinate clustering, not a validated brain atlas... No
> motion/confound regression was applied... head-motion-correlated connectivity differences between groups...
> have not been ruled out.

This run closes both gaps: **Schaefer-100** (7-network, MNI152) anatomical parcellation, and **real per-volume
motion regression + framewise-displacement scrubbing**, computed from scratch since ds000245 is raw BIDS with
no fMRIPrep derivatives (verified directly against the OpenNeuro S3 listing — no `derivatives/` folder exists).

**Prior results are untouched** — this run's outputs live entirely under
`outputs/ds000245_fmri_tda_schaefer100_motcorr/`, with a `_schaefer100_motcorr` suffix on the gate JSON, next
to (not overwriting) `contracts/fmri_tda/ds000245/` and the original `REPORT_ds000245_global_efficiency_gate.md`.

---

## What changed in the pipeline

### Parcellation: Schaefer-100, warped into each subject's native space

The prior run's own caveat was that Schaefer/anatomical atlases weren't used. Doing this correctly on raw
(non-normalized) BOLD requires more than pointing `NiftiLabelsMasker` at an MNI atlas: the functional data
was never registered to MNI space, so an MNI-defined atlas can't be applied to it directly without registration
first (`tools/spatial_normalization.py`):

1. **T1w → MNI152** (affine, 12 DOF, `dipy` mutual-information registration).
2. **Functional reference volume → T1w**, same subject (rigid, 6 DOF).
3. Schaefer-100 labels resampled (nearest-neighbor) through both transforms into the subject's native
   functional grid, then fed to `NiftiLabelsMasker` as an in-memory labels image matching the BOLD data's own
   space.

**Caveat carried forward:** this is affine-only normalization, not full nonlinear warping (no ANTs SyN / FSL
FNIRT available in this environment). It corrects gross size/position/orientation differences but not
individual cortical-folding variability. It is real, registration-based anatomical alignment — not zero
normalization — but coarser than a full nonlinear pipeline.

### Motion: real per-volume centroid-drift regression + FD scrubbing

`tools/motion_correction.py` computes, per volume, the intensity-weighted center of mass in world (mm)
coordinates; the frame-to-frame Euclidean drift of that centroid is used as (a) three nuisance regressors
(cumulative x/y/z drift relative to a reference volume, passed to `NiftiLabelsMasker`'s `confounds`) and (b)
a framewise-displacement scrubbing criterion (threshold 0.5mm; a subject would have been excluded outright if
more than 25% of its frames were scrubbed).

**Caveat carried forward:** this is a translation-only proxy, not full 6-DOF rigid-body realignment — it
does not capture rotation. (A full 6-DOF `dipy`-registration variant was built and benchmarked at ~30-45s/subject
including atlas normalization — fast enough to run — and is kept, unused by default, in
`motion_correction.estimate_motion_dipy_rigid` for a future higher-fidelity re-run if rotation-sensitivity
turns out to matter.)

---

## Motion QC

| Quantity | Value |
|---|---|
| Subjects processed | 45 / 45 |
| **Excluded for motion (>25% frames scrubbed)** | **0** |
| Mean scrub fraction | 0.3% |
| Max scrub fraction (any single subject) | 6.1% (`sub-CTL15`) |
| Subjects with any scrubbed frames | 6 / 45 |

ds000245's resting-state runs are low-motion by this measure — no subject came close to the exclusion
threshold, so the group comparison below uses the full n = 45 (no motion-driven attrition to worry about
when interpreting group differences).

---

## Reproduction check: before vs. after

| | **Prior (K=100, no motion reg.)** | **New (Schaefer-100 + motion reg.)** |
|---|---|---|
| CTL mean | 0.390 | 0.357 |
| ODN mean | 0.433 | 0.410 |
| ODP mean | 0.454 | 0.424 |
| F | 14.34 | 7.64 |
| p (parametric) | 1.8 × 10⁻⁵ | 0.0015 |
| **η²** | **0.406** | **0.267** |
| Ordering | CTL < ODN < ODP | CTL < ODN < ODP (unchanged) |

The group ordering is unchanged, but the effect size drops by roughly a third (0.406 → 0.267) once the
parcellation is anatomical and motion is regressed out plus scrubbed. Some of the original K=100/no-motion
effect was very likely inflated by the confounds this run controls for — consistent with the caveat the prior
report flagged but could not itself quantify.

---

## Q1 — Is the real global_efficiency value more extreme than a phase-randomized null?

Unchanged in method from the prior gate: `validation.surrogate_testing.surrogate_test_topology_metric`,
200 Fourier phase-randomized surrogates per subject, two-sided, run through the *same* Schaefer-100 +
motion-regressed pipeline end to end (`connectivity_matrix` → `graph_metrics`'s `global_efficiency`).

| Quantity | Value |
|---|---|
| Subjects gated | 45 / 45 |
| **Pass at p < 0.05** | **45 / 45 (100%)** — unchanged from the prior run |
| z-score range | −234.7 to −34.8 (mean −120.2) |
| Direction | Real value below the surrogate mean in 45 / 45 subjects |

Metric validity is exactly as decisive as before: every subject's real `global_efficiency`, computed on the
anatomically parcellated, motion-regressed timeseries, falls entirely outside its own phase-randomized null.

---

## Q2 — Does the CTL/ODN/ODP contrast survive a label-shuffle null?

`analysis/permutation.py`'s `permutation_anova`, 10,000 group-label shuffles, same as the prior gate.

| Quantity | Value |
|---|---|
| Observed η² | 0.2668 |
| Observed F | 7.643 |
| **Permutation p-value** | **0.0010** (10 / 10,001) |

Still decisive — not one in a thousand random relabelings produced an η² this large — but the p-value moved
an order of magnitude (0.0001 → 0.0010) alongside the smaller effect size. The contrast is real; it is a
smaller real effect than the original K=100/no-motion-regression number suggested.

---

## Verdict

**The headline survives proper preprocessing, attenuated:**

1. **Reproduction**: same CTL < ODN < ODP ordering, η² = 0.267 (down from 0.406) once parcellation is
   anatomical (Schaefer-100, subject-space-registered) and motion is regressed out + scrubbed.
2. **Q1 (metric validity)**: unchanged, 45/45 subjects — global_efficiency is real, structured signal in
   every subject under this pipeline, not a null artifact.
3. **Q2 (contrast reality)**: p = 0.0010 (10,000 permutations) — the group contrast is not explainable by a
   between-subjects label-shuffle null, though the effect size and permutation p both moved toward "less
   extreme" relative to the original claim.
4. **Motion**: 0/45 subjects excluded; this dataset has low head motion by the centroid-drift proxy used
   here, so motion-driven subject attrition is not a confound in this specific comparison — but the
   confound *regression itself* still measurably shrank the effect size, meaning motion-correlated signal
   was present and contributing to the original (uncorrected) 0.406.

**Caveats that limit what this does and still does not establish:**

- Spatial normalization is affine-only (no nonlinear warp) — coarser than a full ANTs/FSL-grade pipeline.
- Motion regression is a translation-only centroid-drift proxy, not full 6-DOF rigid-body realignment (a
  higher-fidelity `dipy`-based 6-DOF variant exists in the codebase, unused by default — see
  `tools/motion_correction.py`).
- Density-thresholded graph construction (top 15% of edges) is one of several standard choices; this result
  is for that choice, not shown to be threshold-invariant.
- Single dataset; no independent replication cohort run.
- group_means/eta_squared still do not by themselves establish a clinical or anatomical Parkinson's
  mechanism — they establish that the statistical effect, under substantially more rigorous preprocessing
  than the original claim used, is real but smaller than first reported.

---

## Reproduce

```bash
pip install nibabel nilearn scikit-learn networkx ripser scipy dipy

python tools/fetch_ds000245.py --dest data/ds000245 --include-anat

python tools/run_ds000245_schaefer100_motcorr.py \
    --bids-root data/ds000245 \
    --out outputs/ds000245_fmri_tda_schaefer100_motcorr

python tools/gate_ds000245_global_efficiency.py \
    --ts-dir outputs/ds000245_fmri_tda_schaefer100_motcorr/roi_timeseries \
    --out outputs/ds000245_fmri_tda_schaefer100_motcorr/global_efficiency_gate_schaefer100_motcorr.json \
    --n-surrogates 200 --n-permutations 10000 --n-jobs 4
```

Offline tests for the pure logic (no network, no real data):
`pytest tests/test_fetch_ds000245.py tests/test_motion_correction.py tests/test_gate_ds000245_global_efficiency.py`
