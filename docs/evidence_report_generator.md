# Evidence Report Generator

Status: **implemented substrate, first downstream consumer of `EvidenceBundleV1`.**
This document describes the `reports/` package as it exists today. It does
not describe, and should not be read as promising, any of the future
capabilities listed in [Future work](#future-work-toward-htmlpdfsaasapi) --
those are explicitly out of scope for this milestone.

`workflows.report_pipeline` (see `docs/report_pipeline_runner.md`) calls
`reports.evidence_report.build_report` unmodified -- either indirectly
via `evidence.builder`'s `include_report` flag (recipe/derived-features/
`builtin_*` input modes), or directly for `input_mode=
"existing_evidence_bundle"`. It then indexes the resulting
`EvidenceReportV1`'s `report_id` in its own `ReportPackV1`; it never
regenerates or reinterprets report content.

## What an `EvidenceReportV1` is

`transitions/`, `phase_space/`, `benchmarks/`, and `evidence/` (see their
respective docs) together produce a governed `EvidenceBundleV1`: a
reproducible manifest of registry authorization, transition records, and
phase-space coordinates for one source artifact. Nothing before this
milestone turned that machine-oriented JSON manifest into something a
human -- a researcher, a lab evaluating the pipeline, a future paying
customer -- could actually read.

`EvidenceReportV1` is that translation. It is a **deterministic,
template-based summary** of exactly one `EvidenceBundleV1`: how many
transition artifacts and phase-space coordinates it contains, what the
registry authorized, what contamination updates were applied, what claim
scope and evidence level it carries, whether it validated cleanly, and what
it explicitly does not support. Rendered to Markdown (and mirrored as
structured JSON), it is the first artifact in this repository designed to
be read by a person outside the codebase rather than consumed by another
Python module.

**This report generates no new scientific claim.** Every number in it
already existed in the `TransitionRecordV1`/`PhaseSpaceCoordinateV1` files
the source bundle references; `reports.tables`'s aggregation functions only
count and group fields already present on already-loaded JSON dicts (see
[Report content aggregation](#report-content-aggregation)).

## How it consumes `EvidenceBundleV1`

```
EvidenceBundleV1  (already built by evidence.builder.build_evidence_bundle)
        |
        v  reports.evidence_report.build_report(bundle, bundle_path)
        |    - re-validates the bundle (evidence.validation.validate_bundle)
        |    - loads every referenced TransitionRecord.json / PhaseSpaceCoordinates.json
        |    - aggregates counts via reports.tables (no recomputation)
        v
EvidenceReportV1
        |
        v  reports.renderer.render_markdown(report)
        v
EvidenceReport.md + EvidenceReport.json
```

`reports.evidence_report.build_report` fails closed
(`ReportBuildError`) if any transition or phase-space artifact the bundle
references is missing on disk -- there is no `--summary-only` mode in this
milestone; a report can only be built from a bundle whose referenced
artifacts are actually present and readable.

## Why it is deterministic/template-based

`report_id = sha256[:16]` over `(bundle_id, report_type, template_version)`
only -- `created_at`, every summary dict, `limitations`, and
`generated_files` are excluded, mirroring
`evidence.bundle.compute_bundle_id` and
`phase_space.coordinate.compute_coordinate_id`. Rendering the same
`EvidenceReportV1` object through `reports.renderer.render_markdown` twice
produces byte-identical Markdown; building two reports from the same bundle
with the same fixed timestamp produces identical `report_id`s and identical
Markdown. This is deliberate: a report that a lab or reviewer regenerates
from the same bundle must reproduce exactly, not drift with wording changes
between runs.

## Why it is not an LLM scientific interpreter

**No LLM call is made anywhere in `reports/`.** `render_markdown` is a pure
function: fixed template strings plus verbatim values copied from the
report's own fields (which themselves were verbatim-copied or counted from
the bundle). This is a hard constraint of this milestone, not an
implementation shortcut to be lifted later without a deliberate, separately
reviewed decision -- a future Holo-Atlas LLM interpreter (still
unimplemented, see `docs/governed_evidence_bundles.md`) is explicitly a
different, not-yet-built system, and this report generator must not become
a backdoor into that capability.

## Report sections

`reports.renderer.render_markdown` emits, in order:

1. Title and status
2. Executive summary
3. Source artifact and registry authorization
4. Dataset/artifact role and contamination status
5. Transition records generated
6. Phase-space coordinates generated
7. Supported axes and insufficient-data axes
8. Null-control summary
9. Claim scope and evidence level
10. Validation summary
11. Limitations
12. Explicitly blocked interpretations
13. Reproducibility commands
14. Generated artifact manifest
15. Future work / next required validation

Sections 6/7 explicitly state `_No phase-space coordinates were requested or
generated for this bundle._` when `--include-phase-space` was not used for
the source bundle, rather than omitting the section -- insufficient data is
first-class report content, not a silently missing section.

## Report content aggregation

`reports.tables` provides the aggregation functions `build_report` calls:
`summarize_transitions` (count, record levels, `feature_set_id`(s), feature
families, source/target pairs), `summarize_phase_space` (status counts
across all four `PhaseSpaceCoordinateV1.STATUS_VALUES`, confidence counts
across all four `CONFIDENCE_VALUES`, axes estimated vs. insufficient-data --
always zero-filled for every known status/confidence, never silently
omitting a zero count), `summarize_registry`, `summarize_contamination`,
`summarize_claim_scope`, and `summarize_evidence_level`. `null_control_summary`
is copied verbatim from the bundle's own already-honest aggregation (see
`docs/governed_evidence_bundles.md`) rather than re-derived. None of these
functions import `transitions.metrics`, `phase_space.estimators`, or any
other estimator code -- they operate on plain `dict`s produced by
`json.loads`, so there is no code path by which they could recompute a
result.

## CLI usage

```bash
# generate a report from an already-built bundle
python -m reports.export_report \
    --bundle outputs/evidence/ds005620_cohort_summary/EvidenceBundle.json \
    --out outputs/evidence/ds005620_cohort_summary \
    --format markdown,json

# markdown only, or json only
python -m reports.export_report --bundle <path> --out <dir> --format markdown
python -m reports.export_report --bundle <path> --out <dir> --format json
```

### Generating reports for ds005620 and ds000245 bundles

The most common path goes through `evidence.export_bundle`'s optional
`--include-report` flag (see `docs/governed_evidence_bundles.md`), which
builds the bundle and the report in one invocation:

```bash
python -m evidence.export_bundle \
    --dataset ds005620 --feature-set cohort_summary \
    --registry benchmarks/registry_seed.json \
    --source contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/evidence/ds005620_cohort_summary \
    --include-phase-space --include-report

python -m evidence.export_bundle \
    --dataset ds000245 --feature-set schaefer100_motcorr \
    --registry benchmarks/registry_seed.json \
    --source contracts/fmri_tda/ds000245 \
    --out outputs/evidence/ds000245_schaefer100_motcorr \
    --include-phase-space --include-report
```

Default behavior without `--include-report` is unchanged -- no report is
generated, and `bundle.metadata` gets no `"report"` key. Output structure
with the flag:

```
outputs/evidence/<bundle_name>/
  EvidenceBundle.json
  EvidenceReport.json
  EvidenceReport.md
  transitions/
  phase_space/                (only with --include-phase-space)
  registry_updated.json       (only with --mark-seen)
```

`--report-out <path>` overrides the report's output directory (default: the
same directory as `--out`), for cases where the report should live
somewhere other than alongside the bundle.

### Generating a report from an `adapters.mne_bids` export

`adapters.mne_bids` (see `docs/mne_bids_adapter.md`) can produce the same
`EvidenceReport.md`/`EvidenceReport.json` pair for a lab's own derived
feature artifacts, without any `evidence.export_bundle`/
`evidence.builder.DISPATCH` entry for that dataset:

```bash
python -m adapters.mne_bids \
    --features derived_features.csv --mapping mapping.json \
    --out outputs/adapters/mne_bids/my_export \
    --registry benchmarks/registry_seed.json \
    --updated-registry-out outputs/adapters/mne_bids/my_export/registry_updated.json \
    --include-evidence-bundle --include-report
```

This calls `reports.evidence_report.build_report` exactly as
`evidence.builder.build_evidence_bundle`'s own `--include-report` does --
the only difference is the bundle upstream of it was built via
`evidence.builder.build_generic_evidence_bundle()` (see
`docs/governed_evidence_bundles.md`) rather than a `DISPATCH`-registered
exporter.

`adapters.fmri_derivatives` (see `docs/fmri_derivatives_adapter.md`) is a
second adapter producing `EvidenceReport.md`/`EvidenceReport.json` the same
way, via its own `--include-evidence-bundle --include-report` CLI flags.

## Limitations

- No downstream consumer of `EvidenceReportV1` exists yet beyond a human
  reader -- there is no automated report-comparison, report-diffing, or
  report-aggregation-across-bundles tool in this milestone.
- `reports/` reads only what `evidence.bundle.EvidenceBundleV1` and its
  referenced artifacts already contain; if the source bundle's own
  `limitations`/`null_control_summary`/ceilings are wrong, the report
  faithfully reproduces that error rather than catching it -- this
  generator is not an independent check on the bundle's own correctness
  beyond the structural cross-references it does verify (paths exist,
  `transition_id`/`coordinate_id` references match).
- Markdown is the only fully supported rendering target; JSON is a direct
  serialization of the same `EvidenceReportV1` object. HTML/PDF rendering
  is not implemented (see [Future work](#future-work-toward-htmlpdfsaasapi)).
- `reproducibility_commands` reconstructs the bundle-build CLI invocation
  from `bundle.metadata`/`bundle.artifact_paths`; if a bundle was built via
  the library function directly (not the CLI) with arguments that don't map
  cleanly to a flag, the reconstructed command is a best-effort
  approximation, not a guaranteed byte-exact replay.

## Blocked interpretations

Every `EvidenceReportV1.blocked_claims` list is a fixed, non-empty template
(`reports.evidence_report._blocked_claims_template`), not derived from
bundle-specific content, stating explicitly that the report does not
support: a clinical claim; a diagnostic claim; a treatment claim; a claim
that any coordinate/transition artifact is a validated consciousness
biomarker; a claim of spiritual/meditative attainment; a mechanistic-causal
claim; meditation-stage, jhāna, or cessation identification; an
enlightenment-related claim; or a cross-dataset replication/final-claim-
confirmation beyond what the source bundle's own registry decisions
authorized. As with every other layer in this repository, all free text on
a report (`limitations`, `blocked_claims`, `report_title`, `metadata`,
`reproducibility_commands`) is recursively scanned against the shared
banned-phrase list (`phase_space.coordinate.scan_banned_phrases`, itself
built on `sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES` and
`transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES`), and validation
fails closed on a hit.

## Future work toward HTML/PDF/SaaS/API

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **HTML rendering.** `render_markdown`'s section structure is designed to
  translate directly to HTML (or a static-site generator) without a schema
  change; no HTML renderer exists yet.
- **PDF export.** Would most naturally sit on top of an HTML renderer, once
  one exists.
- **SaaS/API delivery.** A future service (upload derived artifacts →
  governed bundle → guarded report) would call `evidence.builder.build_evidence_bundle`
  and `reports.evidence_report.build_report` exactly as the CLIs do today --
  no repository code changes should be required to add an API layer on top,
  since both are already plain library functions independent of their CLI
  wrappers.
- **Productized/commercial reports.** This report's structure (executive
  summary, explicit limitations, explicit blocked interpretations,
  reproducibility commands) is deliberately shaped to be useful as a
  standalone deliverable for a lab or a methods-paper appendix -- but doing
  so does not, and must not, imply any clinical, diagnostic, or
  consciousness-detection capability; every such report still carries the
  same fixed blocked-claims list as every other report this generator
  produces.
