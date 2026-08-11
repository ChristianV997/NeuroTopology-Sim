# MOABB + EEGDash Dataset Candidate Importer v1

Status: **implemented, the third package in this repository's
external-artifact chain**, alongside `adapters.mne_bids`
(`docs/mne_bids_adapter.md`) and `adapters.fmri_derivatives`
(`docs/fmri_derivatives_adapter.md`). This document describes the
`dataset_importers/` package as it exists today. It does not describe, and
should not be read as promising, any of the capabilities listed in
[Future work](#future-work) -- those are explicitly out of scope for this
milestone.

This package is deliberately **not another adapter**. The two existing
adapters convert already-derived feature artifacts into governed
`TransitionRecordV1`/`EvidenceBundleV1`/`EvidenceReportV1` output.
`dataset_importers` sits one layer upstream of that: it scouts *which
public datasets are worth pointing an adapter at in the first place*, and
produces nothing stronger than a scouting record.

## Why metadata-first dataset importers exist

This repository can now ingest external EEG/MNE/BIDS-derived artifacts
(PR #191) and external fMRI/Nilearn-derived artifacts (PR #192). Both
adapters require a human to already know which dataset, which conditions,
and which mapping to write. The actual bottleneck is no longer "can this
repository consume an external lab's derived features" -- it is "which of
the hundreds of public neurophysiology datasets are worth that effort."
MOABB and EEGDash are the two most relevant open catalogs for answering
that question without downloading anything:

- both are public, permissively licensed (BSD-3-Clause) open-source
  projects, not proprietary services;
- both already organize datasets around exactly the metadata this
  repository needs to judge transition-readiness (subjects, sessions,
  tasks/paradigms, conditions/events, modality);
- both connect to the MNE/BIDS ecosystem this repository's first adapter
  already targets;
- both can expand this repository's benchmark coverage (anesthesia, sleep,
  psychedelics, meditation, TMS, clinical research, BCI, ...) without
  committing a single byte of raw data to this repository.

## What v1 imports

Two source catalogs, each with a fixture-based path (always available) and
a best-effort installed-package path (used only if the corresponding
Python package is actually importable in the running environment):

- **MOABB** (`dataset_importers.moabb_importer`, BSD-3-Clause,
  https://github.com/NeuroTechX/moabb) -- exposes each dataset as a
  `moabb.datasets.base.BaseDataset` subclass. Verified this session from
  the project's own source (`moabb/datasets/base.py`,
  `moabb/datasets/utils.py`): the constructor accepts `subjects,
  sessions_per_subject, events, code, interval, paradigm, doi, ...`, and
  `moabb.datasets.utils.dataset_list` enumerates every dataset class via
  `inspect.getmembers(moabb.datasets, inspect.isclass)` filtered to
  `BaseDataset` subclasses -- the same technique
  `import_moabb_candidates_from_installed_package` uses. Instantiating a
  dataset class does not download anything by MOABB's own design; only
  `.get_data()` does, and this module never calls it. `moabb` is not
  declared in `requirements.txt` in this milestone (it is not currently a
  dependency of anything else in this repository), so its installed-package
  path is genuinely best-effort and untested against a live install in
  every environment.
- **EEGDash** (`dataset_importers.eegdash_importer`, BSD-3-Clause,
  https://github.com/eeg2go/eegdash) -- catalogs 700+ BIDS-first
  EEG/MEG/fNIRS/EMG/iEEG datasets. Verified live this session (`eegdash`
  0.8.4, already declared in `requirements.txt` and importable):
  `eegdash.EEGDash.find_datasets()`/`search_datasets()`/`get_dataset()` are
  documented by the package itself as metadata-only -- "does not download
  any signal bytes; only small JSON catalogue documents are transferred."
  The real `eegdash.schemas.Dataset` `TypedDict` (read from the installed
  package's source this session) is the field reference
  `_record_from_eegdash_meta` maps from: `dataset_id`, `name`, `source`,
  `recording_modality`, `datatypes`, `license`, `tasks`, `sessions`,
  `dataset_doi`, `demographics` (with `subjects_count`), `tags`, `storage`.

Both importers produce the same `DatasetCandidateRecordV1` shape (see
below) via `import_<source>_candidates_from_fixture()` (JSON fixture, no
package required) or `import_<source>_candidates_from_installed_package()`
(best-effort, guarded, never raises an uncaught exception).

## What v1 does not import

- No raw dataset download, ever. Neither importer calls `.get_data()`
  (MOABB) or a data-loading/caching class like `EEGDashDataset` (EEGDash) --
  verified by a static source-code guard test
  (`test_cli_never_downloads_raw_data`) in addition to the runtime tests
  below.
- No raw EEG preprocessing, no direct MNE `Raw`/`Epochs` ingestion (that
  remains `adapters.mne_bids`'s job, once a candidate becomes a real,
  mapped dataset).
- No Braindecode model training, no deep-learning baselines, no
  real-time BrainFlow/MNE-LSL streaming, no fMRI preprocessing, no new
  topology algorithms.
- No fabricated license, subject count, task label, or modality. Any field
  the source metadata does not explicitly provide stays `unknown`/`None` --
  never guessed from a dataset's name, its paradigm family, or any other
  indirect signal. See `test_handles_missing_loadability_metadata_conservatively`
  and its MOABB analog.
- No candidate is ever marked validation-ready. See
  [Claim/evidence policy](#claimevidence-policy) below.

## No-download policy (how it is actually enforced)

1. `import_moabb_candidates_from_installed_package` only reads instance
   attributes (`code`, `subject_list`, `n_sessions`, `event_id`,
   `paradigm`, `doi`) already set by a dataset class's own `__init__` --
   it never calls a method.
2. `import_eegdash_candidates_from_installed_package` defaults to
   `live_query=False`, which performs **no network I/O at all**: it only
   confirms the installed package exposes an `EEGDash` client class and
   returns an empty list with the query left unperformed. A real metadata
   query (`EEGDash().find_datasets(...)`) requires the caller to pass
   `live_query=True` explicitly (CLI: `--allow-live-query`) -- never the
   default, never used by this repository's test suite, and never invoked
   more than once per call (no pagination loop, no retry against a
   `.download()`-shaped method).
3. Every network-shaped call is wrapped in `try/except`; a failure raises
   `EegdashImporterUnavailable` with the underlying error message rather
   than silently returning a fabricated or partial result.
4. Tests exercise the live-query code path by monkeypatching
   `eegdash.EEGDash` with a fake client
   (`test_installed_package_live_query_uses_monkeypatched_client_never_real_network`)
   -- the real mapping logic is exercised, but no HTTP request is ever
   made during `pytest`.

## `DatasetCandidateRecordV1`

`dataset_importers/candidate_record.py`. A candidate is **not**
`benchmarks.dataset_registry.DatasetRecordV1` -- it is deliberately
pre-registry and structurally incapable of authorizing a transition/
phase-space export (see [Claim/evidence policy](#claimevidence-policy)).

| Field | Notes |
|---|---|
| `candidate_id` | Deterministic `sha256[:16]` over `(source_catalog, source_dataset_id)` only -- re-importing the same catalog entry always yields the same ID. |
| `source_catalog` | One of `moabb`, `eegdash`, `openneuro_manual`, `nemar_manual`, `repo_manual`, `synthetic_fixture`. |
| `license` / `license_risk` | `license_risk` reuses `external_tools.validation.ALLOWED_LICENSE_RISK`; unknown license always forces `license_risk="unknown_high"`. |
| `access_status` | `public` / `public_requires_download` / `requires_registration` / `restricted` / `unknown`. |
| `download_required` | `"true"` / `"false"` / `"unknown"` -- always explicit, never omitted. |
| `transition_readiness` | See [readiness ladder](#the-transition-readiness-ladder) below. |
| `benchmark_role_recommendation` | `exploration_candidate` / `development_candidate` / `documentation_only` / `blocked` / `review_needed`. |
| `allowed_uses` / `forbidden_uses` | Every candidate's `forbidden_uses` always includes `transition_export`, `phase_space_export`, and the four terminal-claim uses (see below) -- a candidate can never carry evidence authority, regardless of how strong its metadata looks. |
| `risks` / `limitations` / `provenance` | All three are required non-empty by validation; a candidate with no stated risk or provenance fails structurally. |

Full validation lives in `dataset_importers/validation.py`
(`validate_candidate_record`), enforcing all twelve rules from this
milestone's mission spec (deterministic ID, non-empty
limitations/risks/provenance, unknown-license normalization,
restricted/unknown-access ceiling on `development_candidate`, the
`blocked_license_or_access` forbidden-use floor, the "metadata_only is not
evidence" floor, the terminal-claim floor, explicit `source_catalog`, and
explicit `download_required`). It reuses
`phase_space.coordinate.scan_banned_phrases` (the same shared
banned-phrase scanner every other validator in this repository uses) plus
one small additive list of scouting-specific overclaim phrases
(`DATASET_IMPORTER_EXTRA_BANNED_PHRASES`, e.g. `"candidate is evidence"`,
`"metadata proves"`).

### The transition-readiness ladder

`infer_transition_readiness()` in `candidate_record.py` is a single,
shared, deterministic function both importers call -- so two datasets with
identical known metadata always land at the same readiness level,
regardless of which catalog they came from:

```
not modality_supported            -> blocked_unsupported_modality
not (license_ok and access_ok)    -> blocked_license_or_access
no conditions AND no subject_count -> blocked_missing_metadata
conditions AND subject_count       -> candidate_transition_possible
conditions, no subject_count       -> derived_feature_extraction_needed
subject_count, no conditions       -> explicit_condition_mapping_needed
```

`infer_benchmark_role_recommendation()` then derives the role
recommendation from readiness + `access_status`, downgrading
`development_candidate` to `review_needed` whenever access is
`restricted`/`unknown` -- enforcing validation rule 6 at construction time,
not only at validation time.

## Candidate scoring

`dataset_importers/scoring.py`. `score_candidate()`/`rank_candidates()`
are a **simple, documented, additive heuristic** -- explicitly not a
scored/weighted model, mirroring
`external_tools.registry.ExternalToolRegistry.recommended_next()`'s own
stance on this. `CandidateScore` carries no `claim_scope`/`evidence_level`/
`null_control_summary` field, by design: it is a planning heuristic, never
evidence.

Components: `license_score`, `access_score`, `metadata_score` (explicit
condition labels weigh more than a bare subject count),
`transition_score`, `modality_score`, `adapter_fit_score` (from
`compatible_adapters`), and a `risk_penalty` subtracted from the total.
Restricted access additionally **caps** `total_score` at 3 regardless of
every other component, so a metadata-rich but access-restricted dataset
can never outrank a modest, genuinely open one.

## Benchmark-candidate conversion

`dataset_importers.export_candidates.convert_candidates_to_benchmark_records()`
converts only `development_candidate`/`exploration_candidate` tier
candidates into `benchmarks.dataset_registry.DatasetRecordV1` /
`benchmarks.artifact_registry.ArtifactRecordV1` stubs --
`blocked`/`review_needed`/`documentation_only` candidates are never
converted. Every converted record lands with the same conservative floor
the two existing adapters use for their own metadata-scan-only records:
`current_role="exploration"`, `contamination_status="unseen"`,
`allowed_uses=["documentation", "feature_design"]`,
`claim_scope_ceiling="exploratory_metric"`,
`evidence_level_ceiling="L0_computational_artifact"`. The dataset's
`dataset_id` is `<slugified source_catalog>-<slugified source_dataset_id>`
so IDs never collide across catalogs. **The seed benchmark registry
(`benchmarks/registry_seed.json`) is never touched** -- conversion output
is written to a separate file the caller names via
`--to-benchmark-candidates`.

## License/access risk handling

Reuses `external_tools.validation.ALLOWED_LICENSE_RISK` rather than a new
copy. Neither importer guesses a license/access value it was not
explicitly given:

- MOABB's Python API does not expose per-dataset license/access terms as
  object attributes (confirmed from `moabb/datasets/base.py`'s constructor
  signature this session) -- every MOABB-sourced candidate defaults to
  `license="unknown"`/`license_risk="unknown_high"` unless a fixture
  explicitly supplies them.
- EEGDash's `source` field is explicit, verifiable evidence for
  `access_status="public"` only when it is `openneuro` or `nemar` (both
  known public open archives, browsable/fetchable with no registration) --
  any other or missing `source` value stays `unknown`.
- `download_required` is always `"true"` for both catalogs: retrieving
  actual signal bytes from either always requires a fetch/download step
  this repository never performs.

## Transition-readiness statuses

See [the readiness ladder](#the-transition-readiness-ladder) above for the
full decision table; the seven allowed values are `metadata_only`,
`candidate_transition_possible`, `explicit_condition_mapping_needed`,
`derived_feature_extraction_needed`, `blocked_missing_metadata`,
`blocked_license_or_access`, `blocked_unsupported_modality`.

## Claim/evidence policy

**Candidate status is not validation** (this milestone's core principle).
Concretely, enforced structurally (not just by convention) in
`dataset_importers/validation.py`:

- No `DatasetCandidateRecordV1.allowed_uses` may ever contain
  `transition_export` or `phase_space_export` (validation rule 8) --
  every candidate's `forbidden_uses` must include both, unconditionally,
  regardless of how strong its metadata looks. That authority belongs
  only to a real `DatasetRecordV1` built later with an explicit mapping,
  exactly as `adapters.mne_bids`/`adapters.fmri_derivatives` already
  require.
- No candidate may allow `final_claim_confirmation`, `clinical_claim`,
  `mechanistic_causal_claim`, or `prospective_prediction_claim`
  (validation rule 9) -- these four are a required floor of every
  candidate's `forbidden_uses`.
- `metadata_only` readiness is never treated as evidence (validation rule
  8, same mechanism as above).
- Both new `AdapterContractV1` registrations (see below) cap
  `allowed_claim_scope_ceiling="exploratory_metric"` and
  `evidence_level_ceiling="L0_computational_artifact"` -- the same floor
  this repository's metadata-scan-only `DatasetRecordV1` output already
  uses elsewhere.

## Adapter contract / external-tool registration

Two new `AdapterContractV1` entries were added to
`external_tools/adapter_contracts_seed.json` (additive; the file's
existing MNE/BIDS and fMRIPrep/Nilearn contracts are unchanged):

- `tool_id="moabb"`, `adapter_name="MOABB Dataset Candidate Importer v1"`
- `tool_id="eegdash"`, `adapter_name="EEGDash Dataset Candidate Importer v1"`

Both use `integration_mode="metadata_import"` (an already-existing value
in `external_tools.validation.ALLOWED_INTEGRATION_MODES`, matching how
`external_tools/registry_seed.json` already classified both tools before
this milestone) and `output_targets=["external_metadata_only",
"DatasetRecordV1", "ArtifactRecordV1"]` -- deliberately **not**
`TransitionRecordV1`/`PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/
`EvidenceReportV1`: this package produces scouting records only, and its
`AdapterContractV1` says so structurally, not just in prose. Both
`external_tools/registry_seed.json` entries for `moabb`/`eegdash` already
declared a `planned_adapter` string pointing at this exact milestone;
neither entry needed any other change.

## How this supports the commercial plan

The chain this package prepares, without itself producing anything beyond
a scouting record:

```
MOABB / EEGDash public catalog metadata
        |
        v   dataset_importers (this package)
DatasetCandidateRecordV1  (scouting record, never evidence)
        |
        v   convert_candidates_to_benchmark_records (development/exploration tier only)
DatasetRecordV1 / ArtifactRecordV1  (candidate registry entry, still exploration-role)
        |
        v   a human writes an explicit condition/state mapping
adapters.mne_bids  ->  TransitionRecordV1  ->  ...  ->  EvidenceReportV1
```

Concretely: more demo datasets to point the existing pipeline at without a
manual OpenNeuro/NEMAR scouting pass each time; a governed, greppable
answer to "what should the next benchmark pack cover" instead of an ad hoc
web search; safer dataset selection (license/access risk is surfaced
*before* any effort is spent on a mapping); and a documented on-ramp for a
future methods paper describing how this repository selects its public
data sources.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **A safe, curated download pipeline.** This milestone deliberately stops
  at metadata; actually fetching a chosen candidate's raw data (with the
  same disk-bounded fetch-process-delete discipline this repository's
  existing OpenNeuro/DANDI streamers already use) is a separate, larger
  decision this milestone does not make.
- **Derived-feature extraction recipes** for a chosen candidate, once
  downloaded -- turning raw signal into the feature tables
  `adapters.mne_bids`/`adapters.fmri_derivatives` already know how to
  consume.
- **Benchmark-pack generation** -- bundling several converted candidates
  plus their eventual real transition records into a single, documented,
  shippable pack.
- **MOABB task-specific adapters** (per-paradigm feature conventions for
  motor imagery vs. P300 vs. SSVEP) rather than this milestone's uniform,
  paradigm-agnostic treatment.
- **EEGDash BIDS-loadability filtering** -- using the package's own BIDS
  validator status fields (`bids_validator_status`, `n_validator_errors`)
  once a real need to filter on them arises; this milestone reads them
  only if a fixture explicitly supplies them and does not yet fold them
  into scoring.
- **Direct integration with the MNE/BIDS adapter** -- e.g. a single CLI
  invocation that takes a scored candidate straight into
  `adapters.mne_bids`'s metadata-scan path. Today the two packages are
  connected only by documentation and by a human's own next step.

This milestone does not imply that any imported candidate is analyzed
evidence, does not imply clinical validity for any dataset it surfaces,
and does not imply consciousness or spiritual-state detection for any
dataset regardless of its subject matter (e.g. a meditation or psychedelic
study catalogued by EEGDash is scored on the same metadata axes as every
other candidate -- modality, license, access, explicit conditions -- never
on its subject matter).
