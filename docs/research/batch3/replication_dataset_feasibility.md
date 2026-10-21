# Batch 3 — Cross-Dataset Replication Feasibility

Access date: 2026-10-16. Verification audit date: 2026-10-21. Package maintainers: Grok Chat B, Antigravity Agent C.
Status: Research feasibility audit only. Not empirical evidence.
Project Posture: **HOLD / SYNTHETIC_ONLY**.
No participant data were downloaded, opened, preprocessed, or analyzed. No signal files were touched.
Inspection levels used: `listed_in_catalog`, `metadata_inspected`, `files_locally_available`, `analysis_performed`.
Every candidate in this package is strictly at `listed_in_catalog` or `metadata_inspected` level. None are locally available or analyzed.

A successful feasibility note does not validate a theory, does not establish causal or biological validity, and does not emit a scientific PASS.

---

## 1. Replication Question

Can EEG topological and spectral descriptors previously explored on propofol-sedation EEG (OpenNeuro `ds005620`) generalize to an independent cohort with different hardware, montage, task, or acquisition protocol?

- **Prediction is not causation.**
- **Method feasibility is not consciousness evidence.**
- **Dataset availability is not permission to redistribute or to claim an empirical finding.**
- **Catalog enrollment N is an upper bound on recorded files, not analyzed cohort N.**

---

## 2. Ranking Criteria

1. **Independent cohort from `ds005620`**: Subjects, hardware, and acquisition facility must be distinct.
2. **Modality**: EEG or MEG with documented electrode positions and sampling rates.
3. **Open license with explicit terms**: Unambiguous open terms; unresolved license conflicts must be flagged and preserved without silent override.
4. **BIDS sidecar completeness**: Sidecar metadata (`eeg.json`, `channels.tsv`, `events.tsv`) present or documented.
5. **Altered awareness / task contrast**: Validated behavioral, sedation, or cognitive condition contrasts.
6. **Adequate sample size for held-out split**: Sufficient subjects ($N \ge 30$) to support locked held-out generalization without data leakage.
7. **Hardware / montage diversity**: BioSemi, Brain Products, or EGI systems evaluating cross-system robustness.
8. **Autonomic / behavioral covariates**: Concurrent ECG, respiration, or rating probes to enable partialling of peripheral confounders.

---

## 3. Ranked Candidates

### 1. ds003969 — Meditation vs Thinking Task
- **Title**: Meditation vs thinking task
- **Role**: Primary independent replication candidate (Rank 1 conditional)
- **Modality**: EEG (BioSemi ActiveTwo 64 channels, standard 10–10 headcap, external mastoid/EOG electrodes)
- **Primary Source**: OpenNeuro `v1.0.0` (https://openneuro.org/datasets/ds003969/versions/1.0.0), DOI `10.18112/openneuro.ds003969.v1.0.0`
- **License**: CC0 Public Domain Dedication (declared in catalog and dataset description)
- **Catalog Enrollment**: 98 participants, 1 session.
- **Analyzed Cohort Discrepancy**: Catalog states 98 subjects. Public documentation and source TSVs record 24 Himalayan Yoga (HT), 31 Control (CTR), 19 Vipassana (VIP), 20 Isha Shoonya (SNY), and 4 Transcendental Meditation (TM) subjects (total 98), whereas companion source folders describe ~100 participants. Catalog N is an enrollment count, not analyzed N.
- **Acquisition Protocol**: Sampling rate 1024 Hz. Alternating blocks of breath-counting meditation and active thinking with eyes closed.
- **Replication Value**: Independent hardware (BioSemi vs Brain Products in ds005620) and non-pharmacological state contrast.
- **Blockers**: Subgroup count discrepancy between catalog headline and source tables; no concurrent autonomic channels; requires BioSemi BDF BIDS adapter.

### 2. ds008836 — Vipassana Meditative Depth and Heartbeat-Evoked Responses
- **Title**: Heartbeat-evoked responses and self-reported meditative depth in Vipassana practitioners
- **Role**: Autonomic covariate candidate (Rank 2)
- **Modality**: High-density EEG (64 channels) + concurrent ECG, respiration, EMG, and electrodermal activity (EDA)
- **Primary Source**: OpenNeuro `v1.0.1` / `v1.0.2` (https://openneuro.org/datasets/ds008836), DOI `10.18112/openneuro.ds008836.v1.0.0`
- **License**: CC0 Public Domain Dedication (verified on OpenNeuro catalog page 2026-10-21)
- **Catalog Enrollment**: 39 participants, 2 sessions.
- **Analyzed Cohort Status**: Catalog states 39 experienced meditators. No analysis performed; usable N after artifact rejection is unverified.
- **Acquisition Protocol**: Silent meditation with repeated real-time self-reports of meditative depth across distinct blocks (rest, pre-up, SAPO, active oddball, SILENT, cool-down).
- **Replication Value**: Enables rigorous partialling of cardiovascular and respiratory confounders from neural phase and topological metrics.
- **Blockers**: Companion peer-reviewed journal article in preparation / not yet indexed; no prior locked validation split.

### 3. ds001787 — EEG Meditation Study with Mind-Wandering Probes
- **Title**: EEG meditation study
- **Role**: Mind-wandering probe candidate (Rank 3)
- **Modality**: EEG (BioSemi ActiveTwo, 80 channels: 64 scalp + 16 auxiliary/external)
- **Primary Source**: OpenNeuro `v1.1.1` (https://openneuro.org/datasets/ds001787/versions/1.1.1), DOI `10.18112/openneuro.ds001787.v1.1.1`
- **License**: CC0 Public Domain Dedication
- **Catalog Enrollment**: 24 participants, 3 sessions.
- **Analyzed Cohort Status**: Catalog states 24 subjects. Usable N after artifact rejection unverified.
- **Acquisition Protocol**: Originally recorded at 2048 Hz, downsampled to 256 Hz. Meditation interrupted approximately every 2 minutes with thought-probe ratings (concentration vs mind-wandering).
- **Replication Value**: Behavioral probe labels mapped to continuous EEG blocks.
- **Blockers**: Small sample size ($N=24$) limits statistical power for a held-out split.

### 4. ds004572 — Sham Hypnosis Techniques (Balanced Placebo)
- **Title**: The effects of sham hypnosis techniques
- **Role**: Construct generalization candidate (Rank 4)
- **Modality**: EEG (64-channel EasyCap, Brain Products, BrainVision format `.vhdr`, `.vmrk`, `.eeg`)
- **Primary Source**: OpenNeuro `v1.3.1` (https://openneuro.org/datasets/ds004572), DOI `10.18112/openneuro.ds004572.v1.3.1`
- **License**: CC0 Public Domain Dedication
- **Catalog Enrollment**: 52 participants (39 females), 1 session.
- **Analyzed Cohort Status**: Published study notes hypnotizability scores available for only 83% of participants ($N=43$). Catalog N is not analyzed N.
- **Acquisition Protocol**: 2x2 balanced placebo design crossing induction technique (conventional vs unconventional) with framing (hypnosis vs relaxation), with pre/post eyes-closed rest.
- **Replication Value**: Tests whether topological descriptors generalize across distinct non-pharmacological altered-awareness constructs.
- **Blockers**: Construct divergence (hypnosis vs sedation/meditation); missingness in hypnotizability scores (17%); version tag ambiguity (`v1.3.1` vs `v1.3.2`).

---

## 4. Primary Reference Cohort (Not a Replication)

### ds005620 — Propofol Repeated Awakening Study
- **Accession**: `ds005620`
- **Role**: Project reference cohort only. Cannot replicate itself.
- **Primary Source**: OpenNeuro `ds005620` (https://openneuro.org/datasets/ds005620), DOI `10.18112/openneuro.ds005620.v1.0.0`
- **License Conflict Statement**:
  > **Explicit Unresolved License Conflict Preserved**:
  > In `dataset_description.json`, the authors declare **CC0**. In the top-level `README` text, the authors specify that the dataset is **licensed under CC-BY-4.0**. In accordance with repository evidence governance, this conflict is explicitly recorded and preserved rather than resolved silently.
- **Catalog vs Analyzed N**: EEGDash/OpenNeuro catalog reports 21 participants. `participants.tsv` contains `excluded` and `bad_after_preprocessing` columns. Usable cohort N after exclusion filtering remains unverified from catalog text alone. Catalog N is an enrollment count, not analyzed N.
- **Montage & Hardware**: Brain Products 64/65 channels, 5000 Hz sampling rate. Tasks: `awake`, `sed`, `sed2`.
- **Blockers**: Same cohort as primary reference; usable N after exclusions unresolved; unresolved CC0 vs CC-BY-4.0 license conflict.

---

## 5. Deferred or Excluded Datasets

- **ds004541** — Multimodal EEG-fNIRS during surgical general anesthesia. OpenNeuro states 8 participants with variable channel counts (59, 40, 30, 38). **Deferred**: Sample size ($N=8$) is statistically inadequate for held-out validation; channel heterogeneity and surgical confounding.
- **ds005555** — Bitbrain Open Access Sleep Dataset (BOAS). Catalog lists 128 participants, but README documents 128 nights from 100 participants. License verified as CC0. **Deferred**: Sleep architecture represents a distinct physiological construct from sedation or meditation; wearable headband montage is non-comparable without locked channel mapping.
- **ds003171** — Anesthesia fMRI loss of consciousness (17 participants). **Excluded**: Modality is fMRI (T1w/BOLD), not EEG/MEG.
- **maziyarpanahi/openmed** — Local-first clinical NER and PII de-identification software repository (https://github.com/maziyarpanahi/openmed). **Excluded / Not an EEG source**: Software utility for text de-identification; not an EEG archive and not recommended as a runtime dependency.

---

## 6. What Would Prevent a Valid Replication

A replication attempt is invalid and blocked if:
1. Missing, ambiguous, or conflicting participant/session counts are treated as resolved without primary evidence.
2. Catalog enrollment N is conflated with analyzed N after exclusion or artifact rejection.
3. License terms are unconfirmed or license conflicts are silently overridden.
4. Sampling rate or montage layouts are unknown or mismatched.
5. No locked subject-held-out and forward-time validation split is enforced.
6. Volume conduction is unmodeled or treated as biological connectivity.
7. Autonomic covariates (heart rate, respiration) are ignored when present.
8. Synthetic or mock results are reported as empirical observations.
9. Any scientific PASS or proof claim is emitted from this feasibility package.

---

## 7. Machine-Readable Matrix

The machine-readable dataset matrix is maintained at:
[`reports/batch3/grok_chat_b/dataset_candidates.json`](file:///C:/Users/HP/OneDrive/Documentos/GitHub/.repo-dev-worktrees/batch2-replication-feasibility-pr394/reports/batch3/grok_chat_b/dataset_candidates.json)

---

## 8. Epistemic Statement

No participant data were downloaded or analyzed. All evaluations remain conditional on future access authorization, data-use agreements, license verification, and metadata checks under the repository bounded-access policy.
