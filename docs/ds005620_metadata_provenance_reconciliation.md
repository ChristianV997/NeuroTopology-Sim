# DS005620 metadata and provenance reconciliation

**Snapshot/access date:** 2026-10-16
**Scope:** metadata and file-list metadata only. No participant EEG/recording files were downloaded, opened, or analyzed. The checked-in `participants.tsv` fixture is a projection of the source table containing only `participant_id` and `excluded`; age, sex, awakening, TMS, and preprocessing-detail columns were not copied.

## Reconciliation outcome

| Dimension | Result | Basis |
|---|---|---|
| Metadata parsed | Yes for the sanitized snapshot fixture | `participants.tsv`, `dataset_description.json`, `README.txt`, `nemar_metadata.json`, and `published_counts.json` parse. |
| Participant IDs | 21 exact IDs in `participants.tsv`; `sub-SD_1037` is explicitly marked `excluded=True` there.[3] | The flag is reported as a source fact only; it is not treated as proof that this is the participant absent from the paper's analyzed cohort. |
| BIDS subject count | 21 | `participants.tsv` contains 21 IDs; NEMAR's metadata API reports `subject_count: 21`.[1][3] |
| Participant-count claim | Proposal: 20 analyzed; paper: recordings in 20 healthy participants | The values align numerically, but the paper's wording does not establish that the proposal's analyzed cohort is the same set; no analyzed-subject ID list/crosswalk was supplied.[7] |
| Awakening-count claim | Proposal: 52 trials; paper: 52 attempted awakenings | The paper reports attempted awakenings, not retained trials or an inventory file count.[7] |
| Cohort reconciled | **No** | Count difference is 1, and no source-derived mapping from the proposal's 20-person analyzed-cohort claim to the BIDS IDs was supplied. Neither the count difference nor the TSV exclusion flag is used to assign the cohort or an exclusion reason. |
| License resolved | **No** | `README.md` says `CC-BY-4.0`.[5] `dataset_description.json` and NEMAR metadata say `CC0`.[1][2][4] Keep the conflict unresolved. |
| File inventory complete against declared requirements | **Not evaluated** | No supplied task/session/run inventory or authoritative preregistered requirement set was present. NEMAR's task labels are descriptive only.[1][2] |
| Expected task set | **Unresolved / null** | No authoritative preregistration with a verified, canonical, non-empty plan hash was supplied. The observed labels `awake`, `sed`, and `sed2` are descriptive only and are not promoted to requirements.[1][2] |
| Data-use ready | **No** | The license conflict is unresolved; a metadata packet is not permission to use data. |

### Identifier discrepancy in NEMAR metadata

The public `participants.tsv` contains 21 identifiers in the `sub-SD_####` form, while NEMAR's top-level directory index lists 21 `sub-####` directory labels.[3][6] An exact string comparison yields no matching identifiers. The shared numeric suffixes are not treated as an alias mapping: no authoritative crosswalk was provided. The directory index is not a complete task/session/run inventory and is not used to infer one.

## Input and interpretation contract

`tools/export_ds005620_evidence_packet.py` accepts `--metadata-root` containing metadata-only inputs:

- Required: `participants.tsv`, `dataset_description.json`, exactly one `README.txt`/`README.md`/`README`, `nemar_metadata.json`, and `published_counts.json`.
- Optional: `file_inventory.json` using the existing BIDS inventory record shape (`eeg_candidates`), and `preregistered_plan.json` using the existing `ExperimentPlan.v1` checksum convention.
- A plan's `variables.expected_task_requirements` must explicitly enumerate task labels and may constrain session, run, or subject. Its checksum must equal the repository's canonical hash of the non-empty plan with the `checksum` field omitted. The empty-byte SHA-256 (`e3b0c442…`) is rejected, including when supplied as `provenance.source_checksum`.
- A plan hash alone is not a claim that its source is authoritative: the input must also provide an HTTPS preregistration reference and `provenance.authoritative_source_verified: true`. This is an explicit operator attestation; the offline exporter does not fetch or independently authenticate that source.
- File-inventory completeness is evaluated only against those declared requirements and only for the supplied inventory. It does not certify that the supplied inventory itself exhaustively represents a remote dataset.
- Participant IDs, task labels, sessions, and runs are preserved verbatim. The exporter does not normalize subject identifiers or infer requirements from observed tasks.
- Source-specific published-count claims are preserved separately as `published_count_source_claims`; the packet does not equate the proposal's labels with the primary paper's wording.
- `metadata_parsed`, `file_inventory_complete_against_declared_requirements`, `cohort_reconciled`, `license_resolved`, and `data_use_ready` remain separate fields. `data_use_ready` is always false for this metadata audit; it cannot grant authorization.

The exporter reads only the metadata files above. It does not follow inventory paths or open EEG recordings.

All primary source pages in the Sources block were accessed on 2026-10-16. The inventory comparison used directory names only; it did not retrieve participant recording files.

## Unresolved questions

1. Which license declaration governs the dataset: the README's `CC-BY-4.0` or the `CC0` declaration in `dataset_description.json` and NEMAR?[1][4][5] Please provide an authoritative correction from the rights holder or repository maintainer. Until then, license resolution and data-use readiness remain blocked.
2. What authoritative crosswalk maps the `participants.tsv` IDs (`sub-SD_####`) to NEMAR directory labels (`sub-####`), if they represent the same participants? Exact identifiers are not interchangeable without that source.
3. Which 20 subject IDs comprise the cohort behind the proposal's analyzed-participant claim, and what source records the inclusion/exclusion decision and reason? The paper's wording of recordings in 20 healthy participants does not provide an ID mapping.[7] The `excluded=True` flag for `sub-SD_1037` is recorded separately and is not assumed to answer this question.
4. Please supply an exhaustive, versioned task/session/run file inventory, with its source and checksum. Until then, coverage and inventory completeness are not evaluated.
5. Please supply the authoritative preregistration/protocol that declares the expected task/session/run set, plus a canonical non-empty plan with a verified hash and source reference. NEMAR task labels and README filename examples are not substituted for it.
6. Does the published count of 52 refer to attempted awakening events, retained trials, or another unit for the intended analysis? The paper wording is preserved as “attempted awakenings”; no file-level trial count is inferred.[7]

## Scope statement

No participant EEG data was downloaded, opened, or analyzed. Public metadata files and the NEMAR top-level directory index were read only to reconcile metadata. This packet is not empirical evidence and does not grant permission to use the dataset.

## Sources

[1] https://api.nemar.org/datasets/on005620 — NEMAR dataset metadata API for on005620
    > "A repeated awakening study exploring the capacity of complexity measures to capture dreaming during propofol sedation"
[2] https://nemar.org/dataset/on005620 — NEMAR dataset record for on005620
    > "LICENSE CC0 MODALITIES EEG TASKS awake sed sed2"
[3] https://data.nemar.org/on005620/v1.0.0/participants.tsv — NEMAR participants.tsv metadata
    > "sub-SD_1036 False sub-SD_1037 True sub-SD_1045 False"
[4] https://data.nemar.org/on005620/v1.0.0/dataset_description.json — NEMAR dataset_description.json metadata
    > ""License": "CC0", "Affiliations": {"
[5] https://data.nemar.org/on005620/v1.0.0/README.md — NEMAR README.md metadata and license text
    > "This dataset is licensed under CC-BY-4.0."
[6] https://data.nemar.org/on005620/v1.0.0 — NEMAR top-level dataset directory index
    > "sub-1010/ - sub-1016/ - sub-1017/ -"
[7] https://www.nature.com/articles/s41598-025-12695-z — Bajwa et al., Scientific Reports (2025)
    > "in 20 healthy participants during propofol sedation"
    > "Out of the 52 attempted awakenings in this study"
