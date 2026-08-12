# EEGDash Metadata Scout + Dataset Opportunity Pipeline v1

Status: **implemented.** This document describes the
`dataset_opportunities` package as it exists today. It does not describe,
and should not be read as promising, any capability beyond what is listed
here.

This scout ranks opportunities. It does not create evidence. Every output
preserves uncertainty and makes clear that real analysis requires separate
acquisition, explicit mappings, bounded feature recipes, and governed report
generation.

```
DatasetCandidateRecordV1  (already built, per docs/dataset_candidate_importers.md)
        |
        v   dataset_opportunities.scoring.score_opportunity()
        v
DatasetOpportunityRecordV1  (ranked scouting opportunity)
        |
        v   dataset_opportunities.opportunity_batch.build_opportunities_from_candidates()
        v
DatasetOpportunityBatchV1  (ranked_opportunities / rejected_opportunities)
        |
        v   dataset_opportunities.planner.plan_next_actions_from_opportunities()
        v
DatasetOpportunityPlanV1  (candidate next actions -- proposals, not executions)
        |
        v   dataset_opportunities.renderer.render_opportunity_summary()
        v
Markdown scouting report
```

## Why this is a separate package from `dataset_importers`

`dataset_importers` turns a catalog entry into a `DatasetCandidateRecordV1`
(import). `dataset_opportunities` turns many already-imported candidates
into a ranked, actionable plan (opportunity ranking). These are different
concerns with different audiences -- the same reasoning that kept
`benchmark_packs/` (a product artifact) separate from `benchmarks/` (a
data-governance registry). See
[docs/benchmark_gallery.md](benchmark_gallery.md)'s own explanation of that
precedent.

## Why EEGDash metadata-only search is useful

`dataset_importers.eegdash_importer` already confirms (from the installed
`eegdash` package's own docstrings) that its catalog query methods transfer
only small JSON metadata documents, never signal bytes. This package's CLI
`eegdash-metadata-query` subcommand delegates directly to that existing,
already-safe function -- no new live-query logic is written here. A live
query still requires the caller to pass `--allow-live-metadata-query`
explicitly; without it, the subcommand fails clearly rather than silently
returning nothing.

## What opportunity scoring does

`dataset_opportunities.scoring.score_opportunity(candidate)` wraps
`dataset_importers.scoring.score_candidate` (an already-tested, deterministic,
additive heuristic) rather than reimplementing scoring from scratch. It
translates the resulting `CandidateScore` plus the source
`DatasetCandidateRecordV1` into twelve transparent, documented components
(`modality_relevance`, `task_state_relevance`, `metadata_completeness`,
`access_license_safety`, `bids_or_loadability_signal`,
`participant_or_duration_signal`, `mapping_feasibility`,
`adapter_compatibility`, `benchmark_pack_usefulness`,
`literature_link_usefulness`, `outreach_relevance`, `risk_penalty`), each
independently visible on `score_components`. `total_score` is always exactly
the sum of `score_components` -- enforced both at construction and by
`validate_opportunity_record` (rule 4).

- Unknown or restricted access, an `unknown_high` license, or unknown
  estimated size lowers score and removes every execution-oriented
  recommended action (`acquisition_plan_only`, `benchmark_pack_proposal`,
  `local_availability_check`) -- enforced structurally by
  `dataset_opportunities.validation`'s rule 12, not just by the scoring
  heuristic's own judgment.
- Missing task labels lowers `mapping_feasibility`/`task_state_relevance`.
- `outreach_potential` is `insufficient_data` unless the candidate carries an
  explicit identifier (a public/repository/documentation URL) or explicit
  contact metadata (`authors`/`contact`/`contact_email`/`pi`/
  `corresponding_author`) -- never inferred from a dataset name alone.
- `commercial_demo_potential` is framed only as demonstration suitability,
  never as a market or clinical-value judgment.
- A `blocked_*` transition-readiness candidate always gets `reject` in its
  `recommended_next_actions`.

## What opportunity ranking does not do

- **No download, no signal-byte loading, no feature extraction.**
  `build_opportunities_from_candidates` reads only already-constructed
  `DatasetCandidateRecordV1` objects -- it never calls `EEGDashDataset`,
  `.download()`, or any function that fetches signal data.
- **No report-pipeline or benchmark-pack execution.** `benchmark_pack_proposal`
  in `recommended_next_actions` is a proposal, never a call into
  `benchmark_packs`/`job_runner`.
- **No candidate silently dropped.** Every candidate ends up in either
  `ranked_opportunities` or `rejected_opportunities` (with a reason);
  `total_candidates_seen >= len(ranked) + len(rejected)` is enforced by
  `validate_opportunity_batch`.
- **No promotion to evidence.** `DatasetOpportunityRecordV1`/
  `DatasetOpportunityBatchV1`/`DatasetOpportunityPlanV1` structurally cannot
  carry a `claim_scope`/`evidence_level`/`evidence_ready` field
  (`hasattr` checks in `dataset_opportunities.validation`).
- **No automated outreach, no automated download, no clinical or
  spiritual-attainment claim.** Every opportunity's `blocked_actions` is a
  superset of `REQUIRED_BLOCKED_ACTIONS` (`direct_evidence_claim`,
  `direct_report_generation`, `clinical_claim`,
  `spiritual_attainment_claim`, `automatic_contact`, `automatic_download`).

## Planning outputs

`dataset_opportunities.planner.plan_next_actions_from_opportunities(batch,
max_selected=10)` turns the top-ranked opportunities into five candidate
lists, none of which are executed:

1. **Acquisition-plan candidates** -- `source_dataset_id` + a suggested
   `requested_action` (`plan_download`/`scan_existing_local`, matching
   `dataset_acquisition.acquisition_plan`'s own vocabulary) + a safety note
   that nothing has been executed. A real acquisition still requires a
   separate call into `dataset_acquisition.planner`.
2. **Benchmark-pack proposal candidates** -- proposed input mode plus an
   explicit list of missing requirements (condition/state mapping, bounded
   feature recipe, governed report generation) -- never a call into
   `benchmark_packs`.
3. **Literature-review tasks** -- dataset id, topic, task labels, and search
   terms only -- no literature link is fabricated, no external query is run.
4. **Researcher-outreach candidates** -- every entry carries
   `requires_human_review: true` and `not_sent: true`
   (`validate_opportunity_plan` rule 9 rejects any outreach entry missing
   `requires_human_review=True`). No email is sent, no contact is made.
5. **Awareness Studio ingest manifest path** -- a plain repo-relative path
   field (`awareness_studio_manifest_path`) a caller may populate; this
   milestone does not modify Awareness Studio's own runtime behavior.

## Rendering and CLI

`dataset_opportunities.renderer.render_opportunity_summary(batch, plan)`
produces deterministic Markdown with thirteen fixed sections (query summary,
candidate counts, top opportunities, recommended next actions, dataset
risks, acquisition planning candidates, benchmark-pack proposal candidates,
literature-review tasks, researcher-outreach candidates, limitations,
blocked actions, reproducibility commands, Awareness Studio ingest path).
Rendering the same batch/plan twice produces byte-identical text; the
rendered text is scanned for banned phrases before being written --
`render_opportunity_summary` raises rather than returns text if any are
found.

```bash
python -m dataset_opportunities.export_opportunities from-candidates \
    --candidates outputs/dataset_importers/candidates.json \
    --out outputs/dataset_opportunities/batch1

python -m dataset_opportunities.export_opportunities from-eegdash-fixture \
    --fixture tests/fixtures/eegdash_datasets.json \
    --out outputs/dataset_opportunities/batch1

python -m dataset_opportunities.export_opportunities eegdash-metadata-query \
    --query query.json --out outputs/dataset_opportunities/batch1 \
    --allow-live-metadata-query

python -m dataset_opportunities.export_opportunities plan \
    --batch outputs/dataset_opportunities/batch1/DatasetOpportunityBatch.json \
    --out outputs/dataset_opportunities/batch1 --max-selected 10

python -m dataset_opportunities.export_opportunities render \
    --batch outputs/dataset_opportunities/batch1/DatasetOpportunityBatch.json \
    --plan outputs/dataset_opportunities/batch1/DatasetOpportunityPlan.json \
    --out outputs/dataset_opportunities/batch1/summary.md
```

Every subcommand fails clearly (non-zero exit, `FAILED: ...` message) on an
invalid candidates/batch/plan path, an unsafe output root (must be under
`outputs/`or `data/`, mirroring `dataset_acquisition.store`'s own target-root
safety pattern), or a missing `--allow-live-metadata-query` flag on
`eegdash-metadata-query`.

## Relationship to the acquisition planner and benchmark packs

An `acquisition_plan_only` recommendation is a proposal only -- turning it
into a real `DatasetAcquisitionPlanV1` still requires an explicit,
separate call into `dataset_acquisition.planner.plan_acquisition` (see
[docs/dataset_acquisition_planner.md](dataset_acquisition_planner.md)). A
`benchmark_pack_proposal` recommendation likewise never calls
`benchmark_packs.generator` -- see
[docs/benchmark_pack_generator.md](benchmark_pack_generator.md).

## Researcher outreach is human-reviewed only

Every entry in `planned_outreach_candidates` carries
`requires_human_review: true` and `not_sent: true`. This package never sends
an email, never posts to social media, and never submits to a journal. It
only surfaces an identifier and a reason a human might want to follow up.

## Limitations

- Scoring is a documented, additive heuristic -- not a scientific judgment of
  dataset quality, relevance, or clinical usefulness.
- `outreach_potential`/`commercial_demo_potential` reflect metadata
  completeness, not researcher willingness or commercial viability.
- The `_MIN_RANKED_SCORE` / `blocked_*`-implies-`reject` rejection logic is a
  simple threshold, not a calibrated cutoff.
- No live EEGDash query has been exercised in this repository's test suite
  (only fixture and mocked paths) -- `--allow-live-metadata-query` is
  untested against a real network call by design.
- No authenticated API exists for triggering a scouting run.

## Relationship to `oss_opportunities/`

`oss_opportunities` (see `docs/oss_opportunity_pipeline.md`) is the
structurally parallel scout for *repositories* (Trendshift/Star History/
GitHub metadata) rather than *datasets* -- same candidate -> opportunity
-> batch -> plan -> render shape, different source domain. The two
packages do not read or write each other's artifacts.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **MOABB catalog integration** alongside EEGDash (candidate records already
  support `source_catalog="moabb"`).
- **Automated Awareness Studio ingest manifest generation** wired into the
  planner's `awareness_studio_manifest_path`.
- **Scheduled scouting runs**, building on `job_runner.worker`'s bounded
  loop mode.
- **Cross-batch deduplication** across repeated scouting runs over time.

This milestone does not imply clinical validity, does not imply consciousness
or spiritual-state detection regardless of a dataset's subject matter, and
does not imply that a `DatasetOpportunityRecordV1`/`DatasetOpportunityBatchV1`/
`DatasetOpportunityPlanV1` is clinical evidence or a validation-ready
biomarker set -- evidence begins at `adapters.*`/`evidence.builder`/
`reports.evidence_report`, exactly as it did before this milestone; this
package only ranks already-imported scouting candidates and proposes
next-action review items for a human.
