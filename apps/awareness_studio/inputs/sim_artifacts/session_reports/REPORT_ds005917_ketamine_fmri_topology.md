# ds005917 (NIMH Ketamine Mechanism of Action Study) — real resting-state fMRI topology, MDD group, n=24

**Verdict up front:** newly onboarded (NIMH, MDD/BP/HC groups, CC0-adjacent
public deposit). This activates `dual_engine/fmri_tda_pipeline.py` — a
persistent-homology + graph-theoretic topology pipeline previously verified
**only on a synthetic fixture** — on **real fMRI data for the first time**.
Within-subject drug-vs-placebo contrast (ketamine infusion vs. saline
infusion, same subjects, `ses-d2` vs `ses-p2` real BIDS session labels) on
**24 of 25 MDD patients** with complete crossover data: **clean null on
every metric** (paired t-test p = 0.18–0.97, Wilcoxon p = 0.25–0.92, |paired
effect size d_z| ≤ 0.28).

## 1. Why this dataset, and an honest scope limitation up front

ds005917 is real, well-powered (58 total participants: 33 MDD, 22 HC, 3 BP;
45 with complete drug/placebo crossover data), and directly relevant to
altered/consciousness-adjacent states via ketamine's dissociative-anesthetic
mechanism — but it ships **raw BOLD only, no fMRIPrep or other
spatial-normalization derivatives**, and this sandbox has no FSL/ANTs to
perform real anatomical registration to a shared atlas.

**Rather than fabricate a weak custom registration**, this run uses
`parcellate_bold`'s existing, already-tested fallback
(`atlas_labels_img=None` → per-subject KMeans coordinate parcellation in
each subject's own native space — the module's own docstring is explicit:
"labelled synthetic, never presented as an anatomical atlas"). This is
methodologically sound for what this pipeline actually computes: **Betti
numbers, modularity, global efficiency, and total persistence are
graph-topology summary statistics, invariant to node/region labeling** —
they do not require region 12 in subject A to anatomically correspond to
region 12 in subject B. What *would* be invalid without a shared atlas is a
per-region statistic (e.g. "connectivity between region 12 and region 47");
this pipeline never computes one. **The BOLD signal itself is 100% real**
(`provenance="real_fmri"`); only the parcel boundaries are per-subject
data-driven rather than anatomically registered — a real, disclosed
limitation, weaker rigor than ds006644's fMRIPrep-derivative-based run.

## 2. Design

Real BIDS session labels directly encode condition — not inferred:
`ses-d2`/`ses-d10` = drug (ketamine) sessions, `ses-p2`/`ses-p10` = placebo
sessions (2 or 10 days post-infusion). Every complete subject has **both**
arms (within-subject crossover). This run uses `ses-d2` vs `ses-p2` on
`task-rest_run-01`, restricted to the **MDD group** (n=25 with complete
session data — the largest, best-powered subgroup; HC n=18 and BP n=2 exist
for a future pass, not run here).

**Real data quirk found and handled, not hidden:** `sub-MOA113` has complete
`infusion_1`/`infusion_2` crossover metadata in `participants.tsv` but its
`ses-d2` rest-run BOLD file returns a 404 on the real S3 bucket — the
participant metadata and the actual file inventory disagree. The streaming
script originally crashed on this (an unhandled exception after 9 subjects
had already completed); fixed to catch the download failure and record it
as an error-flagged row, so the run completes and reports **24/25** subjects
rather than silently guessing or losing the other 24 subjects' results.

## 3. Result (paired t-test + Wilcoxon signed-rank, n=24, MDD group)

| metric | drug mean | placebo mean | mean diff | paired t p | Wilcoxon p | d_z |
|---|---|---|---|---|---|---|
| betti1 | 60.08 | 60.88 | −0.79 | 0.713 | 0.753 | −0.076 |
| total_persistence_h1 | 2.764 | 2.769 | −0.005 | 0.973 | 0.922 | −0.007 |
| modularity | 0.279 | 0.296 | −0.017 | 0.304 | 0.252 | −0.215 |
| global_efficiency | 0.388 | 0.387 | +0.001 | 0.929 | 0.663 | 0.018 |
| mean_degree | 14.84 | 14.84 | 0.0 | n/a (0 variance) | n/a | n/a |
| small_worldness | 4.155 | 3.654 | +0.501 | 0.176 | 0.439 | 0.285 |

**No metric separates the drug session from the placebo session.** Effect
sizes are all small (|d_z| ≤ 0.285). `mean_degree` is degenerate by
construction — `graph_metrics()` thresholds every subject's connectivity
graph to a fixed 15% edge density, so mean degree is deterministic given
`n_regions=100` and identical (14.84) across every session; it carries no
information in this pipeline and is reported for completeness, not
interpreted.

## 4. Interpretation

Two honest readings, not adjudicated here:

1. **Ketamine's acute dissociative effect may not leave a detectable
   signature in these whole-graph topology summary statistics 2 days
   post-infusion** — `ses-d2` is 2 days after the ketamine infusion, likely
   past the acute dissociative window (which resolves within hours), so this
   contrast may be probing a sub-acute/consolidation period rather than the
   acute altered-state itself. A same-day or acute-window scan (not present
   in this dataset) would be needed to test the acute hypothesis directly.
2. **The per-subject KMeans parcellation (forced by the missing
   normalization derivatives) may wash out a real anatomically-localized
   effect** that a shared-atlas parcellation (as used for ds006644) could
   detect — whole-graph summary statistics are coarser than region-specific
   ones, and this dataset's real infrastructure gap (no FSL/ANTs) caps what
   this pass can detect.

## 5. Caveats

- **Weaker registration rigor than ds006644** (see §1) — disclosed, not
  hidden. A future pass with real spatial normalization (FSL/ANTs/fMRIPrep)
  could re-run this exact contrast on a shared atlas.
- **n=24** (MDD group only). HC (n≈18) and BP (n≈2) groups available for a
  future extension.
- **Single-timepoint contrast** (`d2` vs `p2` only) — `d10`/`p10` (10-day
  timepoints) were not analyzed in this pass.
- **No confound regression** — raw BOLD, no motion/physiological regressors
  applied (none are readily available without the missing preprocessing
  derivatives).

Data: `outputs/dual_engine/ds005917/cohort_result.json`,
`outputs/dual_engine/ds005917/paired_stats.json`.
