# Batch 3 — cross-dataset replication feasibility

Access date: 2026-10-16. Package owner: Grok Chat B.
Status: research feasibility only. Not empirical evidence.
No participant data were downloaded or analyzed. No signal files were opened.
Inspection levels used: listed in a catalog, metadata inspected, files locally available, analysis performed.
Every candidate in this package is at catalog or metadata level only. None are locally available or analyzed.

A successful feasibility note does not validate a theory and does not emit scientific PASS.

## Replication question

Can EEG descriptors previously explored on propofol-sedation EEG (OpenNeuro `ds005620`) generalize to an independent cohort with different hardware, montage, task, or acquisition protocol?

Prediction is not causation. Method feasibility is not consciousness evidence. Dataset availability is not permission to redistribute or to claim an empirical result.

## Ranking criteria

Independent cohort from `ds005620`; EEG or MEG; open license with explicit terms; BIDS or documented sidecars; condition or behavioral labels relevant to altered awareness; sample size adequate for a held-out split; hardware or montage diversity; autonomic or behavioral covariates present.

Popularity in MOABB, OpenNeuro, or NEMAR is not a selection criterion.

## Ranked candidates

1. **ds003969 — Meditation vs thinking task.** Independent meditation EEG with an active-thinking control and tradition groups. OpenNeuro catalog states 98 participants, 1 session, CC0, DOI `10.18112/openneuro.ds003969.v1.0.0`. A public comment reports a different group breakdown and cites earlier studies of about 100 subjects. Conflict flagged, not resolved. Sampling rate not stated on the inspected page. Source: https://openneuro.org/datasets/ds003969/versions/1.0.0

2. **ds008836 — Vipassana meditative depth.** Catalog snippet states 39 participants, 2 sessions, 64-channel EEG plus ECG, respiration, EMG, and electrodermal activity, with repeated self-reports of meditative depth. License and DOI were not extracted. Companion article described as not yet published. Ranked second only after a license check. Source: https://openneuro.org/datasets/ds008836/versions/1.0.1

3. **ds001787 — EEG meditation study.** README and catalog state 24 subjects; catalog states 3 sessions; CC0; DOI `10.18112/openneuro.ds001787.v1.1.1`. Originally 2048 Hz, downsampled to 256 Hz (Biosemi). Mind-wandering probes about every 2 minutes. Small for a held-out replication. Source: https://openneuro.org/datasets/ds001787/versions/1.1.1

4. **ds004572 — Sham hypnosis techniques.** Catalog and README state 52 participants, 64-channel EasyCap (Brain Products), 2x2 induction/framing design, CC0. Version pages inspected listed both v1.3.1 and v1.3.2; DOI pinned to the v1.3.1 metadata page. Useful for construct generalization, not for a same-mechanism claim. Source: https://openneuro.org/datasets/ds004572

## Reference, not a replication

**ds005620** is the project's propofol repeated-awakening EEG reference. `dataset_description.json` states CC0 and DOI `10.18112/openneuro.ds005620.v1.0.0`. One inspected sidecar (`sub-1010` awake EC) states 5000 Hz, 65 channels, Brain Products, reference n/a. EEGDash catalog states 21 subjects and mixed 64/65 channel counts. `participants.tsv` has `excluded` and `bad_after_preprocessing` columns; included n after those flags was not resolved here. It cannot replicate itself.

## Deferred or excluded

- **ds004541** — anesthesia EEG-fNIRS, 8 participants, variable channel counts (EEGDash: 59/40/30/38). Too small. https://openneuro.org/datasets/ds004541/versions/1.0.0
- **ds005555** — sleep PSG plus wearable. Catalog states 128 participants; README states 128 nights from 100 participants. Sleep is a different construct. License not confirmed. https://openneuro.org/datasets/ds005555/versions/1.0.0
- **ds003171** — anesthesia fMRI, 17 participants. Not EEG/MEG. Excluded. https://openneuro.org/datasets/ds003171/versions/1.0.0

MEG archives such as OMEGA were not metadata-inspected in this package and are not ranked.

## What would prevent a valid replication

Missing or conflicting participant counts; unconfirmed license; unknown sampling rate or montage; no locked subject-held-out and forward-time split; volume conduction untreated; respiration or heart rate not partialled when present; synthetic or proxy results labeled empirical; missing subjects zero-filled; any scientific PASS from this package.

## Not an EEG source

`maziyarpanahi/openmed` is a local-first clinical NER / PII de-identification project (https://github.com/maziyarpanahi/openmed). It is not an EEG/MEG archive and is not recommended as a runtime dependency for this question.

## Machine-readable matrix

`reports/batch3/grok_chat_b/dataset_candidates.json`

## Statement

No participant data were downloaded or analyzed. All recommendations remain conditional on access, license, and metadata checks.
