# PR retirement register — Lead decisions (inventory only)

**Inventory date:** 2026-09-06T22:21:12Z  
**Repository:** https://github.com/ChristianV997/NeuroTopology-Sim  
**Live `origin/main` SHA:** `62637a4b9c82c0c258bfc49e28dee1af757b1c25`  
**Main tip:** merge of PR #205  
**Inspector:** Lead phase only, disposable worktree from `origin/main`  
**Evidence source:** live `gh` / GitHub API (open PR list, check-run annotations, compare, file lists)  
**This PR:** new matrix on `grok-bot/pr-retirement-register`  
**Owned files:** `configs/release/pr_retirement_matrix.yaml`, this document  

This document is a **snapshot of open / relevant PRs, key branch-only work, and cited relationships**.  
It is not a merger recommendation, not a test report, and not a scientific verdict.

**Inventory ≠ evidence.**  
**Merger: do not merge. Do not mark ready. Do not close any PR.**

---

## Required explicit statements (read first)

1. **PRs are not merged unless GitHub says so.** Independently confirmed on 2026-09-06: every open PR in the #206–#233 wave has `state=OPEN` and `mergedAt=null`. `mergeable=MERGEABLE` only means Git can apply the diff. It is not a QA or scientific sign-off.
2. **CI billing failure ≠ passing tests.** Check-run annotations on #209 and #213–#233 read: *“The job was not started because recent account payments have failed or your spending limit needs to be increased.”* Those jobs have empty step lists. That is `billing_not_started`. It does **not** mean tests passed.
3. **Disk-full / install CI failure ≠ passing tests.** Independently re-read failed logs this run for #206 (`core-tests` job 101243532368), #211 (`core-tests` on run 33945890473), and #212 (`Cross-system smoke` on run 33945890464): `OSError: [Errno 28] No space left on device` during `pip install`. Pytest was skipped. #207 / #208 / #210 show the same *started then failed at Install root dependencies* step pattern; their ENOSPC log text was not re-fetched in this run.
4. **Synthetic ≠ biological evidence.** Synthetic fixtures, lattice campaigns, and performance stand-in workloads cannot establish scientific `PASS` or biological evidence.
5. **Proxy Bayes ≠ formal Bayes factors.** On `main`, `sim/pitnn/bayesian_falsification.py` states that `bayes_factor` is a descriptive Bayes-factor proxy (Gaussian residual likelihood ratio / RSS). Open #219 / #226 and the branch-only scientific-falsification contract do not change that.
6. **Inventory ≠ evidence.** This register is not a compiled evidence bundle and is not a second #216/#225 evidence authority.
7. **#218 reconciliation metadata ≠ replacement implementation.** The PR owns `tools/integration_reconciliation/**` only. It does not replace #210/#211/#212 (or later) implementations.
8. **Do not invent DUPLICATE or SUPERSEDED** without cited GitHub metadata, PR body, or base/head overlap. Ambiguous rows stay `needs_human_review` / `keep_open`.

Lead does **not** finalize retirement. `status_hint` values are `keep_open` or `needs_human_review` only.

---

## Scope / non-scope

Created here:

- `configs/release/pr_retirement_matrix.yaml`
- `docs/release/pr_retirement_decisions.md`

Not created (other phases / other packs):

- `scripts/validate_pr_retirement_matrix.py` (Release)
- `tests/release/test_pr_retirement_matrix.py` (QA)

Not modified (leave #216 / #225 packs alone):

- `scripts/compile_repository_evidence.py`
- `configs/release/evidence_schema.yaml`
- `docs/release/agent_contribution_matrix.yaml`
- `docs/release/current_state.md`

Not touched: production solvers, CI workflows, Bayesian implementation, signal adapters, streaming tools, dashboard, datasets, credentials. Tooling used against GitHub was read-only (`gh` list/view/api/compare). No PR was closed or merged.

---

## Verified relationships

These are structured edges with cited evidence. They are **not** merger order and **not** retirement orders.

| ID | Edge | Kind | Evidence |
| --- | --- | --- | --- |
| `rel-216-225-docs-supersede` | **#225 → #216** | docs_supersede | #225 title *“superseding #216 inventory”*; both PR bodies; file overlap is exactly the three `docs/release/*` files. Schema / compiler / `tests/release/**` stay on #216 (live head `9c862d90e199`, QA delta after `07841284`). Whole-PR #216 is **not** superseded. |
| `rel-214-220-related-domain` | **#214 vs #220** | related_domain_parallel | Zero path overlap. #214 = `sciencer_d/btc_icft/io/*` + `validation/analytic_phase.py`. #220 = `shared/interop/adapters/**` stacked on **#212**. #233 body cites all three as conformance targets. Not duplicate. |
| `rel-222-227-parallel-ci` | **#222 vs #227** | related_parallel_ci | **#227 exists.** GitHub base of #227 is #213 head `f23c7ef74b13`, not #222. Six workflow files overlap. `git compare` #222…#227 is **diverged**. #227 body names #213 as stack parent and mentions #222 as a billing-blocked parallel attempt. Not duplicate. |
| `rel-211-215-224-232-stack` | **#211 → #215 → #224 → #232** | stacked_chain | Each child’s `baseRefOid` equals the parent head SHA. PR bodies: #215 stacked on #211; #224 stacked on #215/#211; #232 stacked on #224. |
| `rel-219-scientific-falsification-contract` | **#219 vs `codex/scientific-falsification-contract`** | related_diverged | Shared `sim/pitnn/bayesian_falsification.py`. Other files differ. `gh pr list --head` for that branch is empty. `git compare` vs #219 is **diverged**. Not duplicate. |
| `rel-213-ci-dependencies` | **#213 → #227** (overlaps #222) | ci_workflow_dependency | #213 edits `ci.yml`, `required-checks.yml`, requirement profiles, isolated runner. #227 is stacked on #213 and consumes those profiles. #222 edits the same workflow/runner files from `main`. |
| `rel-218-reconciliation-metadata` | **#218** | reconciliation_metadata_not_replacement | Title/body + 36 files all under reconciliation tool/docs/tests. Explicitly does not touch implementation PRs, Bayesian code, workflows, adapters, or dashboard. |
| `rel-212-220-stack` | **#220 → #212** | stacked | #220 `baseRefOid` = #212 head `a21dcb2461cd`. Body: adapters for #212 contracts. Unmerged adapters ≠ supported. |
| `rel-219-226-stack` | **#226 → #219** | stacked | #226 `baseRefOid` = #219 head `a7dd8e24b1d3`. Body: stacked on #219; does not convert proxy evidence into formal K. |
| `rel-217-223-continues` | **#223 continues #217** | continues_without_github_base_stack | #223 body: continues #217 instead of duplicating. Git compare #217…#223 is ahead 4 / behind 0 (snapshot files only). GitHub **base is `main`**, not #217 — stacking is ancestry + body, not GitHub base metadata. Not duplicate. |
| `rel-233-conformance-consumer` | **#233 → #212/#214/#220** | conformance_consumer | #233 body: conformance across #212, #214, and #220. Base is `main`. Consumer suite, not a replacement. |

Additional verified stacks (same method: GitHub `baseRefOid` == parent head):

- **#215 → #211**
- **#220 → #212**
- **#226 → #219**
- **#227 → #213**
- **#224 → #215 → #211**
- **#232 → #224 → #215 → #211**

---

## Duplicate candidates

**Empty.** No exact-duplicate open PRs were verified.

Related pairs that are **not** `DUPLICATE` (cited above):

- #214 vs #220 (no file overlap; different stacks)
- #222 vs #227 (diverged; #227 stacked on #213)
- #219 vs `codex/scientific-falsification-contract` (diverged)
- #217 vs #223 (continuation; #223 contains #217 commits)
- #216 vs #225 (docs overlap only; different remaining file sets)

---

## Superseded candidates

| Candidate | Scope | Evidence | Whole PR? | Final? |
| --- | --- | --- | --- | --- |
| **#216 inventory docs** by **#225** | `docs/release/README.md`, `agent_contribution_matrix.yaml`, `current_state.md` only | #225 title + body; #216 latest body points inventory docs at #225 `a3f7e7e8024d`; path overlap is exactly those three files | **No.** Schema, compiler, and `tests/release/**` stay on #216 | **No.** Integration owns retirement. Do not close #216. |

No other SUPERSEDED label is claimed.

---

## Open PR inventory (all `merged: false`)

GitHub reports `mergeable=MERGEABLE` and `mergeStateStatus=UNSTABLE` on every open PR below. Checks are red or mixed. None is merged.

`status_hint` is **not** a close/merge instruction.

| PR | Draft | Branch / head | Base | `status_hint` | Check class | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| [#206](https://github.com/ChristianV997/NeuroTopology-Sim/pull/206) | draft | `cursor/setup-dev-environment-52dc` `52118e74` | `main` `62637a4b` | keep_open | disk_fail (verified ENOSPC) | Env config only. Included so #206–#208 are not ignored. |
| [#207](https://github.com/ChristianV997/NeuroTopology-Sim/pull/207) | draft | `cursor/pitnn-perf-opt-52dc` `a0038fd0` | `main` | keep_open | job_started_install_fail | `tryptophan_lindblad.py` only. Different file from #211. Author speedup unverified. |
| [#208](https://github.com/ChristianV997/NeuroTopology-Sim/pull/208) | draft | `cursor/disorder-modes-runrecord-sidecar-v1-04d8` `5c2bfe04` | `main` | needs_human_review | job_started_install_fail | Opt-in sidecar. Author: `NOT_SUPPORTED` / `INCONCLUSIVE`; no K. Synthetic ≠ biology. |
| [#209](https://github.com/ChristianV997/NeuroTopology-Sim/pull/209) | draft | `grok-bot/retrofit-inventory` `3a3cf3df` | `main` | keep_open | billing_not_started | Inventory ≠ evidence. |
| [#210](https://github.com/ChristianV997/NeuroTopology-Sim/pull/210) | draft | `claude/ecosystem-integration` `2d46f863` | `main` | keep_open | job_started_install_fail | Scaffold ≠ integration proof. **NOT MERGED.** |
| [#211](https://github.com/ChristianV997/NeuroTopology-Sim/pull/211) | draft | `cursor/streaming-performance-benchmarks` `54c24694` | `main` | keep_open | disk_fail (verified ENOSPC) | Stack root. tracemalloc ≠ RSS. Stand-in workload ≠ science. |
| [#212](https://github.com/ChristianV997/NeuroTopology-Sim/pull/212) | no | `codex/interop-signal-contracts` `a21dcb24` | `main` | keep_open | disk_fail (verified ENOSPC) | Contracts only. Parent of #220. Contracts ≠ adapters supported. |
| [#213](https://github.com/ChristianV997/NeuroTopology-Sim/pull/213) | no | `antigravity/test-isolation-dependency-profiles` `f23c7ef7` | `main` | needs_human_review | billing_not_started | CI profiles + isolated runner. Parent of #227. Overlaps #222. |
| [#214](https://github.com/ChristianV997/NeuroTopology-Sim/pull/214) | no | `antigravity/mne-scipy-streaming-eeg` `8aed328f` | `main` | needs_human_review | billing_not_started | BTC-ICFT MNE streaming. Parallel to #220 (no file overlap). |
| [#215](https://github.com/ChristianV997/NeuroTopology-Sim/pull/215) | draft | `cursor/rss-memory-telemetry` `0dadb61b` | **#211** `54c24694` | keep_open | billing_not_started | STACKED on #211. RSS vs tracemalloc; numbers unverified. |
| [#216](https://github.com/ChristianV997/NeuroTopology-Sim/pull/216) | draft | `grok-bot/evidence-bundle-release` `9c862d90` | `main` | needs_human_review | billing_not_started | Schema/compiler authority. Docs-only supersede candidate vs #225. Do not close. |
| [#217](https://github.com/ChristianV997/NeuroTopology-Sim/pull/217) | no | `grok/tool-registry-admission` `ffc8f6df` | `main` | needs_human_review | billing_not_started | Registry. Continued by #223 (git ancestry). |
| [#218](https://github.com/ChristianV997/NeuroTopology-Sim/pull/218) | draft | `claude/integration-reconciliation` `d8702e27` | `main` | keep_open | billing_not_started | Reconciliation metadata ≠ replacement implementation. |
| [#219](https://github.com/ChristianV997/NeuroTopology-Sim/pull/219) | no | `codex/bayes-falsification-hardening` `a7dd8e24` | `main` | needs_human_review | billing_not_started | Proxy ≠ formal. Related to branch-only contract. Parent of #226. |
| [#220](https://github.com/ChristianV997/NeuroTopology-Sim/pull/220) | no | `antigravity/native-signal-adapters` `5bd26dc5` | **#212** `a21dcb24` | needs_human_review | billing_not_started | STACKED on #212. Unmerged adapters ≠ supported. |
| [#221](https://github.com/ChristianV997/NeuroTopology-Sim/pull/221) | no | `antigravity/legacy-timeout-repair` `a9aba515` | `main` | keep_open | billing_not_started | Legacy test/path repairs. Not scientific PASS. |
| [#222](https://github.com/ChristianV997/NeuroTopology-Sim/pull/222) | no | `codex/ci-root-cause-and-green` `14bce7f7` | `main` | needs_human_review | billing_not_started | Parallel CI repair vs #227. Author 117 tests unverified (jobs not started). |
| [#223](https://github.com/ChristianV997/NeuroTopology-Sim/pull/223) | no | `grok/tool-capability-snapshot` `e0e61618` | `main` | needs_human_review | billing_not_started | Continues #217; GitHub base is still `main`. |
| [#224](https://github.com/ChristianV997/NeuroTopology-Sim/pull/224) | draft | `cursor/adaptive-streaming-budget` `507625f1` | **#215** `0dadb61b` | keep_open | billing_not_started | STACKED on #215. Planner estimate ≠ RSS guarantee. |
| [#225](https://github.com/ChristianV997/NeuroTopology-Sim/pull/225) | draft | `cursor/release-evidence-compilation-9077` `a3f7e7e8` | `main` | needs_human_review | billing_not_started | Inventory-docs supersede of #216 docs only. Leave this pack’s files untouched. |
| [#226](https://github.com/ChristianV997/NeuroTopology-Sim/pull/226) | no | `codex/falsification-consumer-semantics` `099b949b` | **#219** `a7dd8e24` | needs_human_review | billing_not_started | STACKED on #219. Proxy remains proxy. |
| [#227](https://github.com/ChristianV997/NeuroTopology-Sim/pull/227) | no | `codex/ci-install-reliability` `f1796a0b` | **#213** `f23c7ef7` | needs_human_review | billing_not_started | Exists. STACKED on #213, not #222. |
| [#228](https://github.com/ChristianV997/NeuroTopology-Sim/pull/228) | draft | `claude/merge-gate-policy` `6893002a` | `main` | keep_open | billing_not_started | Policy layer only. Does not merge/close PRs. |
| [#229](https://github.com/ChristianV997/NeuroTopology-Sim/pull/229) | no | `grok/dataset-provenance-contract` `6a7ec19d` | `main` | keep_open | billing_not_started | Local-first provenance. No downloads. |
| [#230](https://github.com/ChristianV997/NeuroTopology-Sim/pull/230) | draft | `cursor/performance-regression-policy` `a4d0e778` | `main` | keep_open | billing_not_started | Related domain to #211 stack; no file overlap; base is `main`. |
| [#231](https://github.com/ChristianV997/NeuroTopology-Sim/pull/231) | no | `codex/ci-evidence-preflight` `1c3916a5` | `main` | keep_open | billing_not_started | Read-only CI diagnostics. Does not replace #213/#222/#227. |
| [#232](https://github.com/ChristianV997/NeuroTopology-Sim/pull/232) | draft | `cursor/streaming-checkpoints-replay-64cc` `2ebe094b` | **#224** `507625f1` | keep_open | billing_not_started | STACKED on #224. Engineering replay ≠ scientific PASS. |
| [#233](https://github.com/ChristianV997/NeuroTopology-Sim/pull/233) | no | `antigravity/interop-conformance` `825858d5` | `main` | needs_human_review | billing_not_started | Conformance consumer of #212/#214/#220. |

Full SHAs, rollup counts, and annotations live in `configs/release/pr_retirement_matrix.yaml`.

---

## Branch-only (key remotes, no PR)

| ID | Branch / tip | vs `main` | PR? | `status_hint` | Notes |
| --- | --- | --- | --- | --- | --- |
| `nts-branch-scientific-falsification-contract` | `codex/scientific-falsification-contract` `111d4fc0` | ahead 1 / behind 0 | **none** (`gh pr list --head` empty, `--state all`) | needs_human_review | Required relationship vs #219. SCIENTIFIC_REVIEW_REQUIRED. |
| `nts-branch-grok-tool-admission-research` | `grok/tool-admission-research` `1dac04d6` | ahead 5 / behind 0 | **none** | keep_open | Catalog ≠ admission ≠ evidence. Different paths from #217. |

Many older remotes exist (historical Claude/Codex/Copilot lanes). They were listed via `gh`/API for context. This register does **not** invent retirement rows for leftover remotes that already merged (example: `codex/disorder-averaged-collective-modes` still points at merged #184 `abba063f`). That leftover is not new work.

---

## CI blockers

| Class | PRs | What was verified |
| --- | --- | --- |
| `billing_not_started` | #209, #213–#233 | `core-tests` annotation is the payments / spending-limit text; `steps: []`. |
| `disk_fail` | #206, #211, #212 | Failed logs this run contain `OSError: [Errno 28] No space left on device` during pip install. Pytest skipped. |
| `job_started_install_fail` | #207, #208, #210 | Jobs started; failed at *Install root dependencies*; pytest skipped. ENOSPC string not re-fetched for these three here. |

Awareness-tests **SUCCESS** appears on some older rollups (#206–#208, #210–#212). That does **not** make the PR green. Required `core-tests` still failed before or without pytest.

`mergeStateStatus=UNSTABLE` on every open PR. UNSTABLE ≠ pass.

---

## Scientific blockers (warnings only)

These are **warnings for Research**, not executed falsification results.

- No scientific `PASS` from this register.
- Synthetic ≠ biological evidence (#208 sidecar; #211/#215/#224/#232 performance fixtures; author-claimed pytest counts).
- Proxy Bayes ≠ formal Bayes factors (on-main `bayes_factor`; #219; #226; branch-only scientific-falsification-contract).
- Independently verified process-memory (RSS vs tracemalloc) numbers: **unavailable**. Do not collapse author #215 columns.
- Missing / unmerged adapters ≠ supported (#212 contracts; #220 unmerged; #214 is a different path).
- #218 reconciliation report ≠ integration proof.
- #209 retrofit inventory is author-described as `not_evidence`.
- Do not cite `codex/scientific-falsification-contract` as a merged contract (no PR).

---

## Next action (Research)

1. Classify claim surfaces for **#223–#233** and the two BRANCH_ONLY rows against **this** retirement matrix. Do not rewrite #216/#225 evidence-pack files.
2. Keep stacked chains explicit. Do not recommend retiring a child before its parent.
3. Do not finalize `DUPLICATE` or `SUPERSEDED` beyond the cited **#216 inventory-docs** candidate.
4. Restate: billing ≠ pass; disk ≠ pass; proxy Bayes ≠ formal; synthetic ≠ biology; inventory ≠ evidence.
5. Hand relationship edges to QA, then Integration. Lead does not merge.

**Merger: do not merge.**

---

## Research scientific / infra classification

**Phase:** RESEARCH  
**Classified at:** 2026-09-06  
**Classifier:** `research_and_tooling`  
**Base Lead commit:** `c87f97b01cf8612d65564f5fb61d345c70fe7c2a`  
**Owned files still only:** `configs/release/pr_retirement_matrix.yaml`, this document  

This section classifies every Lead inventory row (#206–#233 plus both BRANCH_ONLY remotes). It does **not** replace the Lead snapshot, change any `status_hint`, invent `DUPLICATE` / whole-PR `SUPERSEDED`, or authorize a merge.

**Inventory ≠ evidence.**  
**Scientific PASS from this pack: false.**  
**Biological evidence from this pack: false.**  
**Merger: do not merge. Do not mark ready. Do not close any PR.**

### Lead warnings restated (still in force)

1. **PRs are not merged unless GitHub says so.** Every open PR in the #206–#233 wave remains `state=OPEN` and `mergedAt=null` in the Lead snapshot this pack classifies.
2. **CI billing failure ≠ passing tests.** `billing_not_started` jobs have empty step lists. That is not a pass.
3. **Disk-full / install CI failure ≠ passing tests.** Verified ENOSPC on #206/#211/#212; same install-step pattern on #207/#208/#210. Pytest was skipped.
4. **Synthetic ≠ biological evidence.** Synthetic fixtures, lattice campaigns, and performance stand-in workloads cannot establish scientific `PASS` or biological evidence.
5. **Proxy Bayes ≠ formal Bayes factors.** On-main `bayes_factor` is a descriptive RSS / Gaussian residual likelihood-ratio proxy. Open #219 / #226 and the branch-only scientific-falsification contract do not convert that into formal K.
6. **Inventory ≠ evidence.** This register is not a compiled evidence bundle and is not a second #216/#225 evidence authority.
7. **#218 reconciliation metadata ≠ replacement implementation.**
8. **Missing / unmerged adapters ≠ supported.**
9. **Do not invent DUPLICATE or SUPERSEDED** without cited GitHub metadata, PR body, or base/head overlap.
10. **Do not retire a stacked child before its parent.** Verified stacks: **#211 → #215 → #224 → #232**, **#212 → #220**, **#219 → #226**, **#213 → #227**.

`status_hint` values remain Lead-only: `keep_open` or `needs_human_review`. Research did not change them.

### Classification table (#206–#233 + BRANCH_ONLY)

`scientific_pass_allowed` is **false** on every row. `biological_evidence` is **false** on every row. `empirical_claim_present` is **false** on every row.

| ID | Relevance | `evidence_mode` | `changes_scientific_semantics` | Proxy flag | One-line note |
| --- | --- | --- | --- | --- | --- |
| #206 | tooling (+ infrastructure) | none | false | false | Env config only. Not a scientific surface. |
| #207 | performance (+ engineering) | synthetic | false | false | Lindblad buffer reuse. Bit-identical / speedup unverified. |
| #208 | engineering (+ scientific-adjacent) | synthetic | false | false | RunRecord sidecar; no K; SCIENTIFIC_REVIEW; not PASS. |
| #209 | tooling (+ governance) | none | false | false | Retrofit inventory is `not_evidence`. |
| #210 | engineering | unavailable | false | false | Scaffold ≠ integration proof. |
| #211 | performance | synthetic | false | false | Stack root. Stand-in / tracemalloc ≠ science. |
| #212 | interoperability (+ governance) | none | false | false | Contracts ≠ adapters supported. Parent of #220. |
| #213 | infrastructure | none | false | false | CI profiles. Parent of #227. |
| #214 | engineering (+ interoperability) | unavailable | false | false | EEG MNE streaming; domain-parallel to #220; not empirical PASS. |
| #215 | performance | unavailable | false | false | STACKED on #211. RSS vs tracemalloc unverified. |
| #216 | governance | none | false | false | Schema/compiler authority. Docs-only supersede candidate vs #225. |
| #217 | tooling | unavailable | false | false | Registry. Continued by #223. Catalog ≠ evidence. |
| #218 | tooling (+ governance) | none | false | false | Reconciliation metadata ≠ replacement. |
| #219 | scientific | **proxy** | **true** | **true** | Contract language only. Proxy ≠ formal K. Not PASS. |
| #220 | interoperability | unavailable | false | false | STACKED on #212. `adapters_supported: false`. |
| #221 | engineering | unavailable | false | false | Legacy timeout/path repair. Not scientific PASS. |
| #222 | infrastructure | unavailable | false | false | Parallel / diverged vs #227. Not a duplicate. |
| #223 | tooling | unavailable | false | false | Continues #217 (ancestry). Catalog ≠ evidence. Not a duplicate. |
| #224 | performance | synthetic | false | false | STACKED on #215. Planner estimate ≠ RSS guarantee. |
| #225 | documentation (+ governance) | none | false | false | Docs-supersedes #216 inventory only. Schema stays on #216. |
| #226 | scientific | **proxy** | **true** | **true** | STACKED on #219. Proxy remains proxy. Not formal K. |
| #227 | infrastructure | unavailable | false | false | STACKED on #213, not #222. Diverged from #222. |
| #228 | governance | none | false | false | Merge-gate policy ≠ merge action. |
| #229 | governance (+ documentation) | none | false | false | Local-first provenance. No downloads. Not empirical PASS. |
| #230 | governance (+ performance) | none | false | false | Related domain to #211 stack; base `main`; no file overlap. |
| #231 | infrastructure | none | false | false | Read-only CI preflight. Does not replace #213/#222/#227. |
| #232 | performance (+ engineering) | synthetic | false | false | STACKED on #224. Engineering replay ≠ scientific PASS. |
| #233 | interoperability | unavailable | false | false | Conformance consumer of #212/#214/#220. Not a replacement. |
| `codex/scientific-falsification-contract` | scientific | **proxy** | **true** | **true** | BRANCH_ONLY. Diverged vs #219. SCIENTIFIC_REVIEW_REQUIRED. No PR. |
| `grok/tool-admission-research` | tooling | none | false | false | BRANCH_ONLY. Catalog ≠ admission ≠ evidence. |

### Duplicates and supersedes

**Verified duplicates: none.** `duplicate_candidates` stays empty. `research_phase.duplicate_candidates_verified` is empty.

Related pairs that remain **not** `DUPLICATE`:

- #214 vs #220 — `domain_parallel`, zero path overlap
- #222 vs #227 — infrastructure-only parallel, git-diverged; #227 stacked on #213
- #219 vs `codex/scientific-falsification-contract` — `diverged_scientific` (shared Bayesian file; other files differ)
- #217 vs #223 — tooling continuation via ancestry, not a duplicate
- #216 vs #225 — docs overlap only

**Superseded candidates (unchanged, docs-only):** #216 inventory docs by #225. Scope is `docs/release/{README.md,agent_contribution_matrix.yaml,current_state.md}` only. Whole-PR #216 is **not** superseded. Schema / compiler / `tests/release/**` stay on #216. Do not close #216.

No other SUPERSEDED label is claimed.

### Stacked chains (do not retire children first)

| Chain | Kind | Research overlap |
| --- | --- | --- |
| **#211 → #215 → #224 → #232** | performance / infrastructure stack | `infrastructure_only` |
| **#212 → #220** | interoperability stack | scientific overlap `none`; adapters still unsupported |
| **#219 → #226** | scientific stack | `semantic`; proxy remains proxy |
| **#213 → #227** | CI infrastructure stack | `infrastructure_only` |
| #217 → #223 | tooling continues (ancestry, GitHub base is `main`) | scientific overlap `none` |
| #233 → #212 / #214 / #220 | conformance consumer | scientific overlap `none` |

Retiring a child before its parent would orphan stacked GitHub bases. Research does not recommend that.

### Scientific blockers (still warnings, not results)

- No scientific `PASS` from this classification pack.
- Synthetic ≠ biological evidence (#208 sidecar; #211/#215/#224/#232 performance fixtures).
- Proxy Bayes ≠ formal Bayes factors (#219, #226, branch-only scientific-falsification-contract). `proxy_evidence_flag` is true on those three only.
- Independently verified RSS vs tracemalloc numbers: **unavailable**.
- Missing / unmerged adapters ≠ supported (`adapters_supported: false` on #212, #214, #220, #233).
- #218 reconciliation report ≠ integration proof.
- CI billing ≠ pass. Disk ENOSPC ≠ pass.

### Next action (QA)

Hand this matrix to QA for `tests/release/test_pr_retirement_matrix.py` **fail-closed** rules. Research did **not** create that test file or `scripts/validate_pr_retirement_matrix.py`.

Suggested fail-closed checks (QA owns the implementation):

- Every row #206–#233 and both BRANCH_ONLY rows have `research_classification.status: classified`.
- `scientific_pass_allowed: false` and `biological_evidence: false` everywhere.
- `proxy_evidence_flag: true` only on #219, #226, and the scientific-falsification branch.
- `adapters_supported: false` on #220 (and false/null on #212/#214/#233).
- `duplicate_candidates` empty; superseded only the docs-only #216 → #225 candidate.
- Lead `status_hint` remains `keep_open` or `needs_human_review` only.
- Stacked children must not be marked retire-before-parent.

Integration owns any later merger recommendation. **Merger: do not merge.**
