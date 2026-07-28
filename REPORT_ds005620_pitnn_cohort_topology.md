# PITNN empirical falsification and phase topology on the full ds005620 propofol cohort

**Run:** `outputs/pitnn_cohort/ds005620/RunRecord.json` — run_id `ef432e1788b331d7`
**Tools:** `tools/stream_pitnn_cohort_ds005620.py` → `tools/analyze_pitnn_cohort_ds005620.py`
**Status:** n = 20 paired subjects. PITNN verdict **NOT_SUPPORTED in 20/20**. One topology
descriptor separates the states robustly; the graph-persistence descriptors do not.

---

## Why this run exists

The prior cohort artifact (`artifacts/topology_monitoring/cohort_sedation/cohort_topology_summary.json`,
schema `NeuroTopologySim.CohortSedationTopology.v1`) reported `discovered_subjects: 1`,
`paired_subjects: ["sub-1010"]`, and `power_status: "insufficient_paired_subjects"` — every
Wilcoxon p-value was `null`. The blocker was never the analysis code; it was that only one
subject's raw EEG had ever been fetched, because ds005620 is **83 GB** of `.eeg` across 202
recordings.

Two defects also limited the older cohort script (`scripts/run_cohort_eeg_topology.py`):

1. It globbed `*task-sed2*.vhdr` only. The onboarding registry maps **both** `sed` and `sed2`
   to the `sedated` state, and `sed` is by far the larger set (92 vs 51 recordings). Most
   sedation data was silently invisible to it.
2. Its awake glob `*task-awake*.vhdr` matched `acq-EC`, `acq-EO` **and** `acq-tms`, then kept
   whichever the dict comprehension happened to assign last. TMS-evoked recordings are a
   different regime and must not enter a resting-state contrast.

This run fixes both and processes the whole cohort.

---

## Dataset & provenance

| Field | Value |
|---|---|
| Accession | OpenNeuro **ds005620** |
| Study | *A Repeated Awakening Study Exploring the Capacity of Complexity Measures to Capture Dreaming During Propofol Sedation* |
| Authors | Bajwa, Nilsen, Skukies, Aamodt, Ernst, Storm, Juel |
| Ethics | REK South East Norway, ref. 2015/1520 |
| License | CC-BY-4.0 |
| Acquisition | BrainVision, 64–65 channels, `SamplingInterval=200.0 µs` → **5000 Hz**, `IEEE_FLOAT_32`, MULTIPLEXED |
| Subjects on S3 | 21 |
| **Paired subjects analysed** | **20** |

### Condition pairing (explicit; no label inference)

Per the dataset README: `EC` = eyes closed during wakefulness, `rest` = rest during sedation,
`sed` = the sedation condition, `sed2` = a one-minute resting EEG recorded just before an
awakening, `run-N` = successive awakenings.

```
awake   := task-awake_acq-EC              (20/20 subjects)
sedated := task-sed_acq-rest_run-1        (20/20 subjects)
```

`sed` is preferred over `sed2` because it is the sustained sedation condition rather than a
one-minute pre-awakening snippet; `run-1` is taken for every subject so run index is constant
across the cohort. `acq-tms` and `acq-EO` are excluded by construction. All 20 subjects
resolved to exactly this pairing — no fallback was exercised.

### Exclusion cross-check (independent confirmation of n = 20)

`participants.tsv` carries the study's own quality flags. Cross-referencing them against the
cohort this pipeline built:

- `excluded == True` for exactly one participant, **sub-SD_1037** — and that is precisely the
  subject dropped here for having **zero** `task-sed*` recordings on S3 (`awakenings = 0`).
  The structural pairing rule and the authors' exclusion agree without being told to.
- `bad_after_preprocessing` is non-`False` for sub-SD_1054, sub-SD_1068 and sub-SD_1071, and in
  every case names only `task-sed_acq-tms_run-*` files — TMS acquisitions, already excluded.

**No recording used in this analysis is flagged bad or excluded by the dataset authors.**

---

## How the run was made efficient

Downloading ds005620 in full is 83 GB. It was not downloaded in full.

A BrainVision `.eeg` is a flat MULTIPLEXED binary array, and the `.vhdr` for this dataset
declares **no `DataPoints` field** (verified by direct header inspection), so MNE infers length
from file size. A byte-range prefix truncated on a whole-sample boundary is therefore itself a
valid, shorter recording. The repo already encoded this in
`base_runner.sync_s3_subject._required_eeg_bytes`; this tool reuses the same arithmetic and
narrows it further to fetch only the **two** recordings each subject actually needs instead of
all eight.

| | Full download | This run |
|---|---|---|
| Bytes transferred | ~83 GB | **~2 GB** (40 s prefix × 2 recordings × 20 subjects) |
| Peak local disk | 83 GB | **~104 MB** (one subject, deleted before the next) |
| Wall clock | — | **~17 min**, 20/20 subjects, 0 failures |

`base_runner.run_streaming_loop` owns the sync → process → delete → checkpoint discipline, so
the run is resumable and never accumulates raw data. Per-window PLV uses the identity
`mean_t exp(i(φ_a − φ_b)) = (z zᴴ)/N`, avoiding the `(65, 65, 5000)` intermediate the older
scripts materialise (~170 MB per window).

### Analysis parameters

| Parameter | Value |
|---|---|
| Downloaded prefix | 40 s per recording |
| Discarded onset | 5 s |
| Analysed | 30 s per condition |
| Decimation | 5000 Hz → **500 Hz** (anti-aliased FIR, zero-phase) |
| Band | **30–80 Hz** (gamma; PITNN's `standardize_condition` default) |
| Windows | 3 × 10 s per condition |
| Channels | 65 (11 subjects) / 64 (9 subjects) — constant within each subject |

---

## Q1 — Does the topology separate awake from sedated at cohort level?

Three tests per metric. The **subject-blocked permutation test**
(`analysis.permutation.subject_blocked_permutation_test`) is the governing one: it collapses
each subject's windows to one value per condition *before* permuting, so repeated windows
cannot inflate significance. It auto-detected the within-subject design and ran a paired
sign-flip test. MixedLM is reported for completeness but operates on all 120 window-level rows
and is correspondingly anti-conservative.

| Metric | Direction (sedated > awake) | Permutation p | dz | Wilcoxon p | MixedLM p |
|---|---|---|---|---|---|
| **Phase-discontinuity proxy** (`mean_beta_1`) | **19 / 20** | — | — | **8.2 × 10⁻⁵** | — |
| Persistence landscape area | 15 / 20 | 0.0746 | −0.42 | 0.0400 | <0.0001 |
| Mean PLV | 7 / 20 | 0.2700 | +0.25 | 0.1769 | 0.0110 |
| Graph β₁ (ripser H1) | 12 / 20 | 0.4396 | +0.18 | 0.4938 | 0.1264 |

**The one robust result is the phase-discontinuity proxy.** It rises under sedation in 19 of 20
subjects (median 5.62 → 9.13, paired Wilcoxon p = 8.2 × 10⁻⁵). This is a subject-level paired
test on one scalar per subject per condition, so it carries no pseudoreplication risk and needs
no permutation correction.

**What that metric actually is matters.** `sim/pitnn/empirical_pipeline.topology_from_phase`
computes it as the per-sample count of adjacent-channel phase differences exceeding 0.75π,
after referencing every channel to channel 0. Its own docstring calls it a *"conservative beta-1
proxy"*. **It is not persistent homology and not a Betti number.** It is a count of large
phase discontinuities across the channel ordering, and that ordering is the `.vhdr` channel
sequence, not a spatial adjacency. Read plainly, it says gamma-band phase relationships across
the montage become markedly more disordered under propofol — a descriptive finding consistent
with the standard picture, not a novel topological one.

The genuine persistent-homology descriptors are weaker. Landscape area moves in the same
direction (15/20) but only reaches p = 0.075 under the governing permutation test; its
significance under Wilcoxon (0.040) and MixedLM (<0.0001) reflects those tests' weaker control,
not stronger evidence. **Reported as suggestive, not significant.** Graph β₁ is flat, and mean
PLV — despite a visible median drop (0.600 → 0.513) — is not significant at subject level
because the effect reverses in 7 subjects.

---

## Q2 — Does PITNN gain evidential support from real anesthesia EEG?

No. `scripts/run_empirical_falsification.py` was run per subject on the paired
`state_a`/`state_b` bundle, comparing a topology-augmented design matrix against the classical
basis via a Gaussian likelihood-ratio Bayes factor, with **PASS reserved strictly for K > 100**.

| Quantity | Value |
|---|---|
| Verdicts | **NOT_SUPPORTED — 20 / 20** |
| Bayes factor range | 0.9999993 – 0.9999999 |
| Median K | 0.99999953 |
| Subjects above K > 100 | **0** |
| ΔAICc (sub-1010) | −2.00 (favouring the classical model) |

K sits at essentially exactly 1 for every subject: adding the topological regressor changes the
residual sum of squares negligibly, and the AICc penalty for the extra active parameter makes
the augmented model strictly worse. **The PITNN model gains no evidential support on real
propofol EEG.** This replicates, now at n = 20 instead of n = 1, the `NOT_SUPPORTED`/K = 1
outcome already recorded in the prior `empirical_falsification_report.json` artifacts.

The tension with Q1 is the informative part: the same recordings that make a *descriptive*
phase metric separate the states cleanly give the *generative* PITNN model no advantage. A
descriptor that discriminates conditions is not evidence for the model that motivated it.

---

## Confound checks

- **Pairing is constant.** All 20 subjects contributed `task-awake_acq-EC` and
  `task-sed_acq-rest_run-1`. No subject used a fallback path, so run index, acquisition type and
  eye state cannot vary across the cohort.
- **TMS excluded.** No `acq-tms` recording entered any contrast; the study's own
  `bad_after_preprocessing` flags name only TMS files.
- **Onset artefact.** The first 5 s of every recording is discarded before analysis.
- **Equal data per condition.** Every subject contributes exactly 15 000 samples (30 s @ 500 Hz)
  and 3 windows per condition, so window count cannot drive a paired difference.
- **Montage size varies between subjects but never within one.** 11 subjects have 65 EEG
  channels and 9 have 64 (`sub-1036, 1060, 1061, 1062, 1064, 1067, 1068, 1071, 1074`); this is
  a property of the recordings themselves — `channels.tsv` types every channel as `EEG` and the
  zero-variance filter dropped none. Because β₁ and landscape area depend on graph size, this
  would matter for a between-subjects comparison, but **both conditions of every subject share
  that subject's montage**, so the paired contrast used here is unaffected.
- **Pseudoreplication** is controlled by construction — see the permutation method above. The
  divergence between permutation (p = 0.075) and MixedLM (p < 0.0001) on landscape area is
  exactly the gap that control closes, and is why the conservative number is the headline.

---

## Limitations

- **30 s per condition.** A byte-range prefix bounds analysis to the start of each recording.
  This is a deliberate cost/coverage trade, not full-recording evidence; a longer prefix is a
  one-flag change (`--download-seconds`, `--analyze-seconds`).
- **Sedation depth is not modelled.** `task-sed` is treated as one state. The dataset supports
  finer contrasts (per-awakening runs, behavioural response, dream report) that this run does
  not use — the registry declares `responsive_vs_unresponsive` and
  `experience_vs_no_experience` contrasts that remain untested here.
- **Gamma band only** (30–80 Hz). Propofol's most prominent signatures include frontal alpha
  and slow-wave changes that this band does not address.
- **Net spatial charge was uninformative.** `sensor_spatial_charge` returned 0.0 for every
  window in every subject: it rounds a signed sum of triangle windings to the nearest integer,
  and the montage-wide net cancels. This is a real null for that estimator as configured, not a
  failure — a localized (unsigned or regional) variant would be needed to say anything.
- **No multiple-comparison correction** across the four metrics. Applying even Bonferroni
  (α = 0.0125) leaves only the phase-discontinuity proxy standing.
- **Single dataset.** No replication cohort was run.

---

## Verdict

1. **Cohort power achieved.** n = 20 paired subjects, up from 1. `power_status` moves from
   `insufficient_paired_subjects` to a real, computed inference, at ~2.4 % of the naive
   download cost.
2. **PITNN: NOT_SUPPORTED, 20/20**, no subject anywhere near the K > 100 gate. The model is not
   supported by this dataset.
3. **One descriptor separates the states** — a phase-discontinuity count, 19/20 subjects,
   p = 8.2 × 10⁻⁵ — but it is an explicitly labelled proxy, not persistent homology, and it
   reports gamma phase disorganisation under propofol.
4. **Persistent-homology descriptors are suggestive at best** (landscape area, 15/20,
   permutation p = 0.075) or null (graph β₁, PLV).

These are descriptive EEG network measures. A paired difference between an eyes-closed awake
recording and a propofol sedation recording does not identify a mechanism, and none of these
metrics is a measure of awareness, dreaming, or consciousness.

---

## Reproduce

```bash
pip install mne ripser matplotlib pandas statsmodels

python tools/stream_pitnn_cohort_ds005620.py \
    --out outputs/pitnn_cohort/ds005620 --work-root data/ds005620_stream

python tools/analyze_pitnn_cohort_ds005620.py \
    --cohort-dir outputs/pitnn_cohort/ds005620
```

Both are resumable: re-running skips subjects already in `manifest.json`. Offline tests for the
pairing rule, byte-range arithmetic and PLV identity: `pytest tests/test_pitnn_cohort_ds005620.py`.
