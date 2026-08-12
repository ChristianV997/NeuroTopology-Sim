# Benchmark Pack Verification + Gallery Index v1

Status: **implemented.** This document describes the
`benchmark_packs.verification`/`benchmark_packs.gallery`/
`benchmark_packs.gallery_renderer` modules as they exist today. It does
not describe, and should not be read as promising, any of the
capabilities listed in [Future work](#future-work) -- those are
explicitly out of scope for this milestone.

This is the bridge from "one generated benchmark pack"
([docs/benchmark_pack_generator.md](benchmark_pack_generator.md)) to a
browsable, trustworthy public demo/methods/commercial-sample gallery: a
deterministic verifier confirms a built `BenchmarkPackV1` is internally
consistent (every link resolves, every id matches, no guardrail hit, no
raw data referenced), and a gallery builder indexes multiple verified
packs into one static HTML page.

```
BenchmarkPackV1  (already built, per docs/benchmark_pack_generator.md)
        |
        v   benchmark_packs.verification.verify_benchmark_pack()
        |     -- read-only; never executes a job, never reruns a pipeline
        v
BenchmarkPackVerificationV1  (passed / passed_with_warnings / failed)
        |
        v   benchmark_packs.gallery.build_benchmark_gallery()
        |     -- verifies every pack, keeps only passed/passed_with_warnings
        v
BenchmarkGalleryV1  (verified_pack_ids / failed_pack_ids / pack_summaries)
        |
        v   benchmark_packs.gallery_renderer.render_benchmark_gallery_index()
        v
BenchmarkGalleryIndexV1 + static gallery index.html
```

## What benchmark-pack verification does

`verify_benchmark_pack(pack_path, strict=True)` loads an already-built
`BenchmarkPack.json`, checks it for internal consistency and
completeness, and returns a `BenchmarkPackVerificationV1`:

- structural validation of the pack itself (`BenchmarkPackV1.validate()`);
- recomputes `benchmark_pack_id` and compares it to the recorded value;
- confirms every `generated_report_pack_paths` entry exists and, once
  loaded, that its own `report_pack_id` is recorded in
  `pack.report_pack_ids`;
- confirms every `generated_html_paths` entry exists (optional -- see
  [Strict vs non-strict mode](#strict-vs-non-strict-mode)) and, if a
  sibling `HtmlReportPack.json` is found, that its `html_pack_id` is
  recorded in `pack.html_pack_ids`;
- confirms the pack's own static index (`generated_index_path`), if
  present, exists and is guardrail-clean;
- confirms `limitations`/`blocked_interpretations` are non-empty;
- scans every free-text field on the pack (and the rendered index HTML,
  if present) for banned phrases;
- confirms no `generated_files` entry in a linked report pack looks like
  a raw dataset path (`data/raw/...`, `data/dsNNNNNN...`).

## What it does not do

- **No job execution, no report-pipeline rerun, no scientific
  recomputation.** `verify_benchmark_pack` only reads already-written
  files and recomputes already-defined content addresses
  (`compute_benchmark_pack_id`, `ReportPackV1.report_pack_id`,
  `HtmlReportPackV1.html_pack_id`) -- a source-guard test
  (`test_verify_benchmark_pack_never_touches_seed_registries_or_jobs`)
  asserts `verification.py` never calls `run_pipeline_job`/`run_batch`.
- **Never mutates the pack it checks.** A verification is a separate,
  independently written artifact
  (`outputs/<gallery_root>/verifications/<benchmark_pack_id>.json`).
- **A "passed" verification is not a scientific validation.** It means
  the pack is internally consistent and every recorded link resolves --
  it does not upgrade any referenced artifact's `claim_scope`/
  `evidence_level`, and `BenchmarkPackVerificationV1`'s own
  `limitations` state this explicitly.

## What the gallery index does

`build_benchmark_gallery(pack_paths, output_root, ...)` verifies each
pack (unless `verify=False`), keeps only the `passed`/
`passed_with_warnings` ones in `verified_pack_ids` (everything else,
including a pack that failed to even load, goes into `failed_pack_ids`),
aggregates dataset/modality/input-mode coverage and a per-pack summary
table across the verified packs, writes `BenchmarkGallery.json`, and
renders a single static `index.html` linking every verified pack's own
index and HTML report packs.

## Difference between `BenchmarkRegistry`, `BenchmarkPackV1`, and `BenchmarkGalleryV1`

- **`benchmarks.export_registry.BenchmarkRegistry`** (and
  `benchmarks.dataset_registry.DatasetRecordV1`/
  `benchmarks.artifact_registry.ArtifactRecordV1`) is this repository's
  **data-governance** layer -- dataset-use tracking, split/holdout
  enforcement, contamination locks. It answers "has this dataset already
  been used, and how."
- **`BenchmarkPackV1`** ([docs/benchmark_pack_generator.md](benchmark_pack_generator.md))
  is a **product artifact** -- one curated collection of report-pipeline
  output. It answers "what does running these specific pipelines
  produce."
- **`BenchmarkGalleryV1`** (this milestone) is a **presentation layer**
  over multiple already-verified `BenchmarkPackV1` artifacts. It answers
  "which built packs are safe to show, and where are their links."

None of the three reads or writes either of the others. A pack being
listed in a gallery does not register a dataset as used in
`BenchmarkRegistry`, and a dataset's registry status does not gate
whether a pack can be built or verified.

## Verification checks

See [What benchmark-pack verification does](#what-benchmark-pack-verification-does)
above for the full list. Each check maps to a status field on
`BenchmarkPackVerificationV1`: `guardrail_status`, `artifact_link_status`,
`raw_data_copy_status`, `claim_promotion_status`, `reproducibility_status`,
`limitations_status`, `blocked_interpretations_status` -- each
independently `"passed"`/`"failed"`, so a caller can see exactly which
category of check failed without parsing free-text `errors`.

## Strict vs non-strict mode

`strict=True` (the default, matching `verify`/`build-gallery`/
`scan-and-build`'s default CLI behavior) treats every missing artifact --
including *optional* ones like an HTML report pack or the pack's own
static index -- as a hard failure. `strict=False` (`--non-strict` on the
CLI) downgrades a missing *optional* artifact to a warning instead
(`verification_status="passed_with_warnings"`); a missing **required**
artifact (a `generated_report_pack_paths` entry) is always a failure
regardless of strictness, since a report pack is never optional.

## Gallery output structure

```
outputs/<gallery_root>/
    BenchmarkGallery.json
    index.html
    verifications/
        <benchmark_pack_id>.json   (one BenchmarkPackVerificationV1 per pack)
```

No raw data file is ever written under the gallery output root -- the
gallery only writes its own manifest, verification records, and static
index; every link it renders points at a path already present on an
already-built `BenchmarkPackV1`.

## CLI

```bash
python -m benchmark_packs.export_gallery verify \
    --pack outputs/benchmark_packs/<name>/BenchmarkPack.json

python -m benchmark_packs.export_gallery build-gallery \
    --pack outputs/benchmark_packs/<name1>/BenchmarkPack.json \
    --pack outputs/benchmark_packs/<name2>/BenchmarkPack.json \
    --out outputs/benchmark_gallery --gallery-name "NeuroTopology Demo Gallery"

python -m benchmark_packs.export_gallery scan-and-build \
    --root outputs/benchmark_packs --out outputs/benchmark_gallery

python -m benchmark_packs.export_gallery render-index \
    --gallery outputs/benchmark_gallery/BenchmarkGallery.json
```

- `verify` prints `verification_id`/`verification_status`/errors/warnings
  as JSON; exits non-zero on `failed`.
- `build-gallery` verifies the explicitly listed packs, writes
  `BenchmarkGallery.json`, and renders the static index in one call.
- `scan-and-build` discovers every `BenchmarkPack.json` under `--root`
  (recursive glob, sorted for determinism) and builds a gallery from
  them; fails clearly if none are found.
- `render-index` re-renders only the static index for an already-built
  gallery (useful after a template change).
- `--non-strict` is accepted by `verify`/`build-gallery`/`scan-and-build`.
- Every subcommand fails clearly (non-zero exit, `FAILED: ...` message,
  or a `verification_status="failed"` JSON payload) on an invalid pack
  path, an invalid output root, or missing linked artifacts in strict
  mode.

## Static HTML policy

Mirrors `benchmark_packs.renderer`'s own policy exactly: every
source-derived value passed through `html.escape`, no external CSS/JS/CDN,
no `<script>` tag at all, rendering the same gallery twice produces
byte-identical HTML, pack summaries sorted deterministically by
`pack_name` then `benchmark_pack_id`. The rendered HTML is scanned for
banned phrases before being written -- `render_benchmark_gallery_index`
raises rather than writes if any are found.

## Guardrail policy

Every free-text field on `BenchmarkPackVerificationV1`/`BenchmarkGalleryV1`/
`BenchmarkGalleryIndexV1` is scanned by the same banned-phrase chain
`benchmark_packs.validation` already reuses from `job_runner`/
`workflows.validation` (no new phrase literals introduced this
milestone). A verification's own `guardrail_status` field records
whether the *pack it checked* passed a fresh scan -- a pack that passed
its own guardrail scan when built could still fail verification later if
someone hand-edits its `BenchmarkPack.json`.

## How this supports future product use

- **Public demo galleries** -- `scan-and-build` over a directory of
  already-built demo packs produces one shareable static page.
- **Methods-paper supplements** -- a gallery over
  `make_methods_supplement_pack_spec`-built packs.
- **Collaborator outreach** -- the gallery index is a single
  self-contained artifact, matching every other static page in this
  repository's "opens in any browser, no server" design.
- **Commercial sample packs** -- a gallery scoped to
  `commercial_sample_pack`-kind packs only.
- **Future hosted benchmark gallery** -- `BenchmarkGalleryV1`/
  `BenchmarkGalleryIndexV1`/`BenchmarkPackVerificationV1` are already
  JSON-serializable, so a future hosted gallery needs no new
  serialization layer, only a presentation layer over data this
  milestone already produces.

## Limitations

- Verification checks consistency, not truth -- it cannot detect a
  scientifically wrong number that is nonetheless internally consistent
  (correct id, existing file, guardrail-clean text).
- The raw-data-path heuristic (`looks_like_raw_data_path`) is a string
  pattern match, not a filesystem content inspection -- it catches an
  obviously mislabeled path, not a renamed raw file.
- Gallery building is a full re-verification on every call in v1 -- there
  is no verification caching keyed by pack content.
- No authenticated API exists for building/serving galleries.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a
design:

- **Signed benchmark-gallery archives**.
- **PDF export** of a gallery.
- **Scheduled gallery regeneration**, building on `job_runner.worker`'s
  bounded loop mode.
- **Authenticated hosted gallery API**.
- **Richer cross-pack comparison dashboards**.
- **Holo-Atlas evidence viewer** consumption of `BenchmarkGalleryV1` output.

This milestone does not imply clinical validity for any artifact a
verification or gallery references, does not imply consciousness or
spiritual-state detection regardless of a dataset's subject matter, and
does not imply that a `BenchmarkPackVerificationV1`/`BenchmarkGalleryV1`
is clinical evidence or a validation-ready biomarker set -- evidence
begins at `adapters.*`/`evidence.builder`/`reports.evidence_report`,
exactly as it did before this milestone; verification only checks
consistency of already-governed report-pipeline output, and the gallery
only indexes already-verified packs.
