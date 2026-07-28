# Gating ds000245's global_efficiency headline on a real 45-subject re-fetch

**Run:** `outputs/ds000245_fmri_tda/global_efficiency_gate.json`
**Tools:** `tools/fetch_ds000245.py` → `dual_engine/fmri_tda_pipeline.py --save-timeseries` →
`tools/gate_ds000245_global_efficiency.py`
**Status:** n = 45 subjects (15 CTL / 15 ODN / 15 ODP), 0 errors. Reproduces the claimed
η² = 0.41 headline (0.406 observed) and **both gate questions pass decisively**.

---

## Why this run exists

`REPORT_gate_ds000245_ds005620.md` gated ds005620's alpha-anteriorization finding (80/80
surrogate pass, permutation p ≤ 0.001) and explicitly **deferred** ds000245's `global_efficiency`
headline (claimed η² = 0.41, ordering CTL < ODN < ODP), stating precisely what was missing:

> re-fetch 45 subjects' BOLD from OpenNeuro S3 (~1.6 GB), re-run `fmri_tda_pipeline.py` with the
> K=100 coordinate path … **plus the new `--save-timeseries` capability** … then gate
> `global_efficiency` with the entire correlation→graph pipeline inside the `metric_fn`, and run
> the group-contrast permutation test.

This is exactly that: the deferred re-fetch, the `--save-timeseries` capability (added to
`dual_engine/fmri_tda_pipeline.py` in this session, mirroring the EEG pipeline's own
`save_timeseries`), and both gate questions run for real.

---

## Dataset & provenance

| Field | Value |
|---|---|
| Accession | OpenNeuro **ds000245** |
| Cohort | Parkinson's disease, resting-state fMRI, eyes closed |
| Groups | CTL (healthy control), ODN, ODP — 15 subjects each, 45 total |
| Acquisition | Siemens Verio 3T, TR = 2.5 s, task = `rest` (confirmed via `task-rest_bold.json`) |
| Transfer | 1.66 GB, 45 `_bold.nii.gz` files, ~37 MB each — full download, no ranged-fetch needed |
| Parcellation | **K = 100 coordinate KMeans** (`parcellate_bold`'s no-atlas fallback) — the original
  headline's own choice, **not** an anatomical atlas (Schaefer, etc.) |

The K=100 path is a real caveat carried through this whole report: it is a deterministic but
non-anatomical spatial clustering of in-brain voxels. Reproducing/gating η² = 0.41 establishes
whether that number is statistically real for *this* parcellation — not that it maps onto any
named brain region.

---

## Reproduction check

| Group | Mean global_efficiency | n |
|---|---|---|
| CTL | 0.390 | 15 |
| ODN | 0.433 | 15 |
| ODP | 0.454 | 15 |

**F = 14.34, p = 1.8 × 10⁻⁵, η² = 0.406** (parametric one-way ANOVA) — reproduces the claimed
η² = 0.41 to the second decimal, with the same CTL < ODN < ODP ordering. All 45 subjects
processed with **zero errors**.

---

## Q1 — Is the real global_efficiency value more extreme than a phase-randomized null?

Per subject, `validation.surrogate_testing.surrogate_test_topology_metric` was run with
`metric_fn` wired through the *entire* real pipeline — `connectivity_matrix` →
`graph_metrics`'s `global_efficiency`, on 200 Fourier phase-randomized surrogates (independent
per-region phase randomization, two-sided since there is no prior directional hypothesis for
this metric alone).

| Quantity | Value |
|---|---|
| Subjects gated | 45 / 45 |
| **Pass at p < 0.05** | **45 / 45 (100 %)** |
| p-value | 0.0050 for every subject (the floor at 200 surrogates: `(0+1)/(200+1)`) |
| z-score range | −160.9 to −19.8 (mean −80.4) |
| Direction | **Real value below the surrogate mean in 45 / 45 subjects** |

Every subject's real `global_efficiency` fell entirely outside its own 200-surrogate null
distribution, uniformly on the low side. Destroying each region's cross-region phase
relationships while preserving its own power spectrum (FT surrogates) produces networks with
*higher* graph global efficiency than the real, temporally-structured BOLD signal — the real
network is reliably less densely/efficiently connected than an unstructured phase-randomized
version of itself. This says the metric is measuring real, non-random temporal structure in
every subject; it does not by itself say anything about *why* real BOLD produces lower
efficiency than its randomized surrogate (a property of resting-state fMRI's low-frequency
autocorrelation, not investigated further here).

---

## Q2 — Does the CTL/ODN/ODP contrast survive a label-shuffle null?

`analysis/permutation.py`'s new `permutation_anova` (added this session — the module's existing
two-group functions do not cover a 3-group between-subjects design) shuffled group labels 10,000
times and recomputed η² each time.

| Quantity | Value |
|---|---|
| Observed η² | 0.4058 |
| Observed F | 14.34 |
| **Permutation p-value** | **0.0001** (1 / 10,001 — the resolution floor at 10,000 permutations) |

Not one of the 10,000 label-shuffles produced an η² as large as the real grouping. The
CTL < ODN < ODP contrast is not an artefact of unequal-variance or non-normal-group parametric
assumptions — the assumption-free permutation null agrees with the parametric ANOVA.

---

## Verdict

**Both questions this report was built to answer resolve decisively, in the direction of the
original claim:**

1. **Reproduction**: η² = 0.406, matching the claimed 0.41 closely, same group ordering, on a
   fresh 45-subject re-fetch with zero processing errors.
2. **Q1 (metric validity)**: 45/45 subjects — the real global_efficiency value is never
   consistent with a phase-randomized null of its own timeseries.
3. **Q2 (contrast reality)**: p = 0.0001 — the group contrast is not explainable by a
   between-subjects label-shuffle null.

**Caveats that limit what this does and does not establish:**

- The K=100 parcellation is a non-anatomical coordinate clustering, not a validated brain atlas.
  This gate confirms the *number* is statistically real for this specific pipeline; it is not an
  anatomical or clinical finding, and no claim about Parkinson's mechanism is made.
- No motion/confound regression was applied (`parcellate_bold`'s `confounds` argument was not
  supplied) — head-motion-correlated connectivity differences between groups (a common resting-
  state fMRI confound, and plausible here given ODN/ODP are older, symptomatic cohorts) have not
  been ruled out. This is the natural next gate, analogous to the ds005620 report's residual-EMG
  check.
- Density-thresholded graph construction (`graph_metrics`, top 15 % of edges by weight) is one of
  several standard choices; this result is for that choice, not shown to be threshold-invariant.
- Single dataset; no independent replication cohort run.

---

## Reproduce

```bash
pip install nibabel nilearn scikit-learn networkx ripser scipy

python tools/fetch_ds000245.py --dest data/ds000245

python -m dual_engine.fmri_tda_pipeline \
    --bids-root data/ds000245 --t-r 2.5 \
    --save-timeseries outputs/ds000245_fmri_tda/roi_timeseries \
    --out outputs/ds000245_fmri_tda

python tools/gate_ds000245_global_efficiency.py \
    --n-surrogates 200 --n-permutations 10000 --n-jobs 4
```

Offline tests for the pure logic (no network, no real data):
`pytest tests/test_fetch_ds000245.py tests/test_fmri_tda_pipeline.py tests/test_permutation.py tests/test_gate_ds000245_global_efficiency.py`
