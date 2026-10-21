# PR-graph reconciliation — 2026-09-14

## Method and evidence class

This is **engineering evidence** (tool output over real git/GitHub facts), not a
scientific or correctness judgment about any PR's contents.

- `origin/main` at audit time: `ad1d480828b23bf9daf7272d8747302dcca138b7`.
- All 22 currently-open PRs (`#296`–`#364`) were enumerated via
  `mcp__github__list_pull_requests` (state=open), then each fetched individually
  via `pull_request_read(method="get")` for `mergeable_state`, `changed_files`,
  `additions`/`deletions`, `draft`, head/base sha. Raw capture:
  [`github_snapshot.json`](pr_reconciliation_2026-09-14/github_snapshot.json)
  (transformed into the tool's `NTS.GitHubReconciliationSnapshot.v1` schema).
- `tools/integration_reconciliation`'s existing `default_registry()` only knows
  about a *different*, older set of PRs (#209–#222, from a prior reconciliation
  round) — it is not a stale bug, just a hand-curated list that predates this
  PR pile. To reconcile the PRs that are actually open now, this run adds
  `work_orders.work_orders_from_snapshot()` (builds one `WorkOrder` per snapshot
  entry) and a `--work-orders-from-snapshot` CLI flag to
  `scripts/verify_integration_reconciliation.py`, both covered by new unit/CLI
  tests (`tests/integration_reconciliation/test_work_orders.py`,
  `tests/integration_reconciliation/test_cli.py`). This is a real, tested code
  change, not a one-off script — future reconciliation runs can reuse it
  against a fresh snapshot without hand-maintaining a branch list.
- Full run command:
  ```
  python3 scripts/verify_integration_reconciliation.py \
    --repo-path . --target-ref origin/main \
    --github-snapshot github_snapshot.json --work-orders-from-snapshot \
    --dashboard-src apps/awareness_studio/src --output-dir <out>
  ```
- Raw tool output: [`report.json`](pr_reconciliation_2026-09-14/report.json),
  [`report.md`](pr_reconciliation_2026-09-14/report.md).
- **Known scope gap**: this pass did not fetch CI check-run status
  (`get_check_runs`) for any PR — only GitHub's `mergeable_state`. Every entry
  below therefore shows `checks: not_run` in the raw report; that reflects
  "not fetched in this pass", not "no CI configured". Classification here is
  based on git-fact merge conflicts and cross-PR file overlap only, not CI
  health. A follow-up pass should pull check runs for anything selected to
  merge.

## Classification (22 PRs, 5 buckets)

### blocked-by-conflict (2)
Real evidence: GitHub reports `mergeable_state: dirty` against current `main`
(the tool maps this to `mergeable: conflicting`; every other PR here reports
`unstable`, which the tool deliberately reports as `unknown` rather than
guessing either way — see `github_source.mergeable_from_state`).

| PR | Title | Notes |
|---|---|---|
| #307 | bounded, resumable simulation campaign runner | 11 changed files, 1 commit ahead of merge-base; conflict is real (git fact), needs a rebase onto current `main` regardless of any other PR. |
| #298 | Validate research-cycle orchestrator against real registry contracts | 9 changed files, 1 commit ahead; same — real conflict against current `main`, independent of the other findings below. |

### needs-rebase-onto-another-open-PR (12)
Real evidence: nonzero *effective* changed-file overlap (i.e. overlap
computed on each PR's diff against its own base, not a raw diff-against-main
double-count) with at least one other currently-open PR. Full overlap list
in `report.md`'s "File overlaps" section. This does **not** mean the PRs are
wrong — only that whichever of an overlapping pair merges second will hit a
conflict (or a silent semantic regression, if the merge only conflicts on
adjacent lines) unless it's rebased first.

| PR | Overlaps with | Shared area |
|---|---|---|
| #358 | #359 (stacked on it), #357 | `research_graph/loader.py`, `types.py`, `diagnostics.py`, evidence-classes test |
| #359 | #358 (stacked), #352, #364, #357 | same research_graph files + `literature_bridge/*` |
| #352 | #359, #364, #357 | `literature_bridge/*` (mapping.py, reporting.py, repo_paths.py) |
| #364 | #359, #352, #362, #356, #357 | `literature_bridge/*`, `simulation_bridge/*`, `research_cycle_preflight/*` |
| #353 | #357, #362, #364 | `simulation_bridge/*` (new module touched by 3 independent PRs) |
| #362 | #353, #357, #364 | `simulation_bridge/*` |
| #354 | #357 | `data_access/policy_enforcement/*` |
| #355 | #357, #363 | BIDS/DANDI ingestion + **shared CI workflow file** `.github/workflows/fmri_tda_ds000245.yml` (3 PRs touching one workflow file — flagging per the "never touch CI workflow files without flagging it" rule, since whichever merges last will silently overwrite the others' workflow edits) |
| #363 | #355, #357, #350 | same ingestion area + `tests/test_fetch_ds000245.py` |
| #356 | #357, #364 | `research_cycle_preflight/*` |
| #350 | #357, #363 | `tests/test_fetch_ds000245.py` (1-file PR — trivial to rebase either direction) |
| #346 | #357 | `validation/s3_fetchers.py`, `validation/fast_tr_fixtures.py`, streaming migration tests |

### duplicate-or-superseded — flagged for owner decision, not resolved here (1)
**#357** ("Wire registered research execution and harden evidence integrity",
101 changed files — the largest PR in the pile) overlaps with **12 of the
other 21 open PRs**: #346, #350, #352, #353, #354, #355, #356, #358, #359,
#362, #363, #364. Concretely, its diff includes:
- Its own independent fix of the *exact same* `research_graph/loader.py`
  EMPIRICAL-promotion bug that #358 fixes (verified by direct diff against
  `origin/main`) — a different, arguably more elaborate design
  (`_classify_source_evidence`, `evidence_tier`/`verification_status`
  checks, terminal-status handling) that neither reuses nor is aware of
  #358/#359's `_classify_evidence` extension or the
  `EMPIRICAL_CLAIM_WITHOUT_VERIFICATION` diagnostic.
- `literature_bridge/mapping.py` at the **same revision #352 shipped**, i.e.
  *without* #364's two extra mismatch-rejection guards (verified by diffing
  #357's and #364's copies of `mapping.py` directly) — so #357 is not aware
  of #364's hardening either.
- New `simulation_bridge/*` and `orchestrator/{execution_review,
  registered_execution, research_context}.py` modules that #353/#362/#364
  also touch independently.

This is a real, evidence-based finding, but **whether #357 is meant to be
the integration point that supersedes the smaller PRs, or an independent
effort that will need to be rebased onto whichever of them lands first, is
not something git/CI facts can settle** — it depends on authorial intent
this reconciliation has no access to. Flagging for the repo owner rather
than guessing.

### no cross-PR conflict or overlap detected in this pass (7)
Real evidence: no `dirty` mergeable_state, no entry in the file-overlap list.
This is **not** the same claim as "safe to merge" — CI check status was not
fetched in this pass (see scope gap above), and `mergeable_state` for every
one of these is `unstable` (GitHub's own "mergeable but checks
pending/failing/unknown" state), not `clean`.

| PR | Title | `mergeable_state` |
|---|---|---|
| #296 | hypothesis-to-orchestrator contract compatibility layer | unstable |
| #297 | embodied-control alignment layer | unstable |
| #331 | approved acquisition adapter (bounded access + eviction) | unstable |
| #342 | post-merge pipeline measurement harness | unstable |
| #351 | migration-wave measurement harness (main vs #331/#344/#345/#346) | unstable |
| #360 | fail-closed cross-system evidence promotion gate | unstable |
| #361 | open-quantum solver / topological-kernel / benchmark optimization | unstable (flagged `scientific_review_required`: touches `core/topology.py`-adjacent scientific paths — a rubric/CI pass on this PR would not itself be scientific confirmation of the optimization's correctness) |

### stale/abandoned-candidate (0)
No PR qualifies by evidence. The three oldest open PRs (#296/#297/#298, opened
2026-09-08) each still carry a real, non-trivial diff (9–10 changed files, 1
commit ahead of merge-base, not an ancestor of `main`) — none is a git no-op
against current `main`, which is the only evidence this tool (and
`tools/github_pr_reconciliation/stale_pr_audit.py`'s
`close_as_noop_superseded_by_main` rule) treats as staleness. Age alone is not
evidence of abandonment and is not used to classify any PR here.

## Additional finding carried into backlog #3
**#360** ("Add fail-closed cross-system evidence promotion gate") adds
`tools/evidence_promotion_gate/` at repo root — a **fifth** independent
evidence/promotion-gate authority, alongside `governance/merge_gate.py`,
`tools/data_access/policy_enforcement/`, `tools/data_access/migration_gate/`,
and this session's own `research_graph` diagnostics. It shows no file overlap
with any other open PR (its own module is new), so it is not a merge-conflict
risk — but it is a duplicate-authority risk once several of these gates are
live simultaneously. Tracked as part of TaskList #3, not resolved here.

## Recommended merge order (informational, not a directive)
Given only git facts and the overlaps above, the lowest-conflict path through
the `literature_bridge`/`research_graph` cluster is: **#352 → #358 → #359 →
#364**, then reconcile #357's loader.py/mapping.py against whatever of those
landed. #350 (1 file) can go in before or after #357/#363 with a trivial
rebase either way. #307 and #298 need a plain rebase onto current `main`
before anything else, independent of this cluster. The #357-vs-everything-else
question above is a prerequisite decision, not something this ordering
resolves.
