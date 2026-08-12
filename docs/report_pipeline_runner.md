# Governed Report Pipeline Runner + Demo Pack v1

Status: **implemented.** This document describes the `workflows/` package
as it exists today. It does not describe, and should not be read as
promising, any of the capabilities listed in [Future work](#future-work)
-- those are explicitly out of scope for this milestone.

This is the first **product/commercial workflow layer** in this
repository -- everything before it (`dataset_acquisition/`,
`dataset_importers/`, `adapters.mne_bids_feature_recipe`,
`adapters.fmri_derivatives_feature_recipe`, `adapters.mne_bids`,
`adapters.fmri_derivatives`, `evidence.builder`,
`reports.evidence_report`) is a real, independently governed module, but
a user had to chain them by hand, one CLI invocation at a time. This
milestone adds one deterministic, guarded runner that executes a
supported pathway end to end and writes a single indexed **report pack**.

```
candidate/import/acquisition planning (dataset_acquisition/, dataset_importers/)
        |
        v   bounded local feature recipes (adapters.*_feature_recipe)
derived_features.csv + mapping.json
        |
        v   adapters (adapters.mne_bids / adapters.fmri_derivatives)
TransitionRecordV1
        |
        v   (optional)
PhaseSpaceCoordinateV1
        |
        v   (optional)
EvidenceBundleV1
        |
        v   (optional)
EvidenceReportV1
        |
        v   workflows.report_pipeline (THIS MILESTONE)
ReportPackV1  (one deterministic index of everything the run produced)
```

## What it does

Given an explicit `ReportPipelineSpecV1` (a small, human-authored JSON
document) and one of 11 supported `input_mode` values, the runner
executes only the steps that mode requires -- reusing the already-tested
library functions each step calls, never reimplementing them -- and
writes a deterministic, indexed `ReportPackV1` once real evidence exists.

## What it does not do

- **No new feature extraction, no raw EEG/fMRI signal processing, no
  persistent-homology computation.** Every scientific number a report
  pack references was already computed by the adapter/recipe/evidence
  module that owns that logic -- see [Core principle](#core-principle).
- **No LLM call.** Report generation is template-based
  (`reports.evidence_report`), exactly as it already was before this
  milestone.
- **No dataset download.** Every mode reads a local file/directory path
  the caller already supplies; `builtin_*` modes read this repository's
  own already-committed `contracts/btc_icft/ds005620/`/`contracts/fmri_tda/
  ds000245/` artifacts, never anything fetched over the network (static
  source-guard test: `test_cli_never_downloads_raw_data`).
- **No registry seed mutation in place.** Every registry-touching step
  writes its update to an explicit `registry_updated.json` under the
  deterministic report-pack layout, exactly mirroring the discipline
  `adapters.mne_bids`/`adapters.fmri_derivatives` already enforce.
- **Does not promote a claim scope or evidence level.** See
  [How a report pack differs from evidence](#how-a-report-pack-differs-from-evidence).

## Core principle

**This runner orchestrates existing governed modules. It does not
duplicate scientific logic already implemented in adapters, recipes,
evidence, or reports.** Concretely: `workflows/report_pipeline.py`
imports and calls `adapters.mne_bids_feature_recipe.run_feature_recipe`/
`write_recipe_outputs`, `adapters.fmri_derivatives_feature_recipe`'s
equivalents, `adapters.mne_bids.export_mne_bids_derived_transitions`,
`adapters.fmri_derivatives.export_fmri_derivative_transitions`, and
`evidence.builder.build_evidence_bundle` **unmodified** -- none of those
functions were changed to support this milestone.

## Files

```
workflows/
    __init__.py
    report_pipeline.py       ReportPipelineSpecV1, ReportPipelineRunManifestV1,
                              run_report_pipeline() -- schema + orchestration
    report_pack.py            ReportPackV1 -- the deterministic output index
    validation.py              structural validation for all three schemas
    store.py                    deterministic output-directory layout
    export_report_pack.py  CLI: python -m workflows.export_report_pack
tests/fixtures/report_pipeline_demo.py   demo fixture generators (Phase F)
```

## Supported input modes

| `input_mode` | What it does |
|---|---|
| `existing_evidence_bundle` | Loads an already-built `EvidenceBundleV1` from `evidence_bundle_path`; optionally builds an `EvidenceReportV1` from it. |
| `mne_bids_epoch_table_recipe` | Runs `adapters.mne_bids_feature_recipe` on an epoch-table fixture, then `adapters.mne_bids`. |
| `mne_bids_derived_features` | Calls `adapters.mne_bids` directly from an already-written `feature_table_path`/`mapping_path`. |
| `fmri_timeseries_recipe` | Runs `adapters.fmri_derivatives_feature_recipe` (`input_kind="timeseries_table"`) then `adapters.fmri_derivatives`. |
| `fmri_connectivity_matrix_recipe` | Same, `input_kind="connectivity_matrix"`. |
| `fmri_graph_summary_recipe` | Same, `input_kind="graph_summary"` (via `graph_summary_path`, not `source_paths`). |
| `fmri_derived_features` | Calls `adapters.fmri_derivatives` directly from an already-written `feature_table_path`/`mapping_path`. |
| `builtin_ds005620_cohort_summary` | Calls `evidence.builder.build_evidence_bundle(dataset="ds005620", feature_set="cohort_summary", ...)` against this repo's own committed `contracts/btc_icft/ds005620/pitnn_cohort/`. |
| `builtin_ds005620_spatial_defect_map` | Same, `feature_set="spatial_defect_map"`. |
| `builtin_ds000245_schaefer100_motcorr` | Same, `dataset="ds000245"`, `feature_set="schaefer100_motcorr"`, against `contracts/fmri_tda/ds000245/`. |
| `builtin_ds000245_kmeans100` | Same, `feature_set="kmeans100"`. |

**`mne_bids_bids_raw_recipe` is intentionally not supported in v1** --
unlike the other ten modes, it requires synthesizing/reading a real MNE
`Raw` file, a materially riskier code path than thin orchestration over
already-tested library functions. A spec with this `input_mode` fails
validation with an explicit `"is a recognized mode but is unsupported in
v1"` message rather than a generic error.

## ReportPipelineSpecV1

Deterministic `pipeline_id = sha256[:16]` over `input_mode`, `dataset_id`,
`source_paths`, `recipe_spec_path`, `feature_table_path`, `mapping_path`,
`output_root` -- `created_at`, `pipeline_name`, `limitations`,
`provenance`, and every other free-text field are excluded, so
re-specifying the same request always yields the same `pipeline_id`.

14 validation rules (`ReportPipelineSpecV1.validate()`), the ones that
most directly gate correctness:

- Rule 1: `pipeline_id` must match the deterministic ID.
- Rule 3/4: `input_mode` is required and must be one of the 11 recognized
  modes; the 10 supported ones validate cleanly, the 1 known-but
  -unsupported one fails with an explicit message.
- Rule 6: `output_root` must be a safe relative path under `outputs/` or
  `data/` (string-level check here; the real traversal/containment safety
  check is `dataset_acquisition.store.validate_target_root`, applied at
  write time in `workflows.store`).
- Rule 7: every path field `REQUIRED_FIELDS_BY_MODE` declares for the
  given `input_mode` must be present (non-empty) -- file *existence* is
  checked by the runner at execution time, not here (`validation.py`
  stays side-effect-free, matching every other validation module in this
  repository).
- Rule 11: the shared banned-phrase scanner
  (`phase_space.coordinate.scan_banned_phrases`, which already includes
  `transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES`) plus a small
  additive `REPORT_PIPELINE_EXTRA_BANNED_PHRASES` tuple
  (`"is clinical evidence"`, `"confirms diagnosis"`).

## ReportPipelineRunManifestV1

`run_id` is content-addressed but documents one execution event
(`created_at` is part of the hash basis) -- mirrors
`compute_manifest_id` in both feature-recipe schemas, not required to
match across separate real-world runs. Records `steps_planned` (computed
from `input_mode` before execution) against `steps_completed`/
`steps_skipped` (the actual outcome), plus every generated path
(`generated_feature_paths`, `generated_mapping_paths`,
`transition_record_paths`, `phase_space_paths`, `evidence_bundle_paths`,
`evidence_report_paths`, `report_pack_path`, `registry_updated_path`).
`execution_status` is one of `dry_run`/`completed`/
`completed_with_warnings`/`failed`. On failure, the manifest is still
written -- `run_report_pipeline` never crashes on a missing input or a
downstream adapter/evidence error; it records the failure in `errors` and
returns.

## ReportPackV1

Deterministic `report_pack_id = sha256[:16]` over `dataset_id`,
`input_mode`, `evidence_bundle_ids`, `evidence_report_ids` --
`created_at`, `summary`, `artifact_manifest`, and every other
execution-detail field are excluded. Only written when a run actually
produced or referenced an `EvidenceBundleV1`/`EvidenceReportV1` (a
bare feature-extraction run with `include_evidence_bundle=False` and
`include_report=False` gets a manifest but no report pack -- there is
nothing yet to index).

Carries no `claim_scope`/`evidence_level` field of its own -- `summary`
only *copies* the ceilings already recorded on the referenced
`EvidenceBundleV1` (see `workflows.validation.validate_report_pack`,
which explicitly rejects a pack that grows either field).
`blocked_interpretations` is a fixed, deterministic list
(`workflows.report_pack.blocked_interpretations_template`), mirroring
`reports.evidence_report._blocked_claims_template`'s convention.

## Output structure

```
<output_root>/
    PipelineSpec.json
    PipelineRunManifest.json
    ReportPack.json                 (only when evidence was produced/referenced)
    recipe_output/                  (*_recipe modes only: derived_features.csv,
                                      mapping.json, recipe_manifest.json,
                                      summary.json -- written by the reused
                                      recipe's own write_recipe_outputs(), unmodified)
    adapter_export/                 (modes that reach TransitionRecordV1:
                                      transitions/, phase_space/,
                                      EvidenceBundle.json, EvidenceReport.md/json,
                                      registry_updated.json -- written by the
                                      reused adapter/evidence functions, unmodified)
    reports/                        (existing_evidence_bundle mode only:
                                      EvidenceReport.md/json referencing the
                                      externally-supplied bundle)
```

This deviates from the illustrative `features/`/`mappings/`/
`transitions/`/`phase_space/`/`evidence/`/`reports/` split sketched as
one possible layout for this kind of runner, in favor of never
re-implementing the adapters'/recipes' own directory conventions -- the
[Core principle](#core-principle) applies to I/O layout, not only
computation. Every generated path is still recorded explicitly, by
relative path, in `ReportPipelineRunManifestV1`/`ReportPackV1`, so the
manifest -- not a folder name -- is the authoritative index. `output_root`
is the literal target directory the caller supplies (matching
`adapters.mne_bids_feature_recipe`/`adapters.fmri_derivatives_feature_recipe`'s
own `--out` convention) -- the runner never auto-nests under a fixed
`outputs/report_packs/<pipeline_id>/` prefix on the caller's behalf.

## CLI

```
python -m workflows.export_report_pack --spec pipeline_spec.json

python -m workflows.export_report_pack --spec pipeline_spec.json \
    --out outputs/report_packs/my-demo --dry-run

python -m workflows.export_report_pack --spec pipeline_spec.json \
    --registry benchmarks/registry_seed.json \
    --include-phase-space --include-evidence-bundle --include-report --include-html
```

`--dry-run`/`--out`/`--include-*`/`--registry` override the corresponding
spec field for this invocation only -- the spec file on disk is never
mutated. Prints `run_id`, `pipeline_id`, `input_mode`, `dataset_id`,
`status`, `steps_completed`/`steps_skipped`, `output_root`, and every
generated evidence-bundle/report path. Fails clearly (non-zero exit,
`"FAILED: ..."` message, or a JSON payload with
`"status": "failed"` and populated `errors`) on: missing/invalid spec,
unsupported `input_mode`, invalid output root, or a missing input file.

## Dry-run behavior

`dry_run=True` (or `--dry-run`) validates the spec, computes
`steps_planned` from `input_mode`, and writes only `PipelineSpec.json` +
`PipelineRunManifest.json` (`execution_status="dry_run"`,
`steps_completed=[]`, every planned step listed in `steps_skipped`) --
no recipe, adapter, evidence, or report call is ever made, and no
`recipe_output/`/`adapter_export/`/`reports/`/`ReportPack.json` is
written. Verified directly:
`test_dry_run_does_not_generate_scientific_outputs`.

## Demo fixtures

`tests/fixtures/report_pipeline_demo.py` follows
`tests/fixtures/make_synthetic_bids.py`'s established convention:
generator *functions* a test calls to write tiny fixtures into a
caller-supplied directory (usually `tmp_path`), not pre-baked static
files -- nothing here can drift stale against a schema change, and
nothing here is a tracked output artifact
(`tests/fixtures/README.md`: "keep fixtures small and deterministic,
prefer inline fixture creation when practical"). Covers all five demo
artifacts the mission's Phase F asks for: an MNE/BIDS epoch-table recipe
spec + epoch table, an MNE/BIDS derived feature table + mapping, an fMRI
timeseries-recipe spec + input, an fMRI graph-summary-recipe spec +
input, an fMRI derived feature table + mapping, and a real (not
fabricated) existing `EvidenceBundleV1` built from this repository's own
already-committed `contracts/btc_icft/ds005620/pitnn_cohort/` artifacts
via `evidence.builder.build_evidence_bundle` -- no raw data download, no
synthetic transition records.

## Commercial/productized-report relevance

This is the first layer in this repository shaped for a non-engineer
user: one spec file in, one indexed report pack out, without needing to
know that `adapters.mne_bids_feature_recipe`, `adapters.mne_bids`,
`evidence.builder`, and `reports.evidence_report` are four separate
modules with four separate CLIs. `ReportPackV1.reproducibility_commands`
and `artifact_manifest` make every generated file traceable back to the
exact invocation that produced it -- the baseline a future paid/hosted
report-generation product would need before adding anything else.

## Future SaaS/API worker relevance

`run_report_pipeline(spec) -> ReportPipelineRunManifestV1` is a plain
Python function with no CLI/filesystem-argv coupling beyond the spec
object itself -- a future queue worker can call it directly with a spec
built from an API request body, exactly as `workflows.export_report_pack`
already does from parsed CLI args. `ReportPipelineSpecV1`/
`ReportPipelineRunManifestV1`/`ReportPackV1` are all already
JSON-serializable, so a worker's job payload and result payload need no
new serialization layer.

[docs/job_runner.md](job_runner.md) builds the first layer of this: a
tracked, file-backed job around one `run_report_pipeline` call (job
status, a job store, a lock, a CLI, and an optional local API), without
yet adding a real queue or authentication.

## How a report pack differs from evidence

A `ReportPackV1` is not itself evidence -- it is a deterministic index
over artifacts that were already governed before this milestone existed
(`TransitionRecordV1`/`PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/
`EvidenceReportV1`). `summary.claim_scope_ceiling`/
`evidence_level_ceiling` are copied verbatim from the referenced
`EvidenceBundleV1`, never computed or promoted by this runner.
`blocked_interpretations` is always non-empty and always includes an
explicit statement that the pack is not clinical evidence. See
[docs/governed_evidence_bundles.md](governed_evidence_bundles.md) and
[docs/evidence_report_generator.md](evidence_report_generator.md) for
where the actual scientific/governance claims a report pack references
are made and bounded.

## HTML report packs

`--include-html` (or `include_html=True` on the spec) renders a
deterministic, static `index.html` from the run's `ReportPackV1` once it
completes -- see
[docs/html_report_pack_renderer.md](html_report_pack_renderer.md). This
is the first shareable, non-technical artifact this runner produces;
default behavior (no `--include-html`) is unchanged.

## Limitations

- `mne_bids_bids_raw_recipe` is not supported in v1 (see above).
- `--updated-registry-out` is accepted by the CLI for interface parity
  with the underlying adapters but is currently informational only --
  this runner always writes registry updates under the deterministic
  `<out>/adapter_export/registry_updated.json` path so every artifact a
  report pack references stays under one root.
- A report pack references artifacts produced by the single pipeline run
  that created it -- there is no cross-run or cross-dataset aggregation
  in v1.
- No HTML/PDF rendering of a report pack exists yet -- `ReportPack.json`
  is a structured index, not a formatted document (the underlying
  `EvidenceReport.md` already provides a human-readable Markdown summary
  of the evidence bundle itself).

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **HTML/PDF rendering** of a `ReportPackV1` (and its referenced
  `EvidenceReportV1`) into a single shareable document.
- **SaaS upload worker** -- a queue consumer that calls
  `run_report_pipeline` from an API request payload and uploads the
  resulting report pack to a customer-facing store.
- **Holo-Atlas evidence viewer consumption** -- once a real visualization
  layer exists, it would consume `ReportPackV1`/`EvidenceBundleV1`
  output, never raw derived features.
- **Benchmark-pack generator** -- a curated collection of report
  pipelines assembled into one indexed pack. Now implemented -- see
  [docs/benchmark_pack_generator.md](benchmark_pack_generator.md).
- **Richer QC and topology backends** -- once the underlying recipes gain
  them (see `docs/mne_bids_feature_recipe.md#future-work` and
  `docs/fmri_derivatives_feature_recipe.md#future-work`), this runner
  would pick them up automatically without any change of its own, since
  it never duplicates their logic.

This milestone does not imply clinical validity for any artifact it
references, does not imply consciousness or spiritual-state detection
regardless of a dataset's subject matter, and does not imply that a
generated `ReportPackV1` is clinical evidence -- evidence begins at
`adapters.*`/`evidence.builder`/`reports.evidence_report`, exactly as it
did before this milestone; this runner only indexes it.
