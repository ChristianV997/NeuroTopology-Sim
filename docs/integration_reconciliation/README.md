# Integration Reconciliation

> **Round 2 update (PR #218 continuation):** added stacked-PR awareness
> (`stacking.py`), richer current-status fields (`checks_status`,
> `mergeability`, `billing_blocked`, `superseded`, `duplicate`,
> `scientific_review_required` -- `models.CurrentStatus`), CI-failure-mode
> interpretation (`ci_interpretation.py`, distinguishing an actual test
> failure from an infrastructure block from a billing block from a
> not-yet-run job), scientific-claim text hints (`scientific_gates.py`),
> and duplicate/superseded detection (`duplicate_detection.py`). See
> "Round 2 findings" below for what the updated dry-run found against the
> real repository, including a real bug this round's own development
> caught and fixed (see "A bug this round's fixture caught").



Branch: `claude/integration-reconciliation`. Owns exclusively:
`tools/integration_reconciliation/**`,
`scripts/verify_integration_reconciliation.py`,
`tests/integration_reconciliation/**`, `docs/integration_reconciliation/**`.
Touches nothing in PR #210/#211/#212's implementation files, the
Bayesian falsification code, CI workflows, signal adapter implementations,
generated artifacts, or dashboard routes.

## What this tool is

A **read-only** verifier that turns "is branch X / PR Y actually in the
state someone reported?" into a precise, evidenced, machine-checkable
answer instead of a claim taken on faith. It never merges, closes,
rebases, deletes, or pushes anything — every git command it runs is a
read (`rev-parse`, `merge-base`, `diff --name-only`, `rev-list --count`),
and every GitHub fact it uses comes from a **pre-fetched JSON snapshot**
supplied via `--github-snapshot`, never a live API call made by this code
itself (see "Why a snapshot file, not a live API call" below).

## Architecture

```
tools/integration_reconciliation/
  models.py              # Evidence, WorkOrder, BranchFacts, PRFacts, ReconciliationEntry/Report
  git_source.py           # read-only git plumbing (rev-parse/merge-base/diff/rev-list)
  github_source.py        # loads + queries a GitHubReconciliationSnapshot.v1 JSON file/dict
  work_orders.py           # the known work-order registry (this mission's 8 entries)
  overlap.py               # pairwise changed-file overlap across work orders
  common_failures.py       # flags a check failing across most work orders as likely environmental
  dashboard_isolation.py   # static AST import scan: no solver import under apps/awareness_studio/src
  artifact_check.py        # pattern-matches changed-file lists for accidentally-committed generated output
  reconcile.py              # orchestrates all of the above into one ReconciliationReport
  reporting.py              # strict JSON + Markdown rendering
scripts/verify_integration_reconciliation.py   # CLI
tests/integration_reconciliation/**             # 78 tests, all against local git fixtures + in-memory dicts
```

## Why a snapshot file, not a live API call

Requirement: "network access must not be required for unit tests." PR
mergeability, check-run conclusions, and merged/draft state are not git
facts — they only exist on GitHub's side. Two ways to get them into this
tool: (a) make this tool itself call the GitHub API, which would make
every test either need real network+credentials or an HTTP mock layer
bolted onto every test; or (b) treat "the current GitHub-side facts" as
an **input** the operator already has (via `gh`, a GitHub App, or an MCP
client) and hand it to this tool as a snapshot file. This tool takes (b):
`tools/integration_reconciliation/github_source.py` only ever reads a
dict. That keeps every unit test network-free by construction, and keeps
the reconciliation logic itself testable with a two-line in-memory dict
instead of a mocked HTTP client.

## The six stages (requirement 7)

For each work order, `reconcile.py` derives:

| Stage | True when | Evidence source |
|---|---|---|
| `reported` | the work order was supplied to this run at all | always "work order was supplied to this reconciliation run" |
| `branch_present` | `git rev-parse --verify` resolves the expected branch | `git_source.ref_exists` |
| `pr_present` | a snapshot entry's `head_ref` (or a declared `reported_pr_number`) matches | `github_source.find_pr_by_branch`/`find_pr_by_number` |
| `checks_passing` | every check in the snapshot's `checks` map is `"success"` | `github_source.checks_all_passing` — `None` if no check data at all |
| `mergeable` | GitHub's `mergeable_state` is exactly `"clean"` | `github_source.mergeable_from_state` — `None` for `"unstable"`/`"blocked"`/unknown, not a guess |
| `merged` | the snapshot's `merged` boolean | verbatim from the snapshot |

Every one of these is an `Evidence(value, source)` pair (`models.py`), so
the strict JSON output always says *why* a value is null (requirement
10), never just that it is.

## Manual dry-run against the real repository (2026-09-06)

GitHub access was available this session, so branch/PR facts were
fetched live via `mcp__github__list_pull_requests` /
`pull_request_read` and saved as
`tests/integration_reconciliation/fixtures/real_repo_snapshot_2026-09-06.json`
(the exact snapshot format this tool consumes — kept as a fixture because
it is an input the tests also exercise, not a generated output). Command:

```bash
python scripts/verify_integration_reconciliation.py \
  --repo-path . --target-ref origin/main \
  --github-snapshot tests/integration_reconciliation/fixtures/real_repo_snapshot_2026-09-06.json \
  --dashboard-src apps/awareness_studio/src \
  --output-dir /tmp/reconciliation_dryrun
```

### Findings

**All seven previously-missing dependency branches now exist on the
remote** (they did not at the time of `claude/ecosystem-integration`'s
PR #210, which correctly reported them absent as of its own fetch).

| Work order | branch present | PR present | checks passing | mergeable | merged |
|---|---|---|---|---|---|
| PR #210 ecosystem-integration-scaffold | yes | yes (#210) | no | unknown | no |
| PR #211 streaming-performance | yes | yes (#211) | no | unknown | no |
| PR #212 signal-interoperability | yes | yes (#212) | no | unknown | no |
| codex/scientific-falsification-contract | yes | **no** | — | — | — |
| antigravity/mne-scipy-streaming-eeg | yes | yes (#214) | no | unknown | no |
| antigravity/test-isolation-dependency-profiles | yes | yes (#213) | no | unknown | no |
| grok/tool-admission-research | yes | **no** | — | — | — |
| grok-bot/retrofit-inventory | yes | yes (#209) | no | unknown | no |

**Corrections to the reported state this reconciliation surfaced:**

1. **"Antigravity and Grok branch reports are currently incomplete or
   unavailable" is stale for three of the four.** `antigravity/
   mne-scipy-streaming-eeg` (PR #214), `antigravity/
   test-isolation-dependency-profiles` (PR #213), and `grok-bot/
   retrofit-inventory` (PR #209) all now have real, open PRs with
   substantial diffs (8, 17, and 32 changed files respectively). Only
   `grok/tool-admission-research` genuinely still has no PR.
2. **The `codex/scientific-falsification-contract` report is confirmed
   accurate**: the branch exists (commit `111d4fc`, 7 changed files
   including `sim/pitnn/bayesian_falsification.py` and
   `analysis/connectivity_topology.py`) but no PR exists for it in the
   live PR listing — consistent with "PR creation previously failed."
3. **No file-overlap conflicts were found** between any pair of the eight
   work orders' changed-file sets (`git diff --name-only` three-dot diffs
   against `origin/main`) — each branch's changes are disjoint at the
   file level. This does not mean their *logic* cannot conflict (e.g. two
   branches independently changing sibling files that call into each
   other), only that no textual merge conflict is mechanically implied.
4. **A likely-environmental CI pattern, not a per-branch defect**: the
   checks `core-tests`, `ontology-claim-language`, and `Cross-system
   smoke` fail identically across **100% of the 6 PRs that reported any
   check data** (including PR #210, which adds files only and edits
   nothing existing) — flagged by `common_failures.py`. `main`'s own most
   recent "Required Checks" workflow run (the aggregator gate) is
   green at the exact base commit (`62637a4b`) every one of these
   branches forked from, per `mcp__github__actions_list` — so this is not
   simply "main is red." The parsimonious reading is that these specific
   checks behave differently under the `pull_request` trigger than
   `push` (possibly a permissions or fork-context difference), not that
   any of these six branches broke something. This reconciliation
   reports the pattern; it does not attempt to root-cause the CI
   configuration itself, since `.github/workflows/**` is explicitly
   outside this branch's ownership.
5. **Dashboard isolation: PASS.** A static AST import scan of
   `apps/awareness_studio/src` (52 `.py` files) found zero imports of
   `sim.pitnn`, `physics.exact_dynamics`, `core.topology`,
   `analysis.connectivity_topology`, `governance`, `shared.interop`, or
   any of this session's own integration tooling.
6. **No accidentally-committed generated artifacts** were found in any of
   the eight work orders' changed-file lists (patterns checked: `*.pyc`,
   `__pycache__/*`, `*RunRecord.json`, `*manifest.json`,
   `*quality_report.json`, `artifacts/*`, `results/*`, `*.npz`, `*.h5`,
   `*.png`, `*.pkl`, `*.log`, excluding this repository's own legitimate
   `docs/`, `tests/**/fixtures/`, and `governance/specs/` conventions).

**What this reconciliation does not (and cannot) claim:** whether the
seven branches' actual *scientific* content is individually correct, or
whether merging them together would introduce a *semantic* conflict
invisible to a file-level diff (e.g. two branches redefining an
overlapping public API differently). Those questions require reading
each branch's diff, which is a code-review task, not a reconciliation
task — this tool's job is to make "reported vs. actual" precise, not to
replace review.

## Round 2 findings (2026-09-06, PR #218 continuation)

Fresh snapshot: `tests/integration_reconciliation/fixtures/real_repo_snapshot_2026-09-06-round2.json`,
covering the 10 PRs named in the updated "known open work" (#209–#215,
#217, #219, #222) plus the two still-branch-only reports.

**Stacked PRs found (requirement 1):** two real stacks exist on the
remote, both self-declared in their own PR bodies:
- **PR #215** (process-memory-telemetry) is stacked on **PR #211**
  (streaming-performance) — its base branch is
  `cursor/streaming-performance-benchmarks`, not `main`.
- **PR #220** (not in the tracked work-order set this round, discovered
  in passing) is stacked on **PR #212** — base branch
  `codex/interop-signal-contracts`.

`stacking.py` computes each stacked work order's *effective* diff against
its immediate base rather than `main`, so its own real contribution is
never double-counted with its base's files — verified end-to-end against
a git fixture reproducing this exact shape
(`tests/integration_reconciliation/test_stacking.py`,
`test_reconcile_stacking.py`).

**A bug this round's fixture caught, before it shipped:** the first
version of `duplicate_detection.detect_superseded` checked plain git
ancestry between every pair of present branches with no awareness of
stacking. Run against the real PR #211/#215 stack, it reported
*"streaming-performance is superseded by process-memory-telemetry"* —
wrong: a stacked PR's branch is *always* a git descendant of its base's
branch by construction, so that ancestry relationship is deliberate
lineage, not evidence of supersession. The same blind-spot also made the
raw (non-effective) file-overlap check report #211 and #215 as sharing 8
"overlapping" files, when in truth #215's real diff is just its own 4 new
files. Both are now fixed: `detect_superseded` excludes known stacked
pairs from its candidate set, and `file_overlaps` is computed from
*effective* diffs. Regression tests:
`test_no_superseded_flagged_for_a_legitimate_stack`,
`test_file_overlaps_use_effective_diffs_not_raw_stacked_diffs`.

**Real (non-stacking-related) file overlaps found — genuine conflict
candidates, requirement 3:**
- **`bayesian-hardening` (PR #219) and `scientific-falsification-contract`
  (no PR)** both touch `sim/pitnn/bayesian_falsification.py`. PR #219's
  description explicitly targets the exact false-PASS gate defect this
  reconciliation effort's earlier scientific review found (see "Scientific
  gate checks" below) — the un-PR'd branch may be independent, overlapping
  work on the same fix.
- **`ci-test-infrastructure` (PR #222) and
  `test-isolation-dependency-profiles` (PR #213)** both touch
  `.github/workflows/ci.yml`, `.github/workflows/required-checks.yml`,
  `conftest.py`, `pytest.ini`, `scripts/run_tests_isolated.py` — two
  independent CI-infrastructure rewrites over the same files. Both would
  need reconciling against each other before either merges.

**CI interpretation (requirement 5) — the shared failure now has a
confirmed root cause, not just a correlation.** A real job log
(`core-tests`, PR #210, job 101412547695, fetched via
`get_job_logs`) ends with:

```
ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device
##[error]Process completed with exit code 1.
```

`ci_interpretation.classify_check` recognizes this exact message and
classifies the check `infrastructure_blocked`, not `failing` — a bare
`conclusion: "failure"` with no such evidence is still reported as a real
test failure, never silently downgraded. PR #222's own description
independently reaches the same conclusion ("disk exhaustion from
CUDA/NVIDIA-heavy packages... before test execution"), which corroborates
the classification from a second, independent source. Notably, **PR
#222's own CI (fetched after its creation) is still all-failing** — its
fix has not yet been observed green; this reconciliation does not assume
a PR's stated fix works until its own checks confirm it.

**Scientific gate hints (requirement 4):** `scientific_gates.py`'s
text-hint check was validated against PR #219's real description as a
deliberate negative case — its careful "distinguish...proxies from
formal...Bayes factors" / "synthetic...unable to produce PASS" language
does *not* trip the `unqualified_bayes_factor_claim` or
`synthetic_pass_claim_risk` hints (see
`test_pr219_style_text_does_not_trip_the_bayes_factor_hint`), confirming
the heuristic rewards rather than penalizes exactly the disclosure
language this ecosystem's own scientific rules ask for.

**Duplicates/superseded (requirement 3), final result:** zero genuine
duplicates and zero genuine superseded branches found among the 10 PRs,
once stacking is correctly excluded.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/integration_reconciliation -q     # 78 passed
python -m governance.validate                                        # 4/4 specs pass (baseline, unaffected)
python -m compileall -q tools/integration_reconciliation scripts/verify_integration_reconciliation.py tests/integration_reconciliation
```

No test in `tests/integration_reconciliation/` opens a socket or calls an
HTTP client; every git fixture is a real, local-only repository built
under `tmp_path` (`tests/integration_reconciliation/conftest.py`), and
every GitHub fact used in a test is a literal in-memory dict.

## Snapshot schema (`NTS.GitHubReconciliationSnapshot.v1`)

See the docstring in `tools/integration_reconciliation/github_source.py`
for the full field-by-field description. Minimal example:

```json
{
  "schema": "NTS.GitHubReconciliationSnapshot.v1",
  "pull_requests": [
    {
      "number": 210, "head_ref": "claude/ecosystem-integration",
      "state": "open", "draft": true, "merged": false,
      "mergeable_state": "unstable",
      "checks": {"core-tests": "failure", "awareness-tests": "success"}
    }
  ]
}
```

## Report schema (`NTS.IntegrationReconciliationReport.v1`)

Top-level keys: `schema`, `base_branch`, `base_commit`, `entries` (one per
work order, each with `branch`/`pr`/`stages`/`notes`, every leaf an
`{"value": ..., "evidence": "..."}` pair), `file_overlaps`,
`common_check_failures`, `dashboard_isolation`, `artifact_commit_findings`.
