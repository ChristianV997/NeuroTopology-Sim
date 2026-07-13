# ds000245 fMRI TDA — Status & Honest Findings

**Bottom line:** the pipeline is built, self-tested, and ready to run. The two blockers below
were about running it *inside the build sandbox*; both are now resolved by running it in
**GitHub Actions** instead (see "Easiest way to run it" below). No empirical result is claimed
here — the numbers appear on the workflow run page once you trigger it.

## Easiest way to run it (resolves both blockers)

Trigger the **`fMRI-TDA ds000245`** workflow from the repo's **Actions** tab → *Run workflow*.
It needs no secrets. It:

- pulls ds000245 straight from the **OpenNeuro public S3 bucket** (`--no-sign-request`), so the
  data is local to the runner — sidestepping Blocker 1 entirely (no base64/MCP channel), and
- uses the **authentic ds000245 `participants.tsv`** from OpenNeuro (Age, Gender, MMSE, **OSITJ**),
  not the mismatched meditation-EEG metadata that was in the Drive copy — resolving Blocker 2.

It fans out one job per group (CTL/ODN/ODP), runs the pipeline, and produces:
- a **rendered group-comparison table** in the run summary (F, p, η² per metric), and
- a downloadable **`cohort-result`** artifact (`cohort_result.json` + `summary.md`).

The two blockers below are retained for the record; they describe why the *sandbox* couldn't
run it, which the CI path avoids.

## What was verified (real, checked facts)

- The Google Drive folder **"OpenNeuro BIDS"** exists and is a real DataLad dataset
  (`.datalad/`, `.gitattributes`).
- It contains 45 imaging subject folders: `sub-CTL01–15`, `sub-ODN01–15`, `sub-ODP01–15`,
  plus a stray `sub-098` and a `.datalad` folder.
- The imaging content is **real**, not git-annex pointers: `sub-CTL03/func/sub-CTL03_task-rest_bold.nii.gz`
  is **37,862,444 bytes (37.8 MB)** of 4D BOLD.
- The BOLD acquisition sidecar is real: **TR = 2.5 s**, Siemens Verio 3T, eyes-closed rest,
  40 slices with slice timing, flip angle 80°.
- Compute environment is ready: `nibabel 5.4.2`, `nilearn 0.14.0`, `ripser 0.6.15`,
  `networkx 3.6.1`, `scikit-learn`, `scipy`, `statsmodels`.

## Blocker 1 — data cannot be transferred into the sandbox

The Google Drive MCP connector returns file bytes as **base64 inside the tool response**.
A single 37.8 MB NIfTI ≈ 50 MB of base64 ≈ millions of tokens — it cannot pass through that
channel, and the full cohort is ~2.2 GB. The connector can enumerate folders and read small
text files (e.g. the 7 KB `participants.tsv`), but not the imaging volumes. There is no
`datalad get` / `rclone` mount to the real bytes in this environment.

## Blocker 2 — metadata provenance mismatch (important)

The `participants.tsv` **inside the "OpenNeuro BIDS" folder is not the ds000245 file**. It is
the metadata table of a different, 98-subject **meditation EEG** study:

```
participant_id  gender  age  group  ...  years_of_practice  notes
sub-001  m  26  htr  ...  3   ...
sub-002  f  62  htr  ...  31  ...
...
sub-098  f  60  sny  ...  4   ...
```

Groups are `htr / ctr / tm / vip / sny` (meditation traditions), conditions
`meditation / thinking`. There are **zero CTL/ODN/ODP rows**. So the folder mixes ds000245
imaging folders with a different dataset's BIDS metadata. Consequence: the age/sex/clinical
covariates for the 45 fMRI subjects are **absent here** — the CTL/ODN/ODP grouping exists
only as folder-name prefixes. A rigorous group comparison needs the *real* ds000245
`participants.tsv`.

## What IS delivered (real, tested)

`dual_engine/fmri_tda_pipeline.py` — a complete, correctly-scoped pipeline:

1. Parcellate BOLD (nilearn `NiftiLabelsMasker`: z-score, band-pass 0.01–0.1 Hz, confound
   regression) → region×time. Offline fallback: deterministic KMeans coordinate parcellation.
2. Functional connectivity (nilearn `ConnectivityMeasure`).
3. Persistent homology (ripser on the 1−|corr| distance matrix): β₀, β₁, total H1 persistence.
4. Classical graph metrics (networkx): modularity, global efficiency, mean degree, small-worldness.
5. Group comparison: one-way ANOVA + η² effect size.

**Verified end-to-end on a synthetic 4D fixture** (`--self-test`, 12 subjects, 3 groups).
The fixture plants a CTL>ODN>ODP coupling gradient; the pipeline recovers it in
`total_persistence_h1` (means 0.10 / 0.18 / 0.80, F=84, η²=0.95) — this confirms the code is
correctly wired. It is a **code-verification result on synthetic data, not a Parkinson's finding.**
Tests: `tests/test_fmri_tda_pipeline.py` (5 passed).

## How to actually run it on the real data

On a machine with the data on local disk (not this sandbox):

```bash
# 1. Get the REAL ds000245 with real metadata (choose one):
datalad install https://github.com/OpenNeuroDatasets/ds000245.git
cd ds000245 && datalad get sub-*/func/*_bold.nii.gz sub-*/anat/*_T1w.nii.gz
#   or: aws s3 sync --no-sign-request s3://openneuro.org/ds000245 ds000245

# 2. Fetch a standard atlas (e.g. Schaefer-200) for anatomical parcellation.

# 3. Run the pipeline:
python -m dual_engine.fmri_tda_pipeline \
    --bids-root /path/to/ds000245 \
    --atlas /path/to/schaefer200_labels.nii.gz \
    --t-r 2.5 --out outputs/fmri_tda
#   -> outputs/fmri_tda/cohort_result.json  (provenance: real_fmri)
```

Before reporting any group result, obtain the **authentic** ds000245 `participants.tsv`
(the one in the current Drive folder is the wrong dataset's) to attach real covariates.

## Honest limitations for any eventual real run

- n = 15 per group is modest; effect sizes + CIs, not bare p-values.
- Preprocessing here is nilearn-level (parcellation, band-pass, confound regression), **not**
  a full fMRIPrep run (no motion correction / normalization from raw) — state this in any writeup.
- Atlas choice (Schaefer vs AAL) and edge-density threshold affect topology; report them.
- Persistent homology finding *nothing* where classical connectivity found degradation would
  be a real negative result to report, not to tune away.
