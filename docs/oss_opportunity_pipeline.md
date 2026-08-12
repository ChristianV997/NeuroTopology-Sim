# Open-Source Trend Scout + Integration Opportunity Registry v1

Status: **implemented.** This document describes the `oss_opportunities`
package as it exists today. It does not describe, and should not be read
as promising, any capability beyond what is listed here.

This scout ranks and plans open-source leverage. It does not perform the
integration. Every output preserves uncertainty and separates safe
immediate adapters, architecture-emulation candidates, docs-only
references, license/security-review candidates, and rejected candidates.

```
Trendshift daily/weekly/monthly/yearly snapshot fixture
Star History starmap snapshot fixture
GitHub manual seed list
        |
        v   oss_opportunities.source_ingestion.import_from_*()
        v
OpenSourceRepositoryCandidateV1
        |
        v   oss_opportunities.license_review.classify_license_risk()
        v
RepositoryLicenseReviewV1
        |
        v   oss_opportunities.scoring.score_opportunity()
        v
OpenSourceIntegrationOpportunityV1
        |
        v   oss_opportunities.opportunity_batch.build_opportunities_from_candidates()
        v
OpenSourceLeverageBatchV1
        |
        v   oss_opportunities.planner.plan_oss_integrations_from_opportunities()
        v
OpenSourceIntegrationPlanV1
        |
        v   oss_opportunities.renderer.render_oss_opportunity_summary[_html]()
        v
Markdown / static HTML leverage report
```

## What OSS opportunity ranking does

- Scores an already-imported `OpenSourceRepositoryCandidateV1` (from a
  Trendshift snapshot fixture, a Star History starmap fixture, GitHub
  repository metadata, or a manual seed list) against a transparent,
  documented, additive heuristic (`oss_opportunities.scoring.
  score_opportunity`) -- direct product leverage, Awareness Studio
  leverage, report-pipeline leverage, document-ingestion/literature/
  code-graph-memory/workflow-orchestration/frontend-SaaS/infra leverage,
  adapter-surface clarity, maintenance/documentation signal, license
  safety, and dependency-weight/security-risk/duplication/commercial-core
  penalties.
- Classifies the observed license string against a fixed, offline risk
  ladder (`oss_opportunities.license_review.classify_license_risk`) --
  never a network license check, never a legal opinion.
- Ranks candidates deterministically into `OpenSourceLeverageBatchV1`, with
  every candidate ending up in either `opportunities_ranked` or
  `opportunities_rejected` (with a documented reason) -- never silently
  dropped.
- Proposes conservative, actionable next-PR names via
  `oss_opportunities.planner.plan_oss_integrations_from_opportunities`.
- Renders a deterministic Markdown and static HTML summary.

## What it does not do

- **No integration is ever performed.** Every opportunity's
  `blocked_actions` is a superset of `REQUIRED_BLOCKED_ACTIONS`
  (`copy_code_without_license_review`, `auto_install_dependency`,
  `execute_untrusted_code`, `commercial_core_copy_without_review`,
  `credential_required_execution`, `automatic_outreach`,
  `automatic_marketing_claim`) -- enforced structurally by
  `oss_opportunities.validation`, not just by scoring's own judgment.
- **No dependency is ever installed, no repository is ever cloned, no
  external code is ever executed.** Every fixture loader in
  `oss_opportunities.source_ingestion` reads only already-local JSON.
- **No raw Trendshift Signal API data is ever redistributed.** The paid
  Signal API is not implemented in this milestone; `trendshift_signal`
  exists in the allowed `source` vocabulary only so a future,
  explicitly-gated integration has somewhere to write records without a
  schema change. `validate_repository_candidate`'s rule 13 rejects any
  candidate that embeds a raw response payload or sets
  `metadata.redistributes_raw_signal_data=true`.
- **No candidate is ever promoted to evidence.** `OpenSourceRepositoryCandidateV1`/
  `OpenSourceIntegrationOpportunityV1`/`OpenSourceLeverageBatchV1`/
  `OpenSourceIntegrationPlanV1` structurally cannot carry a
  `claim_scope`/`evidence_level`/`evidence_ready` field.
- **Trending/star counts are a discovery-priority signal only.** They
  widen `maintenance_signal`/`documentation_quality_signal` slightly but
  never raise `license_safety` or unlock a commercial-core action --
  `test_trending_stars_alone_do_not_force_immediate_integration` asserts
  this directly.

## Trendshift source policy and raw-data redistribution caution

Three Trendshift-derived sources exist:

- `trendshift_daily`/`trendshift_weekly`/`trendshift_monthly`/`trendshift_yearly` --
  static snapshot fixtures (`from-trendshift-fixture`) or a bounded live
  page scan (`live-trendshift-scan`, requires `--allow-live-network`
  explicitly; never called by this repository's test suite). The live
  path's own HTML parser (`_parse_trendshift_html`) is conservative: it
  extracts only `owner/repo` GitHub links in first-seen order and leaves
  stars/license/description as unknown, rather than guessing values from
  markup this milestone has not verified against Trendshift's real page
  structure.
- `trendshift_signal` -- reserved for the paid Signal API, **not
  implemented in this milestone**. No code path fetches it; the source
  value exists only in the schema's allowed vocabulary.

Neither path ever writes a raw Trendshift API response into a candidate's
`metadata` -- `validate_repository_candidate` rejects that explicitly for
`source="trendshift_signal"` (rule 13), and the live-scan path never
receives or stores a raw JSON payload from Trendshift in the first place
(it only ever sees HTML it parses immediately, and only into named
fields).

## Star History starmap's role

`star_history_starmap` fixtures represent a *category* (frontend/backend/
data/infra) plus a *stack layer* per repository. This scout treats a
starmap entry the same as any other candidate for scoring purposes; the
category/stack-layer is recorded in `observed_categories` and read by
`infer_leverage_category`'s keyword matching. Star History is an
**architecture reference source**, not a quality signal -- see "Trending
stars" above.

## License-risk model

`oss_opportunities.license_review.classify_license_risk` maps an observed
SPDX (or SPDX-like) string to one of six risk tiers:

| license_risk | example | commercial_core_policy default |
|---|---|---|
| `permissive_low` | MIT, Apache-2.0, BSD-2/3-Clause, ISC | `allowed_with_attribution` |
| `weak_copyleft_medium` | LGPL-2.1/3.0, MPL-2.0, EPL | `adapter_only` |
| `strong_copyleft_high` | GPL-2.0/3.0, AGPL-1.0/3.0 | `external_process_only` |
| `source_available_or_fair_code_high` | BSL-1.1, SSPL-1.0, Elastic-2.0 | `docs_reference_only` |
| `proprietary_or_unknown_high` | any unmatched string | `blocked_pending_review` |
| `missing_high` | empty/`unknown`/`no-license` | `blocked_pending_review` |

Only `permissive_low` may ever carry a copy-permitting
`commercial_core_policy` (`allowed_with_attribution`) -- fail closed, no
per-record override, enforced both at construction (`_DEFAULT_POLICY_BY_RISK`)
and at validation time (`validate_license_review`'s rule 8). An opportunity
whose `recommended_action` implies code-copy is additionally cross-checked
against its paired license review (`validate_opportunity_against_license_review`)
before it is ever included in a batch.

## Allowed use modes / blocked actions

Every `RepositoryLicenseReviewV1` carries explicit `allowed_use_modes` and
`blocked_use_modes` (e.g. `adapter_only`, `docs_reference`,
`external_process_only`, `attributed_snippet_copy` vs.
`commercial_core_copy`, `code_copy_of_any_kind`, `unattributed_copy`).
Every `OpenSourceIntegrationOpportunityV1`'s `blocked_actions` is always a
superset of the fixed floor listed above, regardless of how well the
repository scores.

## How Copilot Pro review comments should be handled

Per this repository's standing Copilot Pro usage rule: Copilot review
comments are an additional review signal, not source of truth. For each
comment on a PR touching this package: fetch it, classify it (valid / not
applicable / unsafe / out of scope), address valid comments with a real
code fix plus a test that would have caught the issue, and document
rejected comments with reasoning directly in the PR thread rather than
silently ignoring them. Generated code is never accepted without a
repo-local audit, a license-safety check, tests, and a guardrail scan --
this applies to this package's own code as much as to any external
repository it might one day recommend integrating.

## Relationship to `external_tools/`

`external_tools.tool_record.ExternalToolRecordV1` is this repository's
small, **hand-curated** catalog of tools it has already deliberately
assessed for adapter integration. `oss_opportunities` is the automated
**scouting** layer upstream of that catalog: a `recommended_action` of
`integrate_as_external_tool_record` names a *future* `ExternalToolRecordV1`
entry this package's opportunity output could seed -- it never writes to
`external_tools/registry_seed.json` directly, and no seed registry is
mutated by anything in this package.

## Relationship to `dataset_opportunities/`

`dataset_opportunities` ranks *datasets* (EEGDash/MOABB catalogs).
`oss_opportunities` ranks *repositories* (Trendshift/Star History/GitHub).
Different domain, different source model, structurally parallel shape
(candidate -> opportunity -> batch -> plan -> render) -- kept as sibling
packages rather than merged, the same reasoning `dataset_opportunities`
itself used to justify staying separate from `dataset_importers`/
`benchmark_packs` (see `docs/dataset_opportunity_pipeline.md`).

## Relationship to `tools/public_repo_harvest/`

`tools/public_repo_harvest/` is a pre-existing, unrelated prototype (added
under "P39 public repo harvest subsystem", well before this package). It
covers a broader, more ad hoc "harvest reusable patterns across many
subsystems" scope, uses a different, looser coding convention (no
`from __future__ import annotations`, one-line function bodies, no
`validate_or_raise`/deterministic-ID discipline, no tests), and has no
Trendshift/Star History source model at all. `oss_opportunities` neither
reuses nor modifies it.

## Relationship to Awareness Studio

Opportunities in the `code_graph_memory`/`research_memory`/`agent_harness`
leverage categories are the ones most relevant to Awareness Studio's
future memory/research-graph design -- but this milestone only classifies
and proposes; it does not touch `apps/awareness_studio/` at all.

## Relationship to the future SaaS/frontend stack

Opportunities in the `frontend_stack`/`backend_api_stack`/
`database_data_stack`/`infra_observability_stack` leverage categories
default to `emulate_architecture_pattern`, not integration into this
repository's Python core (mission rule: large TypeScript/infra stacks are
usually emulation/reference, not direct-dependency candidates) -- see
`_NON_PYTHON_CORE_LANGUAGES` in `oss_opportunities.scoring`. The proposed
next PR for these categories is a **decision record**, not an
implementation.

## CLI usage

```bash
python -m oss_opportunities.export_oss_opportunities from-manual-seed \
    --seed seed.json --out outputs/oss_opportunities/manual

python -m oss_opportunities.export_oss_opportunities from-trendshift-fixture \
    --fixture trendshift_daily.json --out outputs/oss_opportunities/trendshift

python -m oss_opportunities.export_oss_opportunities from-starmap-fixture \
    --fixture starmap_frontend.json --out outputs/oss_opportunities/starmap

python -m oss_opportunities.export_oss_opportunities live-trendshift-scan \
    --timeframe daily --timeframe weekly \
    --out outputs/oss_opportunities/live --allow-live-network

python -m oss_opportunities.export_oss_opportunities plan \
    --batch outputs/oss_opportunities/manual/OpenSourceLeverageBatch.json \
    --out outputs/oss_opportunities/manual --max-selected 20

python -m oss_opportunities.export_oss_opportunities render \
    --batch outputs/oss_opportunities/manual/OpenSourceLeverageBatch.json \
    --plan outputs/oss_opportunities/manual/OpenSourceIntegrationPlan.json \
    --out outputs/oss_opportunities/manual/summary
```

Every subcommand fails clearly (non-zero exit, `FAILED: ...` message) on
an invalid input path, an unsafe output root (must be under `outputs/` or
`data/`, mirroring `dataset_acquisition.store`'s target-root safety
pattern), an invalid Trendshift timeframe / starmap category, or a missing
`--allow-live-network` flag on `live-trendshift-scan`.

## Limitations

- Scoring is a documented, additive heuristic -- not a scientific or
  legal judgment of repository quality, correctness, or license safety.
- `classify_license_risk` is an offline string match against a fixed list
  -- it does not fetch or parse an actual `LICENSE` file, and
  `review_status` defaults to `"heuristic_unreviewed"`; only a
  human-set `"human_reviewed"` value means an actual person looked at it.
- `infer_leverage_category`'s keyword matching is a simple substring
  overlap over `description`/`topics`/`name` -- it can misclassify a
  repository whose README doesn't use the expected vocabulary.
- The live Trendshift scan's HTML parser has not been verified against
  Trendshift's real page markup in this environment (network-restricted
  sandbox) -- it is conservative by design (repo names + rank only) and
  is never exercised by the test suite beyond its pure-parsing half.
- No authenticated API exists for triggering a scouting run.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Document Ingestion Adapter Registry v1** -- a real `external_tools`
  entry + adapter contract for MarkItDown/AnyDoc/PDF Inspector.
- **Firecrawl External Tool Record + Literature Source Adapter Plan v1**.
- **Awareness Studio Code/Research Graph Memory Design v1**.
- **Static Report Diagram Renderer Plan v1**.
- **SaaS Frontend Stack Decision Record v1**.
- **Authenticated API** for triggering scouting runs.
- **Scheduled trend scans**, building on `job_runner.worker`'s bounded
  loop mode.
- **Trendshift Signal API integration**, gated behind an explicit env
  var/API key contract, once one exists.

This milestone does not imply clinical validity, does not imply
consciousness or spiritual-state detection, and does not imply that any
repository listed in this document's ranked output has been integrated,
its code copied, or its maintainers contacted -- every output here is a
scouting/planning artifact, exactly as it was before this milestone.
