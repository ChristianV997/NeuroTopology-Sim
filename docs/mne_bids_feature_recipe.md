# Bounded MNE/BIDS Local Derived-Feature Recipe v1

Status: **implemented.** This document describes the
`adapters.mne_bids_feature_recipe*` modules as they exist today. It does
not describe, and should not be read as promising, any of the
capabilities listed in [Future work](#future-work) -- those are
explicitly out of scope for this milestone.

This is the fifth link in the chain that started with `dataset_importers/`
and `dataset_acquisition/`:

```
local verified BIDS-like root (dataset_acquisition, PR #194)
        |
        v   adapters.mne_bids_feature_recipe (this milestone)
derived_features.csv + mapping.json
        |
        v   adapters.mne_bids (unmodified, PR #191)
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

Given an explicit `FeatureRecipeSpecV1` (a small, human-authored JSON
document -- required fields, no defaults for anything that determines
scientific meaning) and either a local BIDS-like root or a pre-windowed
epoch-table fixture, computes a small, conservative set of spectral/QC/
complexity features per subject, per requested `source_state`/
`target_state` pair, and writes exactly what `adapters.mne_bids` expects:
`derived_features.csv` (long format) + `mapping.json`.

Two `input_kind` modes:

- **`epoch_table`** (default): reads a JSON file of already-windowed
  epoch arrays. No `mne` dependency required for this path -- only
  numpy/scipy (already core requirements). This is the primary,
  always-tested path.
- **`bids_raw`** (best-effort): walks `bids_root` for `*_events.tsv`
  files (the same glob `adapters.mne_bids.scan_bids_metadata` already
  uses), reads the sibling raw EEG file via `mne.io.read_raw` (already a
  declared, installed dependency: `mne` 1.12.1 verified this session),
  and epochs directly from the events file's own `onset`/`duration`
  columns -- never from a stim channel or `find_events` guess. Tested
  against a real, tiny, in-test-synthesized MNE `RawArray` saved to
  `.fif` and read back -- not a mock, and not a downloaded dataset.

## What it does not do

- **No raw EEG preprocessing framework.** No ICA, no artifact rejection,
  no Autoreject/PyPREP (`artifact_policy` accepts only `"none"` in v1).
- **No automatic event/state inference.** An event label with no entry in
  the spec's `event_state_mapping` is always skipped with an explicit
  reason (`skipped_events`), never guessed into a state.
- **No clinical/qEEG interpretation, no deep-learning baselines.**
- **No MOABB pipeline execution, no EEGDash raw retrieval, no
  BrainFlow/MNE-LSL live streaming.**
- **No dataset download.** `input_kind="bids_raw"` only ever reads a
  `bids_root` the caller already supplies as a local path; nothing in
  this module fetches anything over the network (static source-guard
  test: `test_cli_never_downloads_raw_data`).
- **Does not produce evidence.** See
  [How this differs from evidence](#how-this-differs-from-evidence).

## Why v1 is bounded and explicit

Four resource bounds (`max_subjects`, `max_runs`, `max_epochs_per_state`,
`max_total_epochs`) are **required**, non-optional fields on every
`FeatureRecipeSpecV1` -- a spec missing any of them fails validation
before extraction ever starts (mission rule 9). Subjects/epochs beyond
the bounds are recorded in `skipped_subjects`/`qc_summary`, never
silently dropped without a reason. This keeps a recipe run's cost
predictable regardless of how large the underlying local dataset actually
is, and keeps every recipe run reproducible: `recipe_id` is a deterministic
`sha256[:16]` over exactly the fields that determine *what* gets computed
(`dataset_id`, `feature_set_id`, `source_state`, `target_state`,
`requested_features`, and all four bounds) -- `created_at` and every other
free-text field are excluded, so re-specifying the same request always
yields the same `recipe_id`.

## Required recipe spec (`FeatureRecipeSpecV1`)

All fields from the mission spec are present; the ones that most directly
gate correctness:

| Field | Notes |
|---|---|
| `event_state_mapping` | Required, non-empty `{raw_label: canonical_state}`. States are never inferred any other way (validation rule 5). |
| `source_state` / `target_state` | Required; both must appear as **values** in `event_state_mapping` (rule 6). |
| `modality` | Must be `"EEG"` for v1 (rule 7) -- MEG/iEEG/fNIRS are out of scope until explicitly supported. |
| `requested_features` | Must be namespace-valid (`transitions.features.validate_feature_name`) **and** within this recipe's small supported set (rule 8) -- see below. Each must also have an entry in `feature_definitions`. |
| `max_subjects`, `max_runs`, `max_epochs_per_state`, `max_total_epochs` | All required, positive integers (rule 9). |
| `artifact_policy` | Only `"none"` is valid in v1 -- Autoreject/PyPREP are future work, not v1 dependencies. |
| `reference_policy` | `"as_recorded"` (default, no change applied) or `"average"` (a single `raw.set_eeg_reference("average")` call in `bids_raw` mode). |

## Required event/state mapping

```json
{
  "dataset_id": "demo_bids_eeg",
  "feature_set_id": "mne_bids_spectral_v1",
  "source_state": "rest",
  "target_state": "task",
  "event_state_mapping": {
    "rest_marker": "rest",
    "task_marker": "task"
  },
  "requested_features": ["spectral.alpha_power", "qc.valid_epoch_count"],
  "feature_definitions": {
    "spectral.alpha_power": "Mean relative alpha-band power over valid epochs using the configured recipe.",
    "qc.valid_epoch_count": "Count of valid epochs used per state."
  },
  "max_subjects": 20, "max_runs": 20, "max_epochs_per_state": 30, "max_total_epochs": 600
}
```

- A raw event label absent from `event_state_mapping` is always skipped
  (`skipped_events`, reason `"not present in event_state_mapping (never
  inferred)"`) -- verified by
  `test_bids_raw_skips_unmapped_events`/`test_recipe_never_infers_states_from_event_names`.
- A subject missing epochs for either `source_state` or `target_state` is
  skipped with an explicit reason in `skipped_subjects`, never
  silently dropped or partially exported.
- State imbalance (`total_source_epochs != total_target_epochs`) is
  recorded in `qc_summary.state_imbalance`, never silently corrected
  (e.g. by dropping extra epochs from the larger side beyond what
  `max_epochs_per_state` already bounds).

## Supported features

Deliberately small (mission Phase C: "keep v1 small and robust"). No
connectivity/PLV feature exists in v1 -- correctly implementing and
testing pairwise connectivity was judged out of scope for this milestone.

| Feature | Computation |
|---|---|
| `spectral.{delta,theta,alpha,beta,gamma}_power` | Relative band power (`{band}_power_rel`) via `sciencer_d.btc_icft.level_m.real_features.compute_band_power` -- this repository's own existing, tested Welch-PSD implementation, reused rather than reimplemented. |
| `qc.valid_epoch_count` | Count of epochs used for that state. |
| `qc.channel_count` | Number of channels contributing. |
| `qc.duration_seconds` | Total signal duration used for that state. |
| `qc.missing_value_fraction` | Fraction of `NaN` samples across the picked channels' epochs. |
| `complexity.spectral_entropy` | Normalized Shannon entropy of the Welch PSD's normalized distribution -- implemented directly with `scipy.signal.welch` (the standard textbook definition), not via an external package, since `antropy` (declared in `requirements.txt`) is not guaranteed installed in every environment this recipe runs in. |

Every value is averaged across epochs and channels for that
(subject, state) pair -- one `source_value`/`target_value` pair per
feature per subject/session, matching `adapters.mne_bids`'s expected long
table shape exactly.

## Resource bounds

Enforced during extraction, not just at validation time:

- `max_subjects` bounds how many subjects are even *considered* (in
  deterministic sorted order) -- extras go to `skipped_subjects` with
  reason `"exceeded max_subjects bound"`.
- `max_epochs_per_state` truncates each state's epoch list per subject
  before feature computation.
- `max_total_epochs` bounds the running total across every subject/state
  combined; once exhausted, remaining subjects are skipped with an
  explicit reason rather than partially processed.

## Output files

Written under a validated target root (reuses
`dataset_acquisition.store.validate_target_root` directly -- the same
`outputs/`/`data/`-only, no-`..`-traversal check `dataset_acquisition`
already uses, so this recipe's output can never land in a tracked source
directory):

- `derived_features.csv` -- long format, columns `dataset_id, subject_id,
  session_id, source_state, target_state, feature_name, source_value,
  target_value, feature_definition, artifact_path`.
- `mapping.json` -- `format="long"`, `preprocessing_provenance` recording
  the recipe_id/feature_set_id/frequency_bands/epoch_window/policies used,
  `null_control_status="not_provided"` always (never computed by this
  recipe -- see below).
- `recipe_manifest.json` -- `DerivedFeatureRecipeManifestV1`: subjects
  seen/used, sessions/states observed, `skipped_subjects`/
  `skipped_runs`/`skipped_events` with explicit reasons, `qc_summary`.
- `summary.json` -- a short, human-readable summary of the same run.

## How outputs feed `adapters.mne_bids`

`derived_features.csv` + `mapping.json` are handed to
`adapters.mne_bids.export_mne_bids_derived_transitions` **unmodified** --
this recipe does not fork or duplicate any of that adapter's logic. CLI:
`--run-mne-bids-adapter` (off by default; the default CLI invocation only
ever writes the four files above). Verified end-to-end this session,
including with `--include-phase-space --include-evidence-bundle
--include-report`, producing a validating `EvidenceBundleV1` and a
guardrail-clean `EvidenceReport.md`.

## Optional evidence/report handoff

`--include-phase-space`, `--include-evidence-bundle`, `--include-report`
map directly onto `adapters.mne_bids`'s own flags of the same name -- no
new evidence-generation logic exists in this recipe. `--registry`/
`--updated-registry-out` follow the same "never mutate the seed registry
in place, require an explicit output path for the merged registry when
downstream work needs it" discipline `adapters.mne_bids` already enforces.

## How this differs from evidence

`FeatureRecipeSpecV1`/`DerivedFeatureRecipeManifestV1` carry no
`claim_scope`/`evidence_level`/`allowed_uses` field -- neither object is
`TransitionRecordV1`/`EvidenceBundleV1`, and nothing in this recipe
produces one directly. `mapping.json`'s `null_control_status` is always
`"not_provided"`: this recipe never computes a null control, regardless
of how the resulting `source_value`/`target_value` pair looks (mission
rule 12). Evidence begins only once the recipe's output is passed through
`adapters.mne_bids` and, optionally, `evidence.builder`/`reports.evidence_report`.

## Limitations

- `bids_raw` mode supports only `.fif`/`.edf`/`.bdf`/`.set`/`.vhdr` raw
  files located as a direct sibling of their `*_events.tsv` file with a
  matching basename -- no BIDS derivatives/sidecar-inheritance traversal.
- Epoching in `bids_raw` mode is a fixed-length window starting at each
  mapped event's `onset` -- no baseline correction, no overlap-aware
  re-epoching beyond `epoch_window.overlap_seconds` being recorded (not
  yet applied).
- `channel_policy`/`filter_policy` are applied as single, simple MNE
  calls (`raw.pick(...)`, `raw.filter(...)`) -- no channel-quality
  scoring, no bad-channel interpolation.
- `complexity.spectral_entropy` is a self-contained, direct implementation
  rather than a call into `antropy` (not guaranteed installed).

## Used by the report pipeline runner

`workflows.report_pipeline` (see `docs/report_pipeline_runner.md`) can
run this recipe as its `input_mode="mne_bids_epoch_table_recipe"` step,
then continue into `adapters.mne_bids` and, optionally,
`evidence.builder`/`reports.evidence_report` -- unmodified, exactly as
this recipe's own CLI (`--run-mne-bids-adapter`) already does.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Richer QC** -- bad-channel detection, per-epoch rejection thresholds,
  a real `qc_summary` beyond epoch counts and state imbalance.
- **Autoreject/PyPREP optional QC adapters** -- both already permissively
  licensed per `external_tools/registry_seed.json`'s existing
  classification; not wired in as v1 dependencies.
- **MOABB-specific task recipes** -- per-paradigm (`imagery`/`p300`/`ssvep`)
  feature conventions, once a `dataset_acquisition`-acquired MOABB dataset
  exists locally to test against.
- **EEGDash BIDS-loadability recipes** -- using EEGDash's own
  `bids_validator_status` fields to pre-filter which acquired datasets are
  worth running this recipe against at all.
- **Direct Raw/Epochs v2** -- accepting an in-memory `mne.io.Raw`/
  `mne.Epochs` object directly (rather than only a filesystem path), once
  this repository's broader preprocessing policy (re-referencing defaults,
  filter defaults, ICA policy) is made explicit beyond this recipe's own
  narrow `reference_policy`/`filter_policy` fields.

This milestone does not imply clinical validity for any feature it
computes, does not imply consciousness or spiritual-state detection
regardless of a dataset's subject matter, and does not imply that its own
`derived_features.csv`/`mapping.json` output is evidence by itself --
evidence begins only at `adapters.mne_bids` and beyond.
