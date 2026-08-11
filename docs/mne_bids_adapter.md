# MNE/BIDS Derived Feature Adapter v1

Status: **implemented, the first real adapter.** This document describes
the `adapters/` package as it exists today. It does not describe, and
should not be read as promising, any of the capabilities listed in
[Future work](#future-work) -- those are explicitly out of scope for this
milestone.

## What it does

`adapters.mne_bids` is the bridge from a lab's own MNE/BIDS-organized
artifacts to this repository's governed schema chain:

```
MNE/BIDS-derived artifact metadata/features
        |
        v  adapters.mne_bids
DatasetRecordV1 / ArtifactRecordV1 candidate records
        |
        v
TransitionRecordV1
        |
        v  (optional --include-phase-space)
PhaseSpaceCoordinateV1
        |
        v  (optional --include-evidence-bundle)
EvidenceBundleV1
        |
        v  (optional --include-report)
EvidenceReportV1
```

It supports two independent input modes, usable separately or together:

1. **BIDS metadata scan** (`--scan-bids <bids_root>`): reads
   `dataset_description.json`, `participants.tsv`, `*_events.tsv`, and any
   `derivatives/*.json` under a local BIDS directory, plus the presence of
   standardized BIDS modality subdirectories (`eeg/`, `meg/`, `ieeg/`,
   `nirs/`), and produces a conservative `DatasetRecordV1` and one
   `ArtifactRecordV1` per metadata file found. No `TransitionRecordV1` is
   produced by this mode alone.
2. **Derived feature export** (`--features <table> --mapping <mapping.json>`):
   converts an explicit, user-provided derived feature table -- **not**
   raw signal -- into governed `TransitionRecordV1` artifacts, using an
   explicit mapping file that declares every fact the adapter would
   otherwise have to guess.

## What it does not do

- **Does not run raw EEG/MEG/iEEG/fNIRS preprocessing.** It never opens,
  filters, or reads a raw signal file (`.edf`/`.bdf`/`.fif`/`.set`/...).
  Every feature value it converts into a `TransitionRecordV1` was already
  computed by the user's own pipeline (MNE, or anything else) before this
  adapter ever sees it.
- **Does not download any dataset.** `--scan-bids` reads an
  already-present local directory; nothing is fetched over the network.
- **Does not infer `source_state`/`target_state` from column names, file
  names, or table shape.** Every state label, modality, canonical feature
  name, and feature definition must be explicit in the mapping file (see
  [Required mapping schema](#required-mapping-schema)) -- a wide table
  with columns literally named `awake_alpha_power`/`sedated_alpha_power`
  still fails closed if the mapping omits `source_state`/`target_state`
  (verified by
  `tests/test_mne_bids_adapter_export.py::test_wide_export_never_infers_state_from_column_names`).
- **Does not implement an MNE object adapter, a MOABB/EEGDash importer, or
  live BrainFlow/MNE-LSL streaming.** See
  [Future work](#future-work).
- **Does not make clinical, diagnostic, treatment, biomarker,
  consciousness-detection, or spiritual/meditative-attainment claims.**
  Every `TransitionRecordV1`/`EvidenceBundleV1` this adapter produces
  carries `claim_scope="exploratory_metric"` and the same forbidden-uses
  floor every other layer in this repository enforces.

## Why v1 consumes derived feature artifacts, not raw EEG

Running raw EEG/MEG/iEEG/fNIRS preprocessing correctly (filtering,
referencing, artifact rejection, epoching) requires real scientific
judgment calls this adapter has no way to make on a stranger's data
without guessing. This repository's own pipelines already make those
calls explicitly and document them (`data/preprocessing.py`,
`sciencer_d/btc_icft/`). Asking a lab to hand over feature values it
already computed, plus an explicit statement of what those values mean --
rather than asking this adapter to silently re-derive them -- is the only
version of this bridge that does not either (a) fabricate a preprocessing
decision on the user's behalf or (b) require this repository to trust an
opaque black box. A future v2 that ingests real MNE `Raw`/`Epochs` objects
directly is a distinct, larger scope decision -- see
[Future work](#future-work).

## Required feature-table schema

Two table shapes are supported. Both are declared by the mapping's
`"format"` field (`"long"` or `"wide"`) -- the adapter never guesses which
shape a table is from its columns alone.

### Long format (`"format": "long"`)

One row per (subject, state pair, feature). CSV or JSON (a list of row
objects, or `{"rows": [...]}`).

| column | required | notes |
|---|---|---|
| `subject_id` | yes | |
| `session_id` | no | |
| `source_state` | yes | never inferred |
| `target_state` | yes | never inferred; must differ from `source_state` |
| `modality` | no | defaults to `mapping.modality`; if given, must match it |
| `feature_name` | yes | must be a valid namespaced feature name (see below) |
| `source_value` | yes | numeric |
| `target_value` | yes | numeric |
| `feature_definition` | yes | non-empty; falls back to `mapping.feature_definitions[feature_name]` if present there instead |
| `preprocessing_provenance` | no | falls back to `mapping.preprocessing_provenance` |
| `null_control_status` | no | one of `not_provided`/`not_applicable`/`failed`/`passed`; defaults `not_provided` |
| `artifact_path` | no | source artifact this value came from |
| `dataset_id` | no | if given, must match `mapping.dataset_id` |

### Wide format (`"format": "wide"`)

One row per subject; the mapping's `"features"` list is the *only* thing
that ever associates a column with a canonical feature -- this adapter
never parses a column name.

| column | required | notes |
|---|---|---|
| `subject_id` (or `mapping.subject_id_column`) | yes | |
| one source + one target column per feature in `mapping.features` | yes | e.g. `awake_alpha_power`/`sedated_alpha_power` |

### Feature names

Every `feature_name`/`canonical_name` must be a valid namespaced name
under `transitions.features.ALLOWED_NAMESPACES` (`spectral`, `topology`,
`connectivity`, `dynamics`, `complexity`, `qc`, `transition`,
`phenomenology`, `phase_space`, `experimental`) -- e.g.
`spectral.alpha_power`, `connectivity.mean_plv`. A namespace outside that
set, or a name containing a forbidden token (`diagnos`, `treatment`,
`biomarker`, `clinical`, `consciousness_detect`, `jhana`, `cessation`,
`enlightenment`, `spiritual_attainment`, ...), fails closed.

## Required mapping schema

```json
{
  "format": "long",
  "dataset_id": "my_lab_study_001",
  "modality": "EEG",
  "preprocessing_provenance": {
    "pipeline": "MNE 1.x: 1-40Hz bandpass, 60Hz notch, common-average reference",
    "source_tool_version": "mne==1.7.0"
  },
  "null_control_status": "not_provided"
}
```

```json
{
  "format": "wide",
  "dataset_id": "my_lab_study_002",
  "modality": "EEG",
  "source_state": "awake",
  "target_state": "sedated",
  "feature_definitions": {
    "spectral.alpha_power": "Welch PSD alpha band (8-12Hz) mean power",
    "connectivity.mean_plv": "Mean pairwise PLV across a 19-channel montage"
  },
  "features": [
    {"canonical_name": "spectral.alpha_power", "source_column": "awake_alpha_power", "target_column": "sedated_alpha_power"},
    {"canonical_name": "connectivity.mean_plv", "source_column": "awake_connectivity_mean", "target_column": "sedated_connectivity_mean"}
  ],
  "subject_id_column": "subject_id",
  "preprocessing_provenance": {"pipeline": "MNE 1.x", "source_tool_version": "mne==1.7.0"}
}
```

Required regardless of format: `format`, `dataset_id`, `modality` (one of
`EEG`/`MEG`/`iEEG`/`fNIRS`), `preprocessing_provenance` (non-empty
object). `format="wide"` additionally requires `source_state`,
`target_state`, `feature_definitions`, and `features`. All free text is
scanned against this repository's shared banned-phrase list
(`phase_space.coordinate.scan_banned_phrases`) plus one small additive
list specific to unsafe tool-integration language
(`adapters.validation` reuses `external_tools.validation`'s
`EXTERNAL_TOOL_EXTRA_BANNED_PHRASES` pattern for its own scraping/
reverse-engineering phrase checks where relevant).

## BIDS metadata scan behavior

`scan_bids_metadata(bids_root)` reads, and only reads: `dataset_description.json`
(for the dataset's declared `Name`), `participants.tsv` (row count and
content), every `*_events.tsv` found anywhere under the root, every JSON
file under `derivatives/`, and the presence (not content) of
`eeg/`/`meg/`/`ieeg/`/`nirs/` subdirectories (standard BIDS modality
folder names -- reading them is reading a formal specification's
directory structure, not inferring anything). `dataset_id` is a
deterministic slug of the declared `Name`, or of the root directory's own
name if no `dataset_description.json` is present.

`make_dataset_record_from_bids(summary, mapping_provided=False)` always
returns `current_role="exploration"`, `contamination_status="unseen"`,
never a `validation_lock`. `allowed_uses` is `["documentation",
"feature_design"]`, plus `"transition_export"` only when
`mapping_provided=True` (i.e., an explicit mapping accompanied the scan).
`evidence_level_ceiling` is `L0_computational_artifact` for a
metadata-only scan (nothing was computed) or `L2_single_subject_real_signal`
when a mapping was also provided. `make_artifact_records_from_bids(summary)`
returns one `ArtifactRecordV1` per metadata file found, always
`external=True` (the scanned directory is the user's own, not part of
this repository).

## Registry behavior

`export_mne_bids_derived_transitions` checks the loaded
`benchmarks.export_registry.BenchmarkRegistry` before writing anything:

- If `dataset_id` already has a `DatasetRecordV1` in the registry, its
  existing `allowed_uses`/`forbidden_uses`/role govern this run exactly
  as they would for any other exporter.
- If `dataset_id` has **no** existing entry, a conservative candidate
  `DatasetRecordV1` is synthesized in memory (`current_role="exploration"`,
  `allowed_uses=["documentation", "feature_design", "transition_export"]`,
  plus `"phase_space_export"` only if `--include-phase-space` was
  requested for this run) -- never marked validation-ready, never
  authorized for a confirmatory claim
  (`final_claim_confirmation`/`cross_dataset_replication_claim`/
  `prospective_prediction_claim` all remain in `forbidden_uses`).
- The registry file at `--registry` is **never mutated in place**. If a
  new candidate was synthesized and downstream phase-space/evidence-bundle
  work was also requested, `--updated-registry-out` is **required** (the
  adapter fails closed rather than silently reusing the un-updated
  original registry for that downstream step) -- the merged registry is
  written only to that path.
- `--requested-use` (default `transition_export`) is checked the same way
  every other exporter in this repository checks it
  (`benchmarks.split_policy`); a denied use raises before any
  `TransitionRecordV1` is written.

## Claim/evidence policy

- `claim_scope` is always `"exploratory_metric"`.
- `evidence_level` is always `"L2_single_subject_real_signal"` -- this
  adapter only ever emits `record_level="subject"` records from
  explicitly-provided real subject-level derived values; it never computes
  or claims a cohort-level (`L3`/`L4`) effect.
- `null_control_summary.status` defaults to `"not_provided"`; it becomes
  anything else only when the feature table (or mapping) explicitly
  declares `null_control_status`, and every row in a transition group must
  agree (an inconsistent group is rejected, not silently resolved).
- No clinical, diagnostic, treatment, biomarker, consciousness-detection,
  or spiritual/meditative-attainment claim is ever produced --
  `forbidden_uses` on every generated `DatasetRecordV1` and the fixed
  `AdapterContractV1.forbidden_outputs` floor both enforce this
  structurally, not just by convention.

## CLI usage

```bash
# BIDS metadata scan only
python -m adapters.mne_bids --scan-bids /path/to/my_lab_bids_study \
    --write-dataset-records outputs/adapters/mne_bids/my_study_scan.json

# derived-feature export -> TransitionRecordV1 only
python -m adapters.mne_bids \
    --features derived_features.csv --mapping mapping.json \
    --out outputs/adapters/mne_bids/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/mne_bids/my_export/registry_updated.json

# full chain: TransitionRecordV1 -> PhaseSpaceCoordinateV1 -> EvidenceBundleV1 -> EvidenceReportV1
python -m adapters.mne_bids \
    --features derived_features.csv --mapping mapping.json \
    --out outputs/adapters/mne_bids/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/mne_bids/my_export/registry_updated.json \
    --include-phase-space --include-evidence-bundle --include-report
```

The CLI always prints a JSON summary: dataset_id, groups parsed,
transitions written, skipped-row/error counts (up to 20 shown), the
output directory, registry decisions, whether a new dataset record was
auto-registered, and (when requested) phase-space/evidence-bundle/report
results. `--include-report` without `--include-evidence-bundle` is
explicitly reported as `"not built (requires --include-evidence-bundle)"`
rather than silently doing nothing.

## Optional phase-space/evidence/report path

All three are implemented (not a future-work placeholder):

- `--include-phase-space` runs the existing
  `phase_space.export_from_transitions.export()` unchanged, writing
  `PhaseSpaceCoordinateV1` records under `<out>/phase_space/`. Axes whose
  source features are absent from a given transition are `insufficient_data`
  (never a guessed number), exactly as for every other exporter.
- `--include-evidence-bundle` calls a new, clean, additive function,
  `evidence.builder.build_generic_evidence_bundle()`, which builds an
  `EvidenceBundleV1` by reading whatever `TransitionRecordV1` artifacts
  this adapter already wrote -- it calls no dataset-specific exporter
  itself, so it works for a `dataset_id` that is not, and need not be,
  registered in `evidence.builder.DISPATCH` (the fixed lookup table the
  original `build_evidence_bundle` uses for ds005620/ds000245). This
  function's own signature/behavior, and `DISPATCH`, are unchanged by its
  addition -- see `evidence/builder.py`.
- `--include-report` (only meaningful together with
  `--include-evidence-bundle`) generates an `EvidenceReportV1`
  Markdown+JSON exactly as `evidence.builder.build_evidence_bundle`'s own
  `--include-report` does, via the same `reports.evidence_report.build_report`.

## Adapter contract / external-tool registration

`adapters.mne_bids_contract.check_adapter_eligible()` runs before any
scan or export work: it confirms `mne-bids`'s `ExternalToolRecordV1`
(`external_tools/registry_seed.json`) is not `reference_only`/`avoid_core`
and is not license-blocked, and that a matching, structurally valid
`AdapterContractV1` exists. That contract lives in a **separate** file,
`external_tools/adapter_contracts_seed.json` (schema
`NeuroTopologySim.AdapterContractRegistry.v1`), loaded via
`external_tools.adapter_contract.load_adapter_contracts()` -- deliberately
not merged into the already-committed, already-tested
`external_tools/registry_seed.json`, so adding an adapter contract never
required touching that file's content or `external_tools/registry.py`'s
tested `ExternalToolRegistry` class. The contract's `integration_mode` is
`"adapter_only"`: this adapter has zero hard runtime dependency on `mne`
or `mne_bids` (pure Python standard library -- `json`/`csv` -- throughout);
those packages remain optional, already-permissive (`BSD-3-Clause`)
dependencies for a future v2 that reads real MNE objects directly.

## Limitations

- Consumes lightweight BIDS metadata and explicit user-provided derived
  feature tables only -- does not read raw signal files and does not run
  MNE preprocessing.
- Requires an explicit, human-authored mapping; never infers state labels,
  modality, or feature identity from column names or file paths.
- Emits subject-level records only; no cohort-level (`L3`/`L4`) claim is
  ever produced by this adapter.
- The registry-candidate auto-registration is in-memory unless
  `--updated-registry-out` is given -- without it, a repeat run against
  the same never-before-seen `dataset_id` re-synthesizes the same
  candidate from scratch rather than reusing a persisted one.
- `evidence.builder.build_generic_evidence_bundle()`'s optional
  `artifact_kind` parameter (for artifact-level, not just dataset-level,
  registry gating) is not exercised by this adapter in v1 -- only the
  dataset-level registry decision is checked for artifacts this adapter
  itself produces.
- Does not independently verify the correctness of a supplied feature
  value; it trusts the mapping author's provenance and definitions as
  given, same as any other externally-sourced artifact this repository
  ingests.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Direct MNE object ingestion.** A v2 adapter that accepts a real MNE
  `Raw`/`Epochs` object (or reads a raw signal file itself via `mne`) and
  computes features internally, rather than trusting a user-supplied
  table -- a materially larger scope decision (this repository's own
  preprocessing choices would need to be made explicit and owned, not
  merely trusted from an external source).
- **MOABB/EEGDash dataset importers.** `external_tools/registry_seed.json`
  already classifies both as `P0`/`metadata_import` candidates (see
  `docs/external_tool_integration_strategy.md`); no importer exists yet.
- **Real-time BrainFlow/MNE-LSL streaming.** Explicitly out of scope for
  this milestone and the mission that produced it.
- **PyBIDS-backed BIDS layout parsing.** v1's `scan_bids_metadata` reads
  three specific file types directly with the standard library; a fuller
  BIDS layout traversal (arbitrary derivatives structure, sidecar JSON
  inheritance) would more naturally use PyBIDS (already `P0`/permissive in
  the external tool registry) once justified by real demand.
