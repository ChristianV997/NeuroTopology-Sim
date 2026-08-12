# Benchmark Pack Generator v1

Status: **implemented.** This document describes the `benchmark_packs/`
package as it exists today. It does not describe, and should not be read
as promising, any of the capabilities listed in [Future
work](#future-work) -- those are explicitly out of scope for this
milestone.

This is the bridge from individual report jobs
([docs/job_runner.md](job_runner.md), [docs/job_worker.md](job_worker.md))
to public demo packs, methods-paper supplements, and productized sample
packs: a curated collection of `ReportPipelineSpecV1` entries, executed
through `job_runner`'s existing batch/worker infrastructure, indexed into
one deterministic `BenchmarkPackV1` with an optional static HTML page.

```
BenchmarkPackSpecV1 (curated collection of ReportPipelineSpecV1 entries)
        |
        v   benchmark_packs.builder.build_benchmark_pack()
        |     -- job_runner.batch.create_batch_from_specs() (one job per spec)
        |     -- job_runner.batch.run_batch() (if spec.run_immediately)
        v
BenchmarkPackV1  (report_pack_ids / html_pack_ids / execution_summary / coverage_summary)
        |
        v   benchmark_packs.renderer.render_benchmark_pack_index()  (if spec.include_html)
        v
BenchmarkPackIndexV1 + static index.html
```

## What benchmark packs are

A `BenchmarkPackV1` is a deterministic index over a curated set of
already-executed `ReportPipelineSpecV1` runs -- which report packs/HTML
packs were produced, from which datasets/modalities/input modes, with
what execution outcome. It exists to answer "what does this repository's
report-pipeline output look like, for a chosen curated set of pipelines,
in one place" -- for a public demo, a methods-paper supplement, a
collaborator handoff, or a productized sample pack.

## What benchmark packs are not

- **Not new evidence.** A benchmark pack does not compute anything --
  every report pack it references was already produced by
  `job_runner.runner.run_pipeline_job`/`workflows.report_pipeline.run_report_pipeline`
  before the pack was assembled. `BenchmarkPackV1` carries no
  `claim_scope`/`evidence_level`/`validation_ready` field of its own
  (`benchmark_packs.validation` explicitly rejects one if added), and its
  `blocked_interpretations` always state that including a report pack in
  a benchmark pack adds no evidentiary weight.
- **Not `BenchmarkRegistry`.** `benchmarks.export_registry.BenchmarkRegistry`
  (and `benchmarks.dataset_registry.DatasetRecordV1`/
  `benchmarks.artifact_registry.ArtifactRecordV1`) is this repository's
  **data-governance** layer -- dataset-use tracking, split/holdout
  enforcement, contamination locks. `BenchmarkPackV1` is an unrelated
  **product artifact** -- a curated collection of report packs. Neither
  reads nor writes the other; a benchmark pack does not register a
  dataset as used, and the dataset registry does not gate what a
  benchmark pack may include. This is why `benchmark_packs/` is a
  top-level package (sibling to `workflows/`/`job_runner/`) rather than
  nested under `benchmarks/`.
- **No new scientific logic, no dataset download, no raw preprocessing.**
  `benchmark_packs.builder` only calls
  `job_runner.batch.create_batch_from_specs`/`run_batch` (which
  themselves call `job_runner.store.JobStore.create_job`/
  `job_runner.runner.run_pipeline_job` unmodified).
- **No seed-registry mutation.** `benchmark_packs/*.py` never call a
  registry's `.save(...)`/construct a `SeedRegistry` themselves -- a
  source-guard test (`test_benchmark_pack_builder_never_touches_seed_registries`)
  asserts this directly.
- **No authenticated API, no hosted dashboard, no PDF export.**

## Pack spec structure

`BenchmarkPackSpecV1` is a pure request/definition object (mirrors
`ReportPipelineSpecV1` itself -- content-addressed, no `created_at`
field): `pack_name`, `pack_purpose`, `pack_kind` (`demo_pack`/
`methods_supplement`/`internal_regression_pack`/`commercial_sample_pack`/
`benchmark_candidate_pack`), `pipeline_specs` (embedded
`ReportPipelineSpecV1` dicts) and/or `pipeline_spec_paths` (file paths),
`requested_outputs`, `jobs_root`/`output_root`, `include_html`,
`run_immediately`, `max_jobs`, `limitations`, `provenance`, `metadata`.

`benchmark_pack_spec_id` is content-addressed over `pack_name`/
`pack_kind`/a stable identity handle per pipeline spec (the embedded
spec's own `pipeline_id` when a dict is embedded, or the raw path
otherwise)/`requested_outputs`/`output_root` -- building the identical
spec twice is still "the same definition"; each *build* is what carries
execution-event uniqueness (via `job_runner.batch`'s own `batch_id`).

## Default curated packs

`benchmark_packs.builder` provides three generators, all built from this
repository's own already-committed artifacts or synthetic test fixtures
-- never a download:

- **`make_builtin_demo_pack_spec`** (`pack_kind="demo_pack"`) -- the four
  already-committed `builtin_*` modes: `builtin_ds005620_cohort_summary`,
  `builtin_ds005620_spatial_defect_map` (EEG, `contracts/btc_icft/ds005620/`),
  `builtin_ds000245_schaefer100_motcorr`, `builtin_ds000245_kmeans100`
  (fMRI, `contracts/fmri_tda/ds000245/`). Each `builtin_*` mode's own
  evidence/claim ceiling is preserved unmodified -- this generator does
  not touch that logic.
- **`make_fixture_demo_pack_spec`** (`pack_kind="internal_regression_pack"`)
  -- one synthetic EEG (`mne_bids_derived_features`) and one synthetic
  fMRI (`fmri_derived_features`) demo, generated via
  `tests.fixtures.report_pipeline_demo`'s existing generator functions.
  Explicitly marked `metadata["synthetic"]=True` and stated as synthetic
  in `limitations` -- never presented as real subject data.
- **`make_methods_supplement_pack_spec`** (`pack_kind="methods_supplement"`)
  -- one EEG + one fMRI builtin mode, a narrower cross-modality selection
  intended as a methods-paper supplement.

## Build behavior

`benchmark_packs.builder.build_benchmark_pack(spec) -> BenchmarkPackV1`:

1. Validates `spec`.
2. Materializes any embedded `pipeline_specs` dicts to files under
   `<output_root>/pipeline_specs/` (the in-memory `spec` object itself is
   never mutated), combined with any `pipeline_spec_paths`.
3. Creates one job per spec via `job_runner.batch.create_batch_from_specs`
   -- never executes yet.
4. If `spec.run_immediately`, runs that batch via `job_runner.batch.run_batch`.
5. Reads back every job's `PipelineJobV1`/`PipelineJobResultV1` to
   collect dataset/modality/input-mode coverage and
   `report_pack_id`/`html_pack_id` (only for jobs that actually produced
   one -- a failed or not-yet-run job contributes nothing here, never a
   fabricated id or path).
6. Assembles `BenchmarkPackV1`, with `execution_summary["status"]` one of
   `not_run`/`completed`/`failed`/`completed_with_failures` depending on
   the per-job outcomes.
7. If `spec.include_html` and at least one HTML report pack was
   produced, renders the pack's own static index
   (`benchmark_packs.renderer.render_benchmark_pack_index`).
8. Writes `BenchmarkPack.json` under `output_root`.

A pack built without `run_immediately` still returns a valid
`BenchmarkPackV1` -- `execution_summary["status"]="not_run"`,
`report_pack_ids`/`html_pack_ids` empty, `job_ids` populated -- a
"planned" summary a caller can inspect or hand off to
`job_runner.export_worker`/`job_runner.batch.run_batch` later.

## Static index behavior

`benchmark_packs.renderer.render_index_html(pack) -> (html_text, sections_rendered)`
is a pure function: 11 required sections (Purpose, Execution summary,
Datasets/modalities/input modes included, Report packs, HTML report
links, Coverage summary, Limitations, Blocked interpretations,
Reproducibility commands, Generated artifact manifest, Future work),
every source-derived value passed through `html.escape`, no external
CSS/JS/CDN, no `<script>` tag at all. Rendering the same pack twice
produces byte-identical HTML.

`render_benchmark_pack_index(pack, out_dir)` scans the rendered HTML for
banned phrases before writing -- refuses to write (raises
`BenchmarkPackStoreError`) if any are found, mirroring
`workflows.html_report_pack`'s own render-then-scan-then-write
discipline -- then writes `index.html` and returns a validated
`BenchmarkPackIndexV1`. Links only to artifact paths already present on
`pack` (`generated_report_pack_paths`/`generated_html_paths`) -- never a
raw data file, and never a link for a report/HTML pack that was not
actually produced.

## CLI

```bash
python -m benchmark_packs.export_benchmark_pack create-spec \
    --kind demo_pack --out outputs/benchmark_packs/demo_pack_spec.json \
    --output-root outputs/benchmark_packs/demo_pack

python -m benchmark_packs.export_benchmark_pack build \
    --spec outputs/benchmark_packs/demo_pack_spec.json

python -m benchmark_packs.export_benchmark_pack build-default \
    --kind demo_pack --out outputs/benchmark_packs/demo_pack --run-immediately --include-html

python -m benchmark_packs.export_benchmark_pack render-index \
    --pack outputs/benchmark_packs/demo_pack/BenchmarkPack.json
```

- `create-spec` only writes a pack spec (via one of the three default
  generators, keyed by `--kind`) -- it never creates or runs a job.
- `build` builds an already-written spec -- creates jobs, and runs them
  only if the spec's own `run_immediately` is set.
- `build-default` generates a curated default spec and builds it in one
  step; `--run-immediately`/`--include-html` are CLI-level overrides
  applied to the generated spec.
- `render-index` re-renders only the static index for an already-built
  pack -- useful after a template change, or if `include_html` was not
  set at build time.
- `create-spec`/`build-default` only support the three `pack_kind`
  values with a default generator (`demo_pack`/`internal_regression_pack`/
  `methods_supplement`) -- `commercial_sample_pack`/`benchmark_candidate_pack`
  require a hand-authored spec passed to `build` directly.
- Every subcommand fails clearly (non-zero exit, `FAILED: ...` message)
  on an invalid pack kind, an invalid output root, or an invalid pipeline
  spec.

## Output structure

```
outputs/benchmark_packs/<name>/
    BenchmarkPackSpec.json      (only written by build-default/create-spec)
    BenchmarkPack.json
    index.html                  (only if include_html and an HTML pack was produced)
    pipeline_specs/
        spec_000.json, spec_001.json, ...   (materialized from embedded pipeline_specs)
    reports/
        <input_mode>/
            ReportPack.json, html/index.html, ...   (job_runner.runner's own output layout)
```

No raw data file is ever written under `outputs/benchmark_packs/` --
every pipeline spec used by the default generators either points at this
repository's own already-committed `contracts/` artifacts or at a
synthetic fixture generated on demand.

## Guardrail policy

Every free-text field on `BenchmarkPackSpecV1`/`BenchmarkPackV1`/
`BenchmarkPackIndexV1` is scanned by `benchmark_packs.validation`'s
banned-phrase chain (the same `sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES`
+ `transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES` +
`workflows.validation.REPORT_PIPELINE_EXTRA_BANNED_PHRASES` chain
`job_runner.validation` already reuses, no new phrase literals
introduced this milestone). The rendered HTML index is scanned again
before it is ever written to disk.

## How this supports future product use

`build_benchmark_pack`/`render_benchmark_pack_index` are plain Python
functions with no CLI/filesystem-argv coupling beyond their arguments --
directly reusable for:

- **Public demos** -- `make_builtin_demo_pack_spec` + `--include-html`
  produces a shareable static page with no server.
- **Methods-paper supplements** -- `make_methods_supplement_pack_spec`.
- **Productized report samples** -- a `commercial_sample_pack` spec
  hand-authored over a curated selection of already-governed pipelines.
- **Collaborator outreach** -- the static index is a single self-contained
  artifact, matching `workflows.html_report_pack`'s own "opens in any
  browser, no server" design.
- **Future hosted benchmark gallery** -- `BenchmarkPackV1`/
  `BenchmarkPackIndexV1` are already JSON-serializable, so a future
  gallery needs no new serialization layer, only a presentation layer
  over data this milestone already produces.

## Limitations

- `create-spec`/`build-default` only cover the three `pack_kind` values
  with a default generator -- `commercial_sample_pack`/
  `benchmark_candidate_pack` are supported schema values but have no
  built-in curated spec generator in v1.
- A benchmark pack is a snapshot of one build -- there is no cross-build
  diffing or historical comparison in v1.
- The static index is a single aggregate page; it does not embed each
  individual `HtmlReportPackV1`'s own content, only links to it.
- No authenticated API exists for building/serving benchmark packs.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a
design:

- **Authenticated API** for building/serving benchmark packs.
- **Scheduled benchmark-pack regeneration**, building on
  `job_runner.worker`'s bounded loop mode.
- **Signed benchmark-pack archives**.
- **PDF export** of a benchmark pack.
- **Richer cross-report comparison dashboards**.
- **Holo-Atlas evidence viewer** consumption of `BenchmarkPackV1` output.
- **Benchmark-pack gallery** -- a static index over many verified packs
  now exists -- see [docs/benchmark_gallery.md](benchmark_gallery.md).

This milestone does not imply clinical validity for any artifact a
benchmark pack references, does not imply consciousness or
spiritual-state detection regardless of a dataset's subject matter, and
does not imply that a `BenchmarkPackV1` is clinical evidence or a
validated biomarker set -- evidence begins at
`adapters.*`/`evidence.builder`/`reports.evidence_report`, exactly as it
did before this milestone; a benchmark pack only curates and indexes
already-governed report-pipeline output.
