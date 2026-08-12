# fMRIPrep/Nilearn Derived fMRI Adapter v1

Status: **implemented, the second real adapter** (after
`adapters.mne_bids`, see `docs/mne_bids_adapter.md`). This document
describes the `adapters.fmri_derivatives` module as it exists today. It
does not describe, and should not be read as promising, any of the
capabilities listed in [Future work](#future-work) -- those are
explicitly out of scope for this milestone.

`adapters.fmri_derivatives_feature_recipe` (see
`docs/fmri_derivatives_feature_recipe.md`) fills the remaining gap: it
computes an explicit, bounded `derived_features.csv`/`mapping.json` pair
from a local timeseries-table/connectivity-matrix/graph-summary fixture,
then calls this adapter's own `export_fmri_derivative_transitions`
unmodified (optional CLI flag `--run-fmri-derivatives-adapter`) -- this
adapter's own eligibility checks, mapping validation, and registry
discipline all apply unchanged to that caller too.

## What it does

`adapters.fmri_derivatives` is the bridge from an fMRI lab's own
fMRIPrep/Nilearn-organized artifacts to this repository's governed schema
chain:

```
fMRIPrep/Nilearn-derived artifact metadata/features
        |
        v  adapters.fmri_derivatives
DatasetRecordV1 / ArtifactRecordV1 candidate records
        |
        v
TransitionRecordV1 (subject-level, or cohort-level with explicit stats)
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

It supports four independent input modes:

1. **fMRIPrep-style metadata scan** (`--scan-derivatives <derivatives_root>`):
   reads `dataset_description.json`, `participants.tsv`,
   `derivatives/fmriprep/dataset_description.json`,
   `*_desc-confounds_timeseries.tsv` files, and derivative JSON sidecars,
   plus explicit BIDS filename entities (`sub-`, `task-`, `run-`, ...)
   and the presence of `func/` directories. Produces a conservative
   `DatasetRecordV1` and one `ArtifactRecordV1` per metadata file found.
   No `TransitionRecordV1` is produced by this mode alone.
2. **Long-format derived feature table** (`--features table.csv --mapping mapping.json`):
   one row per (subject, session, source_state, target_state, feature),
   with `atlas_or_parcellation` required per row for connectivity/topology
   features.
3. **Wide-format derived feature table**: one row per subject with paired
   `<state>_<feature>` columns, plus an explicit mapping declaring
   pairing semantics, atlas/parcellation, and feature definitions.
4. **Connectivity/graph-summary JSON** (`--features graph_summary.json`,
   no separate `--mapping` needed): a single, self-contained JSON document
   carrying dataset/atlas/state metadata plus subject-level paired metrics
   and/or explicit cohort-level statistics.

## What it does not do

- **Does not run raw BOLD preprocessing, execute fMRIPrep, or fit any
  Nilearn model.** It never opens a NIfTI file. Every feature value it
  converts into a `TransitionRecordV1` was already computed by the user's
  own pipeline (fMRIPrep + Nilearn, or anything else) before this adapter
  ever sees it.
- **Does not download any dataset.** `--scan-derivatives` reads an
  already-present local directory; nothing is fetched over the network.
- **Does not infer `source_state`/`target_state`, atlas identity, or
  feature identity from column names, file names, or parcel counts.**
  Every state label, atlas/parcellation name, canonical feature name, and
  feature definition must be explicit in the mapping (or self-contained
  graph-summary document) -- a wide table with columns literally named
  `placebo_global_efficiency`/`drug_global_efficiency` still fails closed
  if the mapping omits `source_state`/`target_state`
  (`tests/test_fmri_derivatives_adapter_export.py::test_wide_export_never_infers_state_from_column_names`).
- **Does not treat a parcellation label as validated anatomy.**
  `atlas_or_parcellation` is stored verbatim as provided (e.g.
  `"Schaefer100"`); every generated `TransitionRecordV1`'s `limitations`
  explicitly states this is not independently verified as anatomically
  accurate.
- **Does not compute cohort statistics.** A cohort-level
  (`record_level="cohort"`) `TransitionRecordV1` is only ever produced
  from an explicit, already-computed `cohort.subject_count>=2` and
  `cohort.metrics` in a graph-summary document -- this adapter never
  aggregates subject-level rows into a cohort statistic itself.
- **Does not treat a parametric p-value as a null-control pass.** A
  `cohort.metrics` entry's `p_value`/`statistic` fields (if present) are
  carried through as-is in the source data but never used to set
  `null_control_summary.status` -- that field is set only from an
  explicit `null_control_status` key, defaulting to `"not_provided"`
  (`tests/test_fmri_derivatives_adapter_export.py::test_graph_summary_parametric_p_value_alone_is_not_null_control_pass`).
- **Does not implement a direct MNE `Raw`/`Epochs` adapter, a
  MOABB/EEGDash importer, or live BrainFlow/MNE-LSL streaming.** See
  [Future work](#future-work).
- **Does not make clinical, diagnostic, treatment, biomarker,
  consciousness-detection, or spiritual/meditative-attainment claims.**
  Every `TransitionRecordV1`/`EvidenceBundleV1` this adapter produces
  carries `claim_scope="exploratory_metric"` and the same forbidden-uses
  floor every other layer in this repository enforces.

## Why v1 consumes derived features rather than raw BOLD

Running fMRIPrep and fitting a Nilearn connectivity/graph model correctly
requires real scientific judgment calls (motion-correction strategy,
confound regression set, band-pass filtering, atlas choice, connectivity
estimator) this adapter has no way to make on a stranger's data without
guessing. Asking a lab to hand over feature values it already computed,
plus an explicit statement of what those values mean and how they were
produced, is the only version of this bridge that does not either (a)
fabricate a preprocessing decision on the user's behalf or (b) require
this repository to trust an opaque black box. This mirrors
`adapters.mne_bids`'s identical design choice for EEG/MEG/iEEG/fNIRS --
see `docs/mne_bids_adapter.md`'s "Why v1 consumes derived feature
artifacts, not raw EEG" section for the parallel reasoning.

## Required feature-table schema

### Long format (`"format": "long"`)

One row per (subject, state pair, feature). CSV or JSON.

| column | required | notes |
|---|---|---|
| `subject_id` | yes | |
| `session_id` | no | |
| `source_state` | yes | never inferred |
| `target_state` | yes | never inferred; must differ from `source_state` |
| `modality` | no | defaults to `mapping.modality` (always `"fMRI"`); if given, must match |
| `feature_name` | yes | must be a valid namespaced feature name |
| `source_value` | yes | numeric |
| `target_value` | yes | numeric |
| `feature_definition` | yes | non-empty; falls back to `mapping.feature_definitions[feature_name]` if present |
| `atlas_or_parcellation` | conditional | **required** whenever `feature_name` is a `connectivity.*`/`topology.*` (graph) feature; falls back to `mapping.atlas_or_parcellation` |
| `preprocessing_provenance` | no | falls back to `mapping.preprocessing_provenance` |
| `confound_policy` | no | falls back to `mapping.confound_policy` |
| `null_control_status` | no | one of `not_provided`/`not_applicable`/`failed`/`passed`; defaults `not_provided` |
| `artifact_path` | no | source artifact this value came from |
| `dataset_id` | no | if given, must match `mapping.dataset_id` |

### Wide format (`"format": "wide"`)

One row per subject; `mapping.features` is the only thing that ever
associates a column with a canonical feature.

| column | required | notes |
|---|---|---|
| `subject_id` (or `mapping.subject_id_column`) | yes | |
| one source + one target column per feature in `mapping.features` | yes | e.g. `placebo_global_efficiency`/`drug_global_efficiency` |

### Connectivity/graph-summary JSON (`"format": "graph_summary"`)

A single, self-contained document -- see [Example: graph-summary
JSON](#example-graph-summary-json) below. `subjects` (list) and/or
`cohort` (object) may both be present; at least one is required.

## Required mapping schema

```json
{
  "format": "long",
  "dataset_id": "my_lab_fmri_study_001",
  "modality": "fMRI",
  "preprocessing_provenance": {
    "pipeline": "fMRIPrep 23.1.0 + Nilearn ConnectivityMeasure (correlation)",
    "source_tool_version": "fmriprep==23.1.0"
  },
  "confound_policy": "24-param + aCompCor (5 components), high-pass 0.01Hz",
  "null_control_status": "not_provided"
}
```

```json
{
  "format": "wide",
  "dataset_id": "my_lab_fmri_study_002",
  "modality": "fMRI",
  "source_state": "placebo",
  "target_state": "drug",
  "atlas_or_parcellation": "Schaefer100",
  "feature_definitions": {
    "connectivity.global_efficiency": "Graph global efficiency over a Schaefer-100 correlation connectome",
    "connectivity.modularity": "Louvain modularity Q"
  },
  "features": [
    {"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_global_efficiency", "target_column": "drug_global_efficiency"},
    {"canonical_name": "connectivity.modularity", "source_column": "placebo_modularity", "target_column": "drug_modularity"}
  ],
  "subject_id_column": "subject_id",
  "preprocessing_provenance": {"pipeline": "fMRIPrep 23.1.0 + Nilearn", "source_tool_version": "fmriprep==23.1.0"},
  "confound_policy": "24-param + aCompCor"
}
```

Required regardless of format: `format`, `dataset_id`, `modality` (must
be exactly `"fMRI"`), `preprocessing_provenance` (non-empty object),
`confound_policy` (non-empty string -- an fMRI feature table with no
stated confound-regression policy is exactly the kind of ambiguity this
adapter fails closed on). `format="wide"`/`"graph_summary"` additionally
require `source_state`, `target_state`, `feature_definitions`, and
(whenever any declared feature is a `connectivity.*`/`topology.*` graph
feature) `atlas_or_parcellation`.

### Example: graph-summary JSON

```json
{
  "format": "graph_summary",
  "dataset_id": "my_lab_fmri_study_003",
  "modality": "fMRI",
  "atlas_or_parcellation": "Schaefer100",
  "source_state": "placebo",
  "target_state": "drug",
  "preprocessing_provenance": {"pipeline": "fMRIPrep 23.1.0 + Nilearn", "source_tool_version": "fmriprep==23.1.0"},
  "confound_policy": "24-param + aCompCor",
  "feature_definitions": {
    "connectivity.global_efficiency": "Graph global efficiency over a Schaefer-100 correlation connectome",
    "connectivity.modularity": "Louvain modularity Q"
  },
  "null_control_status": "not_provided",
  "subjects": [
    {"subject_id": "sub-01", "metrics": {
      "connectivity.global_efficiency": {"source_value": 0.34, "target_value": 0.29},
      "connectivity.modularity": {"source_value": 0.31, "target_value": 0.40}
    }}
  ],
  "cohort": {
    "subject_count": 20,
    "metrics": {
      "connectivity.global_efficiency": {"source_value": 0.33, "target_value": 0.30, "statistic": "paired_t", "p_value": 0.01}
    }
  }
}
```

`cohort` is entirely optional; when present, it must carry an explicit
integer `subject_count >= 2` and non-empty `metrics` -- the adapter fails
closed on a `cohort` block missing either.

## Feature namespaces

Recommended canonical names, all of which are already valid under
`transitions.features.ALLOWED_NAMESPACES` without any change to that
module (its namespace-level validation already accepts any well-formed
`namespace.local_name` under an allowed namespace, not just the starter
`CANONICAL_FEATURES` list -- see `transitions/features.py`):

- **Connectivity** (atlas/parcellation required): `connectivity.global_efficiency`,
  `connectivity.modularity`, `connectivity.degree`,
  `connectivity.small_worldness`
- **Topology** (atlas/parcellation required): `topology.fmri_graph_betti0`,
  `topology.fmri_graph_betti1`, `topology.fmri_graph_total_persistence_h1`,
  `topology.persistence_landscape_area`, `topology.bottleneck_distance`
  (only if genuinely computed as such)
- **Complexity/dynamics** (no atlas required unless a parcellation was
  actually used to compute it): `complexity.entropy`, `dynamics.metastability`
- **QC** (no atlas required): `qc.mean_fd`, `qc.motion_outlier_fraction`,
  `qc.valid_timepoints`

No new namespace or canonical-name entry was added to
`transitions/features.py` for this milestone -- every name above already
passes that module's existing namespace-based validation. A feature name
containing a forbidden token (`diagnos`, `clinical`, `biomarker`,
`consciousness_detect`, ...) is rejected regardless of namespace,
unchanged from every other layer in this repository.

Never call a Pearson-correlation graph metric "PLV" (that is an
EEG/MEG phase-locking-specific term); never assign an anatomical label
to an anonymous parcel; never convert a confound value (e.g.
framewise displacement) into a scientific state feature unless the
mapping explicitly marks it as a `qc.*` feature.

## Metadata scan behavior

`scan_fmri_derivatives_metadata(derivatives_root)` reads, and only reads:
`dataset_description.json`, `derivatives/fmriprep/dataset_description.json`
(if present), `participants.tsv`, every `*_desc-confounds_timeseries.tsv`
found anywhere under the root (plus their explicit BIDS filename
entities -- `sub-`, `task-`, `run-`, parsed via a standard key-value
grammar, not inferred), every other JSON sidecar file, and the presence
(not content) of `func/` directories. `dataset_id` is a deterministic
slug of the declared `Name`, or of the root directory's own name if no
`dataset_description.json` is present.

`make_dataset_record_from_fmri_derivatives(summary, mapping_provided=False)`
always returns `current_role="exploration"`, `contamination_status="unseen"`,
never a `validation_lock`. `allowed_uses` is `["documentation",
"feature_design"]`, plus `"transition_export"` only when
`mapping_provided=True`. `evidence_level_ceiling` is
`L0_computational_artifact` for a metadata-only scan, or
`L4_cross_subject_dataset_specific` when a mapping was also provided (the
widest ceiling this adapter can legitimately produce, covering both
subject- and cohort-level output). `make_artifact_records_from_fmri_derivatives(summary)`
returns one `ArtifactRecordV1` per metadata file found, always
`external=True`.

## Atlas/parcellation handling

`atlas_or_parcellation` is required (structurally enforced, fails closed)
whenever any `connectivity.*`/`topology.*` feature is involved -- at the
mapping level for `wide`/`graph_summary` formats (checked up front, since
every feature is declared in the mapping itself), and per-row for `long`
format (checked during cross-validation, since rows carry their own
feature names). It is stored verbatim in
`TransitionRecordV1.metadata["atlas_or_parcellation"]` and grouped into
the transition-grouping key (two rows for the same subject/state-pair but
different atlases become two separate `TransitionRecordV1`s, never
merged). Non-graph features (`complexity.*`, `dynamics.*`, `qc.*`) do not
require an atlas.

## Confound/QC handling

`confound_policy` is always required in the mapping (or graph-summary
document) -- a non-empty, free-text description of the confound-regression
strategy (e.g. `"24-param + aCompCor, high-pass 0.01Hz"`). It is folded
into each generated `TransitionRecordV1.preprocessing_provenance` under
its own `confound_policy` key, alongside the `preprocessing_provenance`
object's other fields -- never silently dropped, never treated as a
scientific feature itself. A confound value (e.g. mean framewise
displacement) only becomes a `TransitionRecordV1` feature at all if the
mapping author explicitly declares it as a `qc.*`-namespaced feature with
its own definition, exactly like any other feature.

## Registry behavior

Identical to `adapters.mne_bids`'s registry behavior (see
`docs/mne_bids_adapter.md`'s "Registry behavior" section) -- an
unregistered `dataset_id` gets a conservative, in-memory candidate
`DatasetRecordV1` (never persisted to the `--registry` file itself,
never authorized for a confirmatory claim); `--updated-registry-out` is
required whenever a new candidate was created and downstream phase-space/
evidence-bundle work is also requested (the adapter fails closed rather
than silently reusing an out-of-date registry for that downstream step).

## Claim/evidence policy

- `claim_scope` is always `"exploratory_metric"` -- subject-level and
  cohort-level records alike.
- Subject-level (`record_level="subject"`) records use
  `evidence_level="L2_single_subject_real_signal"`.
- Cohort-level (`record_level="cohort"`) records use
  `evidence_level="L4_cross_subject_dataset_specific"`, and are only ever
  produced from an explicit graph-summary `cohort.subject_count>=2` +
  `cohort.metrics` -- never computed by this adapter.
- `null_control_summary.status` defaults `"not_provided"`; a parametric
  p-value alone never sets it to `"passed"` (see above). Every row/entry
  in a group must agree on `null_control_status`, or the group is
  rejected rather than silently resolved.
- No clinical, diagnostic, treatment, biomarker, consciousness-detection,
  or spiritual/meditative-attainment claim is ever produced.

## CLI usage

```bash
# fMRIPrep-style metadata scan only
python -m adapters.fmri_derivatives --scan-derivatives /path/to/my_lab_derivatives \
    --write-dataset-records outputs/adapters/fmri_derivatives/my_study_scan.json

# derived-feature export -> TransitionRecordV1 only
python -m adapters.fmri_derivatives \
    --features derived_features.csv --mapping mapping.json \
    --out outputs/adapters/fmri_derivatives/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/fmri_derivatives/my_export/registry_updated.json

# self-contained connectivity/graph-summary JSON (no separate --mapping)
python -m adapters.fmri_derivatives \
    --features graph_summary.json \
    --out outputs/adapters/fmri_derivatives/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/fmri_derivatives/my_export/registry_updated.json

# full chain: TransitionRecordV1 -> PhaseSpaceCoordinateV1 -> EvidenceBundleV1 -> EvidenceReportV1
python -m adapters.fmri_derivatives \
    --features derived_features.csv --mapping mapping.json \
    --out outputs/adapters/fmri_derivatives/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/fmri_derivatives/my_export/registry_updated.json \
    --include-phase-space --include-evidence-bundle --include-report
```

The CLI always prints a JSON summary: dataset_id, groups parsed,
subject-level transitions written, cohort records written, skipped-row/
error counts (up to 20 shown), the output directory, registry decisions,
whether a new dataset record was auto-registered, the distinct
atlas/parcellation values observed, a total limitations count, and (when
requested) phase-space/evidence-bundle/report results.
`--include-report` without `--include-evidence-bundle` is explicitly
reported as `"not built (requires --include-evidence-bundle)"` rather
than silently doing nothing.

## Optional phase-space/evidence/report path

Implemented identically to `adapters.mne_bids`'s own optional path (see
`docs/mne_bids_adapter.md`'s "Optional phase-space/evidence/report path"
section) -- `--include-phase-space` calls
`phase_space.export_from_transitions.export()` unchanged;
`--include-evidence-bundle` calls the same additive
`evidence.builder.build_generic_evidence_bundle()` introduced by the
MNE/BIDS adapter milestone (PR #191), which reads whatever
`TransitionRecordV1` artifacts this adapter already wrote and requires no
`evidence.builder.DISPATCH` entry for a lab's own `dataset_id`;
`--include-report` (only meaningful together with
`--include-evidence-bundle`) generates the same `EvidenceReportV1`
Markdown+JSON via `reports.evidence_report.build_report`.

## Adapter contract / external-tool registration

`adapters.fmri_derivatives_contract.check_adapter_eligible()` runs before
any scan or export work, mirroring `adapters.mne_bids_contract` exactly:
it confirms `nilearn`'s `ExternalToolRecordV1`
(`external_tools/registry_seed.json`) is not `reference_only`/`avoid_core`
and is not license-blocked, and that a matching, structurally valid
`AdapterContractV1` exists in `external_tools/adapter_contracts_seed.json`
(the same, separate seed file introduced by PR #191, now holding two
adapter contracts). `nilearn` (not `fmriprep`) is the registered tool
because it is already a real, declared, `ready_for_adapter` dependency of
this repository (`dual_engine/fmri_tda_pipeline.py`), while `fmriprep`
remains `external_cli`/`planned` (a heavyweight external pipeline, not a
pip-installable dependency, and its FreeSurfer sub-dependency's license
was not verified). The contract's `integration_mode` is `"adapter_only"`:
this adapter has zero hard runtime dependency on `nilearn` or `fmriprep`
-- pure Python standard library (`json`/`csv`) throughout.

## Limitations

- Consumes lightweight fMRIPrep-style metadata and explicit user-provided
  derived feature tables/graph-summary JSON only -- does not read raw
  BOLD NIfTI files and does not run fMRIPrep or fit any Nilearn model.
- Requires an explicit, human-authored mapping (or self-contained
  graph-summary document); never infers state labels, atlas identity, or
  feature identity from column names, file paths, or parcel counts.
- Cohort-level output requires an explicit, already-computed
  `cohort.subject_count>=2` and `cohort.metrics` -- this adapter never
  computes cohort statistics itself.
- The registry-candidate auto-registration is in-memory unless
  `--updated-registry-out` is given -- without it, a repeat run against
  the same never-before-seen `dataset_id` re-synthesizes the same
  candidate from scratch rather than reusing a persisted one.
- Atlas/parcellation identity is recorded as provided, not independently
  validated as anatomically accurate.
- Does not independently verify the correctness of a supplied feature
  value, confound policy, or preprocessing description; it trusts the
  mapping author's provenance as given, same as any other
  externally-sourced artifact this repository ingests.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Richer fMRIPrep derivative parsing.** v1 reads three specific
  metadata file types directly with the standard library; a fuller
  derivatives-tree traversal (arbitrary space/`desc` entity combinations,
  sidecar JSON inheritance rules) would more naturally use PyBIDS
  (already `P0`/permissive in the external tool registry, see
  `docs/external_tool_integration_strategy.md`) once justified by real
  demand.
- **Direct Nilearn object ingestion.** A v2 adapter that accepts a real
  Nilearn `NiftiMasker`/connectivity object (or reads a raw BOLD NIfTI
  file itself via `nilearn`) and computes features internally, rather
  than trusting a user-supplied table -- a materially larger scope
  decision, mirroring `docs/mne_bids_adapter.md`'s identical "direct MNE
  object ingestion" future-work item.
- **MOABB/EEGDash dataset importers.** Unrelated to fMRI, but tracked
  alongside this adapter in the external tool registry's `P0` tier for
  EEG benchmarking -- no importer exists yet.
- **Holo-Atlas visualization.** No visualization layer of any kind is
  implemented by this or any prior adapter milestone; any future
  visualization of adapter-produced artifacts would consume the same
  `TransitionRecordV1`/`PhaseSpaceCoordinateV1`/`EvidenceBundleV1`
  artifacts this adapter already produces, unmodified.
