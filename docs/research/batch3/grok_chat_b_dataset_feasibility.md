# Batch 3 metadata audit — independent EEG replication candidates

Research date: 2026-10-16.
Live main SHA checked: `a65611adcf4490a0d2378cbecb92dd883f4c5f0a` (refreshed 2026-10-22; original base `3f3fe8593303184cb88eef056c1322f3d4e57a16`).
Prior package: open PR #394 on `batch3/grok-chat-b-replication-dataset-feasibility` owns `docs/research/batch3/replication_dataset_feasibility.md` and `reports/batch3/grok_chat_b/dataset_candidates.json`. This note uses distinct paths.
Status: HOLD / SYNTHETIC_ONLY. No scientific PASS. No participant data downloaded or analyzed.

## Question

Can descriptors explored on OpenNeuro `ds005620` / NEMAR `on005620` propofol EEG generalize across an independent cohort, hardware, montage, and protocol?

Catalog counts are not paper inclusion counts. An inventory parser does not establish the analyzed cohort or an authoritative exclusion manifest. Neither catalog license metadata nor repository README files constitute verified transfer permission without resolving contradictory upstream statements.

## Source Statement Classification

All source statements in this audit are strictly classified into two categories:
1. **author-supplied**: Statements made by original dataset uploaders, repository READMEs, or publication authors (e.g. catalog participant counts, BIDS JSON sidecar fields, published recruitment totals, and declared license strings). These are preserved as claims rather than accepted as verified empirical facts.
2. **independently verified**: Statements established directly through fail-closed artifact inspection and structural comparisons (e.g. the presence of licensing contradictions between `dataset_description.json` and GitHub READMEs, file header columns in `participants.tsv`, DOI resolution endpoints, and the verification that no candidate dataset employs propofol).

## Reference: ds005620 / on005620

- Version/DOI: v1.0.0, `10.18112/openneuro.ds005620.v1.0.0` (DOI URL: `https://doi.org/10.18112/openneuro.ds005620.v1.0.0`, source: `https://openneuro.org/datasets/ds005620/versions/1.0.0`, retrieved 2026-10-16).
- License conflict, preserved:
  - `dataset_description.json` states `"CC0"` (`https://openneuro.org/datasets/ds005620/versions/1.0.0`) [author-supplied].
  - NEMAR catalog states `"CC0"` (`https://nemar.org/dataexplorer/detail?dataset_id=on005620`) [author-supplied].
  - OpenNeuroDatasets GitHub README states `"This dataset is licensed under CC-BY-4.0."` (`https://github.com/OpenNeuroDatasets/ds005620/blob/master/README`) [author-supplied].
  - Contradiction is preserved fail-closed [independently verified]; no permission or waiver is inferred.
- Catalog n: NEMAR states 21 participants [author-supplied]. `participants.tsv` has a header plus 21 data rows and columns `excluded` and `bad_after_preprocessing` [independently verified]. This audit does not claim which rows were excluded, nor does it infer completer N.
- Tasks: awake, sed, sed2.
- Hardware: one inspected sidecar (sub-1010 awake EC) states 5000 Hz, 65 channels, Brain Products, reference n/a. EEGDash catalog states mixed 64/65 channel counts.
- Fit: reference only. It cannot replicate itself. No candidate below is propofol EEG, so none is a same-mechanism replication [independently verified].

## Candidates

### ds003969 — construct generalization, not same mechanism

- Version/DOI: v1.0.0, `10.18112/openneuro.ds003969.v1.0.0` (DOI URL: `https://doi.org/10.18112/openneuro.ds003969.v1.0.0`, source: `https://openneuro.org/datasets/ds003969/versions/1.0.0`, retrieved 2026-10-16) [independently verified].
- License: `dataset_description.json` states `"CC0"` [author-supplied].
- Catalog n: OpenNeuro states 98. A public comment reports group counts summing to 98 and cites earlier studies of about 100 [author-supplied].
- Paper: Braboszcz et al. 2017, *PLoS ONE*, `10.1371/journal.pone.0170647` (`https://doi.org/10.1371/journal.pone.0170647`), states 20 Vipassana, 27 Himalayan Yoga, 20 Isha Shoonya, and 32 controls collected, then 4 matched groups of 16 (N=64 analyzed) [author-supplied]. Catalog 98 is not the analyzed N.
- Tasks: med1breath, med2, think1, think2. Eyes closed. Sampling rate not stated on the inspected catalog page.
- Fit: best open meditation-versus-control candidate for construct generalization. Not a propofol replication. Rank is not by sample size alone.

### ds008836 — construct generalization with autonomic covariates

- Version/DOI: v1.0.1, `10.18112/openneuro.ds008836.v1.0.1` (DOI URL: `https://doi.org/10.18112/openneuro.ds008836.v1.0.1`, source: `https://openneuro.org/datasets/ds008836/versions/1.0.1`, retrieved 2026-10-16) [independently verified].
- License: `dataset_description.json` and catalog state `"CC0"` [author-supplied].
- Catalog n: 39 participants, 2 sessions [author-supplied].
- Hardware: `task-meditation_eeg.json` states 500 Hz, Brain Products, reference FCz. README states 64-channel EEG plus ECG, respiration, EMG, and electrodermal activity. Catalog modality list shows EEG only. Conflict preserved.
- Related paper cited by the dataset: Reggente et al. 2024, `10.1016/j.bpsgos.2024.100402` (`https://doi.org/10.1016/j.bpsgos.2024.100402`). Analyzed N for a heartbeat-evoked companion was not extracted.
- Fit: useful for respiration/autonomic controls. Not equanimity evidence. Not propofol.

### ds001787 — small-n meditation probes

- Version/DOI: v1.1.1, `10.18112/openneuro.ds001787.v1.1.1` (DOI URL: `https://doi.org/10.18112/openneuro.ds001787.v1.1.1`, source: `https://openneuro.org/datasets/ds001787/versions/1.1.1`, retrieved 2026-10-16) [independently verified].
- License: `dataset_description.json` states `"CC0"` [author-supplied].
- Catalog n: 24 subjects, 3 sessions. README: 2048 Hz downsampled to 256 Hz (Biosemi). Channel count not stated [author-supplied].
- Paper: Brandmeyer and Delorme 2016, `10.1007/s00221-016-4811-5` (`https://doi.org/10.1007/s00221-016-4811-5`), states 25 Himalayan Yoga meditators participated and that one participant reported additional information after collection. Catalog 24 is not automatically the paper N [author-supplied].
- Fit: probe labels are useful. n=24 is a power limit, not a reason to prefer or reject by size alone. Not propofol.

### ds004572 — different construct (hypnosis)

- Version/DOI: `dataset_description.json` states v1.3.2, `10.18112/openneuro.ds004572.v1.3.2` (DOI URL: `https://doi.org/10.18112/openneuro.ds004572.v1.3.2`, source: `https://openneuro.org/datasets/ds004572/versions/1.3.2`, retrieved 2026-10-16) [independently verified]. Earlier catalog pages listed both v1.3.1 and v1.3.2.
- License: `dataset_description.json` states `"CC0"` [author-supplied].
- Catalog n: 52 participants (39 females). README: 64-channel EasyCap, Brain Products. Sampling rate not stated [author-supplied].
- Paper: 2024 Scientific Reports paper states hypnotizability scores were available for 83 percent of participants [author-supplied].
- Fit: hypnosis/framing, not propofol or meditation. Construct generalization only.

## Not replication datasets

- `maziyarpanahi/openmed`: local-first clinical NER and PII de-identification. Not an EEG/MEG archive.
- `research-agent frameworks`: orchestration tools do not supply independent EEG cohorts.
- `ds003171 (anesthesia fMRI)`: non-EEG anesthesia fMRI dataset; does not provide an independent EEG cohort.

## Conditional recommendation

No candidate supports same-mechanism replication of `ds005620`. `ds003969` and `ds008836` are the only candidates that could later support a preregistered construct-generalization test, and only after:

1. License confirmation from `dataset_description.json` and the live catalog, with the `ds005620` CC0 versus CC-BY-4.0 conflict resolved before any reference transfer.
2. Bounded access with explicit network permission. No full-dataset exception.
3. Preregistration of subject-held-out, session-held-out, and forward-time splits, null models, and multiplicity.
4. Montage and sampling harmonization, or an explicit incomparability statement.
5. Catalog n is not treated as analyzed n. Exclusion flags are not an exclusion manifest.

HOLD / SYNTHETIC_ONLY. Feasibility is not empirical evidence.
