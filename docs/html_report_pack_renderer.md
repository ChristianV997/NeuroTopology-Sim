# Static HTML Report Pack Renderer v1

Status: **implemented.** This document describes the
`workflows.html_report_pack`/`workflows.html_renderer`/
`workflows.html_validation`/`workflows.export_html_report_pack` modules
as they exist today. It does not describe, and should not be read as
promising, any of the capabilities listed in [Future work](#future-work)
-- those are explicitly out of scope for this milestone.

This is a **presentation and packaging layer**, not a new analysis
milestone -- it turns an existing `ReportPackV1` (and, if present, its
linked `EvidenceReportV1`/`EvidenceBundleV1` artifacts) into a
shareable, self-contained static web page.

```
ReportPipelineSpecV1
        |
        v   run_report_pipeline()
ReportPackV1  (+ linked EvidenceReport.md/json, EvidenceBundle.json)
        |
        v   workflows.html_report_pack.render_html_report_pack (THIS MILESTONE)
index.html + HtmlReportPack.json (+ copied artifacts/)
```

## What it does

Given an already-built `ReportPackV1` JSON file, `render_html_report_pack`
reads it (and, optionally, a `ReportPipelineRunManifestV1` and the
`EvidenceReportV1`/`EvidenceBundleV1` JSON/Markdown files it references),
renders one deterministic, static `index.html`, and writes
`HtmlReportPack.json` alongside it -- a small, indexable record of the
render itself (`html_pack_id`, section list, copied-artifact list,
validation summary).

## What it does not do

- **No new scientific analysis, no reinterpretation.** Every number shown
  on the page was already computed by `evidence.builder`/
  `reports.evidence_report`/`workflows.report_pipeline` before this
  module runs -- this renderer only formats already-governed dict fields.
- **No LLM call.**
- **No PDF generation.** Not trivially available without a new
  dependency (no PDF library is installed) -- see [Limitations](#limitations).
- **No JavaScript.** No `<script>` tag is ever emitted.
- **No external CDN/asset.** All CSS is one inline `<style>` block; no
  `http://`/`https://` reference exists anywhere in the generated page
  (verified by a static test: `test_no_external_assets_or_cdns`).
- **No raw HTML execution of Markdown.** `EvidenceReport.md` content, when
  embedded, is shown as `html.escape`-d text inside a `<pre>` block --
  never parsed into live HTML elements.
- **Does not promote a claim scope or evidence level.** `HtmlReportPackV1`
  carries no `claim_scope`/`evidence_level` field of its own; see
  [How this differs from evidence](#how-this-differs-from-evidence).

## Why it is deterministic and static

`workflows.html_renderer.render_index_html` is a pure function: the same
`ReportPackV1`/`EvidenceReportV1`/`EvidenceBundleV1` input (and the same
fixed `created_at` instant) always produces byte-identical HTML --
mirrors `reports.renderer.render_markdown`'s own determinism guarantee
exactly (verified by `test_deterministic_output_across_repeated_renders`,
which renders the same source pack twice and diffs the output modulo the
`Generated:` timestamp line). "Static" here means the output is a plain
HTML file with no server, no build step, and no client-side computation
-- open it in any browser, or serve it from GitHub Pages/any static host,
and it renders identically every time.

## Architecture: why `workflows/`, not `reports/`

`ReportPackV1`/`ReportPipelineSpecV1`/`ReportPipelineRunManifestV1`/the
existing `--include-report`/`--include-evidence-bundle`/
`--include-phase-space` flag family already live in `workflows/` (see
`docs/report_pipeline_runner.md`). This milestone is a direct extension
of that same "product/commercial workflow layer" concept -- it consumes a
`ReportPackV1` specifically, not an `EvidenceBundleV1` directly the way
`reports.evidence_report` does -- so it belongs beside `report_pack.py`/
`report_pipeline.py`, not inside `reports/` (which is scoped to
`EvidenceReportV1` generation and stays untouched by this milestone).

## Files

```
workflows/
    html_report_pack.py         HtmlReportPackV1 schema + render_html_report_pack() orchestration
    html_renderer.py              pure, stdlib-only HTML string builder (render_index_html)
    html_validation.py            structural validation + banned-phrase scan
    export_html_report_pack.py  CLI: python -m workflows.export_html_report_pack
```

## Open-source/stdlib audit

No `jinja2`, `markdown`, or any HTML/templating package is declared in
`requirements.txt` or installed in this environment (`import jinja2`/
`import markdown` both fail). Per the mission's own guidance, this
milestone implements a small stdlib-only renderer using `html.escape` and
deterministic Python f-string templates -- no new dependency was added.

## `HtmlReportPackV1` schema

Deterministic `html_pack_id = sha256[:16]` over `report_pack_id`,
`dataset_id`, `input_mode`, `source_evidence_report_paths`, and
`template_version` -- `created_at`, `title`, `limitations`, and every
other free-text field are excluded. `template_version`
(`"workflows.html_renderer v1"`) participates so a future renderer
template change deliberately yields a new id rather than silently
overwriting a page built with different rendering logic (mirrors
`phase_space.coordinate.ESTIMATOR_VERSION`'s role in `coordinate_id`).

12 validation rules (`HtmlReportPackV1.validate()` plus a separate
filesystem-touching check, see below):

- Rule 1/2: `limitations`/`blocked_interpretations` must be non-empty.
- Rule 3: `source_report_pack_path` is required.
- Rule 5: `output_root` must be a safe relative path under `outputs/` or
  `data/` (string-level check; the real traversal/containment safety
  check is `dataset_acquisition.store.validate_target_root`, applied at
  write time).
- Rule 9/11: the shared banned-phrase scanner
  (`phase_space.coordinate.scan_banned_phrases`, which already includes
  `transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES`) plus
  `workflows.validation.REPORT_PIPELINE_EXTRA_BANNED_PHRASES` and one
  small renderer-specific addition.
- Rule 10: `HtmlReportPackV1` must not carry its own `claim_scope`/
  `evidence_level` field.

Rules 3/4 also have a **filesystem-touching** counterpart,
`workflows.html_validation.validate_source_artifacts_exist`, kept
deliberately separate from `.validate()` so the schema's own structural
check stays side-effect-free (matching every other `validate()` method in
this repository). An empty `source_evidence_report_paths`/
`source_evidence_bundle_paths` list is a valid "no report/bundle was
generated for this run" state, not an error -- only a *declared* path
that does not resolve on disk is an error.

## HTML rendering behavior

`render_index_html` emits 15 sections in deterministic order: header/
title/status, executive summary, evidence chain, registry/authorization
summary, transition summary, phase-space summary, null-control summary,
claim/evidence ceiling summary, validation summary, limitations, blocked
interpretations, reproducibility commands, generated artifact manifest,
download/view artifact links, and future work. Sections 4-9 read directly
from the linked `EvidenceReportV1`'s own already-computed dict fields
(`registry_summary`, `transition_summary`, `phase_space_summary`,
`null_control_summary`, `claim_scope_summary`/`evidence_level_summary`,
`validation_summary`) when an evidence report was generated for this run;
when it was not, they fall back to the coarser fields already present on
`ReportPackV1.summary` and clearly say so rather than silently omitting
the section. A visible `research-use / exploratory artifact` disclaimer
banner is rendered directly under the title on every page, phrased to
avoid tripping this repository's own banned-phrase scanner while still
being unambiguous (e.g. "does not represent a validated consciousness
biomarker" rather than the literal banned substring "validated
biomarker" -- the same safe-construction convention
`reports.evidence_report._blocked_claims_template` already established).

Every source-derived value is passed through `html.escape` before being
placed in the page (`test_escapes_unsafe_text` injects
`<script>alert(1)</script>` into a copy of the source `ReportPack.json`
and confirms it survives only as `&lt;script&gt;`). After the full page
is assembled, `scan_html_for_banned_phrases` runs once more over the
complete rendered string; a hit raises `HtmlReportPackError` and the page
is never written -- this is a defense-in-depth check beyond the
per-field scan already applied when `HtmlReportPackV1.validate()` runs.

## Artifact-copy/linking behavior

`copy_artifacts=True` (default) copies `ReportPack.json`, the
`PipelineRunManifest.json` (if given), every declared
`EvidenceReport.md`/`EvidenceReport.json`, and every declared
`EvidenceBundle.json` into `<out>/artifacts/` alongside `index.html`, and
records each copied path in `HtmlReportPackV1.copied_artifact_paths`.
Each candidate file is checked against a defensive 5 MB ceiling before
copying (`_MAX_COPIED_ARTIFACT_BYTES`) -- oversized files are skipped and
recorded as a warning, never silently copied; this is a ceiling far above
any real `ReportPack.json`/`EvidenceReport.json`/`EvidenceBundle.json`
this repository produces, not an expectation any of them should approach.
**Only these already-governed JSON/Markdown artifact types are ever
copied -- raw data (`transitions/`, `phase_space/`, `recipe_output/`
directories, or anything under `data/`) is never copied into an HTML
report-pack directory.**

`--no-copy-artifacts` (or `copy_artifacts=False`) instead writes the
"Download / view artifacts" section as plain repository-relative paths
(`<code>` text, not clickable links, since the exact relative path from
an arbitrary future hosting location back to the original repository
path cannot be computed reliably) -- useful when the source artifacts
will be published or served from elsewhere.

## Report pipeline integration behavior

`ReportPipelineSpecV1` gained two additive fields: `include_html: bool =
False` and `html_out: Optional[str] = None` (defaults to
`<output_root>/html` when `include_html=True` and `html_out` is not
given). Neither field participates in `pipeline_id`'s identity basis, so
adding them is fully backward-compatible with specs written before this
milestone. When `include_html=True` and a `ReportPackV1` was actually
produced, `run_report_pipeline` calls `render_html_report_pack`
**after** the pipeline's own manifest has already been written once
(mirroring `evidence.builder.build_evidence_bundle`'s own "write once,
optionally augment metadata, re-write" pattern for its `include_report`
step) -- `ReportPipelineRunManifestV1.metadata["html_report_pack"]` is
set additively (`html_pack_id`, `index_html_path`,
`html_pack_json_path`), never as a new top-level schema field, and the
manifest is re-written once more to persist it.

If HTML rendering itself fails (e.g. a linked artifact went missing
between pipeline completion and render time), the failure is recorded as
a `manifest.warning` and `execution_status` becomes
`"completed_with_warnings"` -- the already-valid `ReportPackV1` and its
underlying evidence are not discarded over a presentation-layer problem.
**A pipeline run that itself failed never reaches this code path at
all** -- `run_report_pipeline`'s failure branch returns before a
`ReportPackV1` ever exists, so there is no "fake" HTML pack rendered from
a failed run (verified: `test_failed_pipeline_does_not_render_html`).
Default behavior (`include_html` omitted or `False`) is completely
unchanged from `docs/report_pipeline_runner.md`'s existing documented
behavior (verified: `test_default_without_include_html_is_unchanged`).

## CLI usage

```bash
# standalone: render HTML from an already-built ReportPack.json
python -m workflows.export_html_report_pack \
    --report-pack outputs/report_packs/my-demo/ReportPack.json \
    --pipeline-manifest outputs/report_packs/my-demo/PipelineRunManifest.json \
    --out outputs/report_packs/my-demo/html

# run the pipeline and render HTML in one invocation
python -m workflows.export_report_pack --spec pipeline_spec.json \
    --include-report --include-html
```

Optional flags: `--pipeline-manifest <path>`, `--copy-artifacts`/
`--no-copy-artifacts` (mutually exclusive; default is to copy),
`--title "..."`. Fails clearly (non-zero exit, `"FAILED: ..."` message)
on: missing `--report-pack`, invalid output root, a missing linked
artifact, or a banned-phrase hit in the rendered output.

## Output structure

```
<out>/
    index.html
    HtmlReportPack.json
    artifacts/                  (only when copy_artifacts=True)
        ReportPack.json
        PipelineRunManifest.json  (only if --pipeline-manifest was given)
        EvidenceReport.md
        EvidenceReport.json
        EvidenceBundle.json
```

## How this supports productized reports, demos, and outreach

- **Paid research reports / methods-paper supplements**: `index.html` is
  a single self-contained file (aside from the small `artifacts/`
  sidecar directory) that opens in any browser with no server, matching
  what a lab or a paying customer would expect to receive and archive.
- **GitHub Pages / static hosting**: no build step, no server-side code,
  no external asset fetch -- the output directory can be committed to a
  `gh-pages` branch or uploaded to any static host as-is.
- **SaaS previews**: `render_html_report_pack` is a plain Python function
  callable from a future queue worker exactly as `run_report_pipeline`
  already is (see `docs/report_pipeline_runner.md`'s "Future SaaS/API
  worker relevance" section) -- no CLI/filesystem-argv coupling beyond
  the function's own arguments.
- **Collaborator outreach / lab demos**: the visible disclaimer banner,
  always-non-empty limitations/blocked-interpretations sections, and
  embedded reproducibility commands mean a page can be shared without a
  verbal caveat -- the page states its own scope.

## How this differs from evidence

`HtmlReportPackV1` carries no `claim_scope`/`evidence_level` field of its
own -- the "Claim / evidence ceiling summary" section only *displays*
values already present on the referenced `ReportPackV1.summary`/
`EvidenceReportV1.claim_scope_summary`/`evidence_level_summary`, verbatim,
never computed or promoted here. The visible disclaimer banner and the
non-empty `blocked_interpretations` list (copied from the source
`ReportPackV1`) make this explicit on every rendered page: **this HTML
page is a deterministic, static rendering of already-governed output,
not clinical evidence, not a validated biomarker, and not a new
scientific result.**

## Limitations

- No PDF export -- no PDF-generation library is installed, and adding one
  was out of scope for this milestone (see [Future work](#future-work)).
- `--no-copy-artifacts` links are plain text, not clickable `<a href>`
  elements, since a reliable relative path cannot be computed for an
  arbitrary future hosting location.
- Only the first evidence-report/bundle JSON found in
  `ReportPackV1.artifact_manifest` is used to populate the richer
  sections (registry/transition/phase-space/claim summaries) -- a report
  pack referencing more than one evidence report (not currently possible
  via any supported `workflows.report_pipeline` input mode) would only
  surface the first.
- The 5 MB per-artifact copy ceiling is a defensive default, not
  independently configurable via the CLI in this milestone.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **PDF export** of a rendered report pack (would require either a new
  dependency or an external CLI tool such as a browser print-to-PDF
  invocation -- neither is wired in).
- **Richer styling** -- charts/sparklines for transition/phase-space
  summaries, a proper design system, dark-mode toggle beyond the current
  `color-scheme: light dark` CSS hint.
- **Holo-Atlas evidence viewer** consumption of `ReportPackV1`/
  `EvidenceBundleV1` output (not implemented, no design commitment --
  see `docs/governed_evidence_bundles.md`).
- **Hosted SaaS preview** -- a web endpoint serving rendered report packs
  directly, building on the plain-function `render_html_report_pack`
  entry point already established here.
- **Signed report archives** -- a checksum/signature manifest over the
  `artifacts/` directory for tamper-evident sharing.
- **Multi-report comparison dashboards** across several pipeline runs or
  datasets -- this milestone renders exactly one report pack per page.

This milestone does not imply clinical validity for any artifact it
displays, does not imply consciousness or spiritual-state detection
regardless of a dataset's subject matter, does not imply that a rendered
HTML page is clinical evidence, and does not imply that any new
scientific analysis was performed -- every value shown already existed in
the referenced `ReportPack.json`/`EvidenceReport.json`/
`EvidenceBundle.json` files before this renderer ran.
