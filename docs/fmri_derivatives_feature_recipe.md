# Bounded fMRIPrep/Nilearn Local Derived-Feature Recipe v1

Status: **implemented.** This document describes the
`adapters.fmri_derivatives_feature_recipe*` modules as they exist today.
It does not describe, and should not be read as promising, any of the
capabilities listed in [Future work](#future-work) -- those are
explicitly out of scope for this milestone.

This mirrors `adapters.mne_bids_feature_recipe` (see
[docs/mne_bids_feature_recipe.md](mne_bids_feature_recipe.md)) for the
fMRI modality:

```
local fMRIPrep/Nilearn-style derivatives or fixture
        |
        v   adapters.fmri_derivatives_feature_recipe (this milestone)
derived_features.csv + mapping.json
        |
        v   adapters.fmri_derivatives (unmodified, PR #192)
TransitionRecordV1
        |
        v   (optional --include-phase-space)
PhaseSpaceCoordinateV1
        |
        v   (optional --include-evidence-bundle)
EvidenceBundleV1
        |
        v   (optional --include-report)
EvidenceReportV1
```

## What it does

Given an explicit `FmriFeatureRecipeSpecV1` (a small, human-authored JSON
document -- required fields, no defaults for anything that determines
scientific meaning) and a small local JSON fixture of already-extracted
parcel timeseries, a precomputed connectivity matrix, or a self-contained
`adapters.fmri_derivatives` `format="graph_summary"` document, computes a
small, conservative set of connectivity/graph/QC features per subject, per
requested `source_state`/`target_state` pair, and writes exactly what
`adapters.fmri_derivatives` expects: `derived_features.csv` (long format)
+ `mapping.json`.

Three `input_kind` modes:

- **`timeseries_table`** (default): a JSON fixture of already-extracted
  parcel-level timeseries (`(n_parcels, n_timepoints)` arrays per raw
  state label per subject). Pearson correlation is computed via
  `numpy.corrcoef` over the bounded, truncated timeseries -- this recipe
  never parses a raw NIfTI file.
- **`connectivity_matrix`**: identical fixture shape but with an already
  -computed `(n_parcels, n_parcels)` matrix per raw state label -- no
  correlation is computed by this recipe in this mode.
- **`graph_summary`**: reuses `adapters.fmri_derivatives_features`'s own
  `load_graph_summary`/`expand_graph_summary` directly (the same format
  `adapters.fmri_derivatives` itself already validates/consumes) -- a pure
  pass-through of already-computed values, filtered down to
  `requested_features`. This is the only mode where the three
  `topology.fmri_graph_*` features are usable, since this recipe never
  computes persistent homology itself.

## What it does not do

- **No raw BOLD preprocessing, no fMRIPrep execution, no full Nilearn
  model fitting.** This recipe consumes already-extracted parcel
  timeseries/connectivity matrices/graph summaries, never a raw NIfTI.
- **No automatic state inference.** A raw state label with no entry in
  the spec's `state_mapping` is always skipped with an explicit reason
  (`skipped_subjects`), never guessed into a state.
- **No persistent-homology computation.** `topology.fmri_graph_betti0`/
  `betti1`/`total_persistence_h1` are accepted only as a pass-through from
  an already-computed `graph_summary` input -- never computed here.
- **No anatomical-label validation.** `atlas_or_parcellation` is recorded
  as provided, never independently checked against a real atlas.
- **No dataset download.** Every `input_kind` mode only ever reads a local
  file the caller already supplies as a path; nothing in this module
  fetches anything over the network (static source-guard test:
  `test_cli_never_downloads_raw_data`).
- **Does not produce evidence.** See
  [How this differs from evidence](#how-this-differs-from-evidence).

## Why v1 is bounded and explicit

Four resource bounds (`max_subjects`, `max_runs`, `max_timepoints_per_state`,
`max_total_timepoints`) are **required**, non-optional fields on every
`FmriFeatureRecipeSpecV1` -- a spec missing any of them fails validation
before extraction ever starts (rule 11). Subjects/timepoints beyond the
bounds are recorded in `skipped_subjects`/`qc_summary`, never silently
dropped without a reason. `recipe_id` is a deterministic `sha256[:16]`
over exactly the fields that determine *what* gets computed (`dataset_id`,
`feature_set_id`, `source_state`, `target_state`, `requested_features`,
`atlas_or_parcellation`, and all four bounds) -- `created_at` and every
other free-text field are excluded, so re-specifying the same request
always yields the same `recipe_id`. Unlike the EEG recipe's `recipe_id`,
`atlas_or_parcellation` is deliberately part of the fMRI recipe's identity
basis: two recipes that differ only in atlas/parcellation are extracting a
different scientific quantity, not re-specifying the same request.

## Required recipe spec (`FmriFeatureRecipeSpecV1`)

| Field | Notes |
|---|---|
| `state_mapping` | Required, non-empty `{raw_label: canonical_state}`. States are never inferred any other way (rule 5). |
| `source_state` / `target_state` | Required; both must appear as **values** in `state_mapping` (rule 6). |
| `modality` | Must be `"fMRI"` for v1 (rule 7). |
| `atlas_or_parcellation` | Required, non-empty string (rule 8) -- recorded as provided, never validated against a real atlas. |
| `confound_policy` | Required non-empty object with a non-empty `description` string (rule 9) -- an fMRI feature table with no stated confound-regression policy is exactly the kind of ambiguity this recipe fails closed on. |
| `requested_features` | Must be namespace-valid (`transitions.features.validate_feature_name`) **and** within this recipe's small supported set (rule 10) -- see below. Each must also have an entry in `feature_definitions`. Topology features additionally require `input_kind="graph_summary"`. |
| `graph_policy.threshold` / `graph_policy.threshold_method` | Required whenever a graph-requiring feature (`connectivity.global_efficiency`/`modularity`/`degree`/`small_worldness`) is requested **and** `input_kind != "graph_summary"` (rule 13) -- `graph_summary` mode never builds a graph itself, so no threshold policy is needed there. |
| `max_subjects`, `max_runs`, `max_timepoints_per_state`, `max_total_timepoints` | All required, positive integers (rule 11). |

## Required state mapping

```json
{
  "dataset_id": "demo_fmri_ketamine",
  "feature_set_id": "fmri_connectivity_graph_v1",
  "source_state": "placebo",
  "target_state": "drug",
  "atlas_or_parcellation": "Schaefer100",
  "state_mapping": {
    "placebo_run_label": "placebo",
    "drug_run_label": "drug"
  },
  "confound_policy": {
    "source": "provided_confounds_tsv",
    "motion_threshold": 0.5,
    "description": "24-param + aCompCor confound regression already applied upstream."
  },
  "requested_features": ["connectivity.mean_connectivity", "qc.valid_timepoints"],
  "feature_definitions": {
    "connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation over the bounded, truncated parcel timeseries.",
    "qc.valid_timepoints": "Number of valid timepoints used per state."
  },
  "max_subjects": 20, "max_runs": 20, "max_timepoints_per_state": 200, "max_total_timepoints": 8000
}
```

- A raw state label absent from `state_mapping` is never consulted; a
  subject with no raw label resolving to both `source_state` and
  `target_state` is skipped with an explicit reason in `skipped_subjects`
  (verified by `test_recipe_never_infers_states_from_labels`).
- State imbalance (`total source timepoints != total target timepoints`)
  is recorded in `qc_summary.state_imbalance`, never silently corrected.

## Supported features

Deliberately small. No persistent-homology computation exists in v1 --
`topology.fmri_graph_*` features are pass-through-only from an already
-computed `graph_summary` input.

| Feature | Computation |
|---|---|
| `connectivity.mean_connectivity` | Mean of the strictly-upper-triangular (off-diagonal) entries of the Pearson correlation matrix -- the diagonal never dominates this value. |
| `connectivity.global_efficiency` | `networkx.global_efficiency` over the thresholded connectivity graph. |
| `connectivity.modularity` | `networkx.algorithms.community.greedy_modularity_communities` + `modularity` over the thresholded graph. |
| `connectivity.degree` | Mean node degree of the thresholded graph. |
| `connectivity.small_worldness` | `networkx.algorithms.smallworld.sigma` (bounded `niter=1, nrand=2, seed=0` for determinism/speed), only attempted when the graph has >=5 nodes and is connected -- otherwise marked skipped (NaN + a recorded reason), never invented. |
| `qc.valid_timepoints` | Count of timepoints used per state (post-truncation to `max_timepoints_per_state`). |
| `qc.missing_value_fraction` | Fraction of `NaN` samples in the truncated parcel timeseries. |
| `qc.mean_fd` / `qc.motion_outlier_fraction` | Only ever populated from an explicit `confounds` block in the input fixture -- never computed/estimated by this recipe. NaN (and therefore filtered) if absent. |
| `topology.fmri_graph_betti0` / `betti1` / `total_persistence_h1` | Pass-through only, `input_kind="graph_summary"` only -- always NaN in any other mode (never reached, since validation rejects the request). |

NetworkX (`networkx` 3.6.1, BSD-3-Clause, already declared in
`requirements.txt`) is reused directly for every graph computation --
nothing in this recipe reimplements a graph algorithm.

## Graph/connectivity/QC behavior

- `compute_correlation_matrix` returns `None` -- never a fabricated 0/1
  matrix -- when any parcel signal is constant or entirely NaN
  (`np.corrcoef` on a constant row is undefined). This is recorded
  immediately as a `skipped_inputs` entry (`"constant or all-NaN parcel
  signal -- correlation is undefined"`).
- Any feature value that still ends up NaN (a matrix could not be
  computed, a requested confound was never supplied, ...) is filtered out
  of `derived_features.csv` entirely -- recorded in `skipped_inputs`
  (`"source_value or target_value is NaN ... -- never exported as a valid
  row"`) rather than ever being written as a syntactically-valid-looking
  but scientifically meaningless row. A NaN silently round-trips through
  `float(str(nan))`, so without this explicit filter a downstream
  `adapters.fmri_derivatives` coercion would have accepted it as valid.
- `_build_graph` supports two `graph_policy.threshold_method` values:
  `"absolute_threshold"` (edge iff `value >= threshold`) and
  `"density_threshold"` (edge iff `value` is above a per-matrix quantile
  cutoff computed to hit the target density). An unrecognized method
  raises at graph-build time (defense in depth beyond the spec-validation
  -time presence check).
- `weighted` vs unweighted graph construction is an explicit
  `graph_policy.weighted` boolean, recorded in `mapping.json`'s
  `preprocessing_provenance.graph_policy`.

## Resource bounds

Enforced during extraction, not just at validation time:

- `max_subjects` bounds how many subjects are even *considered* (in
  deterministic sorted order) -- extras go to `skipped_subjects` with
  reason `"exceeded max_subjects bound"`.
- `max_timepoints_per_state` truncates each state's timeseries per subject
  before correlation is computed.
- `max_total_timepoints` bounds the running total across every
  subject/state combined (`timeseries_table` mode only); once exhausted,
  remaining subjects are skipped with an explicit reason.

## Output files

Written under a validated target root (reuses
`dataset_acquisition.store.validate_target_root` directly -- the same
`outputs/`/`data/`-only, no-`..`-traversal check `dataset_acquisition`
already uses):

- `derived_features.csv` -- long format, columns `dataset_id, subject_id,
  session_id, source_state, target_state, atlas_or_parcellation,
  feature_name, source_value, target_value, feature_definition,
  artifact_path`.
- `mapping.json` -- `format="long"`, `confound_policy` as the required
  non-empty **string** `adapters.fmri_derivatives` expects (derived from
  `spec.confound_policy.description`), the full `confound_policy` dict
  additionally preserved under
  `preprocessing_provenance.confound_policy_detail` for traceability,
  `null_control_status="not_provided"` always.
- `recipe_manifest.json` -- `FmriDerivedFeatureRecipeManifestV1`: subjects
  seen/used, sessions/states observed, `skipped_subjects`/`skipped_inputs`
  with explicit reasons, `qc_summary`.
- `summary.json` -- a short, human-readable summary of the same run.

## Downstream adapter/evidence/report integration behavior

`derived_features.csv` + `mapping.json` are handed to
`adapters.fmri_derivatives.export_fmri_derivative_transitions`
**unmodified** -- this recipe does not fork or duplicate any of that
adapter's logic. CLI: `--run-fmri-derivatives-adapter` (off by default;
the default CLI invocation only ever writes the four files above).
`--include-phase-space`, `--include-evidence-bundle`, `--include-report`
map directly onto `adapters.fmri_derivatives`'s own flags of the same
name -- no new evidence-generation logic exists in this recipe.
`--registry`/`--updated-registry-out` follow the same "never mutate the
seed registry in place, require an explicit output path for the merged
registry when downstream work needs it" discipline
`adapters.fmri_derivatives` already enforces. Verified end-to-end this
session, including with `--include-phase-space --include-evidence-bundle
--include-report`, producing a validating `EvidenceBundleV1` and a
guardrail-clean `EvidenceReport.md`.

## CLI

```
python -m adapters.fmri_derivatives_feature_recipe_cli \
    --spec recipe_spec.json --timeseries-table timeseries.json \
    --out outputs/feature_recipes/<recipe_id>

python -m adapters.fmri_derivatives_feature_recipe_cli \
    --spec recipe_spec.json --graph-summary graph_summary.json \
    --out outputs/feature_recipes/<recipe_id> \
    --run-fmri-derivatives-adapter --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/feature_recipes/<recipe_id>/adapter_export/reg.json \
    --include-phase-space --include-evidence-bundle --include-report
```

Exactly one of `--timeseries-table`/`--connectivity-matrix`/
`--graph-summary` is required, matching `spec.input_kind`. Prints
`recipe_id`, `subjects_used`, `states_observed`, `features_written`,
`skipped_subjects`/`skipped_inputs` counts, and output paths. Fails
clearly (non-zero exit, `"FAILED: ..."` message) on: missing/invalid
spec, missing state mapping, missing atlas, missing confound policy,
invalid feature namespace, invalid output root, exceeded bounds, or a
missing graph threshold policy when a graph-requiring feature was
requested outside `graph_summary` mode.

## How this differs from evidence

`FmriFeatureRecipeSpecV1`/`FmriDerivedFeatureRecipeManifestV1` carry no
`claim_scope`/`evidence_level`/`allowed_uses` field -- neither object is
`TransitionRecordV1`/`EvidenceBundleV1`, and nothing in this recipe
produces one directly. `mapping.json`'s `null_control_status` is always
`"not_provided"`: this recipe never computes a null control, regardless
of how the resulting `source_value`/`target_value` pair looks. **This
recipe produces derived features, not evidence by itself. Evidence begins
only when the resulting derived-feature table is passed through
`adapters.fmri_derivatives` and the downstream governed layers.**

## Limitations

- `timeseries_table`/`connectivity_matrix` modes read a small,
  self-contained JSON fixture, not a real fMRIPrep derivatives directory
  tree -- no `dataset_description.json`/BIDS-entity-based file discovery
  (that already exists, separately, in `adapters.fmri_derivatives.scan_fmri_derivatives_metadata`).
- `connectivity_matrix` mode has no timeseries available, so
  `qc.valid_timepoints`/`qc.missing_value_fraction` are NaN (and
  therefore filtered) unless the matrix-mode fixture also supplies an
  explicit `confounds` block covering the relevant QC feature.
- `small_worldness` is skipped (not computed) for any graph with fewer
  than 5 nodes or that is disconnected after thresholding -- a real
  limitation of `networkx.algorithms.smallworld.sigma`, not a bug.
- Atlas/parcellation identity is recorded as provided, never
  independently validated as anatomically accurate.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Richer fMRIPrep parsing** -- real `*_desc-confounds_timeseries.tsv`
  ingestion as the QC confound source, rather than only an explicit
  `confounds` block in a fixture.
- **Direct Nilearn object support** -- accepting an in-memory
  `nilearn.maskers`/`ConnectivityMeasure` output directly, rather than
  only a filesystem JSON fixture.
- **Atlas metadata validation** -- checking `atlas_or_parcellation`
  against a real, versioned atlas registry rather than recording it as
  provided.
- **Topology computation backends** -- computing
  `topology.fmri_graph_betti0`/`betti1`/`total_persistence_h1` directly
  (e.g. via `core/topology.py`'s existing GUDHI-backed persistence
  functions) rather than only accepting them as a `graph_summary`
  pass-through.
- **Holo-Atlas visualization** -- once real evidence bundles exist from
  this chain, a visualization layer consuming `EvidenceBundleV1` output
  (not raw derived features) is a natural next step.

This milestone does not imply clinical validity for any feature it
computes, does not imply consciousness or spiritual-state detection
regardless of a dataset's subject matter, and does not imply that its own
`derived_features.csv`/`mapping.json` output is evidence by itself --
evidence begins only at `adapters.fmri_derivatives` and beyond.
