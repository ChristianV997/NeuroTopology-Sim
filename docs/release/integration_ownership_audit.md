# Integration ownership audit — Lead decisions log

**Phase:** Lead only (coordinate + record)  
**Inspected:** 2026-09-07  
**Repository:** https://github.com/ChristianV997/NeuroTopology-Sim  
**Live `origin/main`:** `62aa8fee786abf916ab0aa2b7e7b91c570fee119` (`#221`)  
**Evidence source:** `gh` + GitHub API (live). Disposable worktree from `origin/main`. Primary checkout left untouched.  
**Owned files:** `configs/release/integration_ownership.yaml`, this log.  
**Not created:** `scripts/validate_integration_ownership.py` (Release), `tests/release/test_integration_ownership.py` (QA).  
**Not modified:** production scientific code, reconciliation tools, merge-gate, CI, adapters, topology, streaming, Bayesian, artifacts, datasets, credentials, packs `#216` / `#225` / `#237` / `#242`.  
**Evidence authority:** Release owns those four packs. This inventory is not a second evidence compiler.

This pack is an **audit inventory**. It is not a merger, not compiled evidence, and not a scientific verdict.

**CURRENT_INTEGRATION_HEAD:** `af3ac584419148ddcfc57cb565c416eba6328725`

**Merger:** Codex C is the sole merger. Do not merge. Do not close. Do not retarget PRs.  
**Bots used:** Alfred + Lead.  
**Alfred:** organization/ownership audit + duplicate decisions folded (done).

---

## Required decisions (read first)

1. **Codex C is the sole merger.** This Lead pack records GitHub metadata. It does not merge, close, or retarget any PR. Do not compete with Codex C.
2. **This pack is audit-only.** Inventory rows are not evidence and cannot establish scientific `PASS`. **Release** is the sole evidence authority for packs `#216` / `#225` / `#237` / `#242`. No second evidence authority.
3. **Synthetic is `NOT_SUPPORTED`.** Synthetic, invalid, incomplete-provenance, and proxy comparisons cannot produce empirical `PASS`.
4. **Proxy Bayes ≠ formal.** On-main and integration Bayes-factor paths remain RSS / Gaussian-likelihood proxies. They are not formal marginal-likelihood `K`. Formal likelihood validation is still required before strong empirical interpretation.
5. **`INTEGRATED_ONLY` ≠ merged into main.** Presence on `codex/integration-all-open-prs` (PR `#236`) or a GitHub merge into a **non-main** base is not a main-line merge. `VERIFIED` is used only when GitHub reports `merged=true` **and** the merge commit is on `origin/main`.
6. **Live `#236` `headRefOid` is the only `CURRENT_INTEGRATION_HEAD`.** Reconfirmed `2026-09-07` via `gh`: still `af3ac584419148ddcfc57cb565c416eba6328725`. Open, not merged.

---

## Live PR `#236` verification

Fetched with `gh pr view 236 --json` plus GitHub `pull_request_read` (`get`, `get_status`, `get_check_runs`, `get_commits`, `get_files`).

| Field | Live value |
| --- | --- |
| URL | https://github.com/ChristianV997/NeuroTopology-Sim/pull/236 |
| Title | Integration: merge validated open PR groups |
| `state` | `OPEN` |
| `isDraft` | `false` |
| `merged` / `mergedAt` | `false` / `null` |
| `mergeable` | `MERGEABLE` |
| `mergeStateStatus` | `UNSTABLE` |
| `baseRefName` | `main` |
| `baseRefOid` | `62aa8fee786abf916ab0aa2b7e7b91c570fee119` |
| `headRefName` | `codex/integration-all-open-prs` |
| **`headRefOid` (CURRENT)** | **`af3ac584419148ddcfc57cb565c416eba6328725`** |
| `changedFiles` | `140` |
| `commits` | `98` |
| `additions` / `deletions` | `18527` / `1460` |
| Combined commit status | `pending`, `total_count=0` |
| Updated | `2026-09-07T04:24:48Z` |

GitHub does **not** report `#236` merged into `main`. The live head is **not** an ancestor of `origin/main`.

### Check rollup summary (live head)

Required / image / e2e jobs on `af3ac5844191…` completed `FAILURE` in about **three seconds** (`core-tests` and `awareness-tests`: `2026-09-07T04:24:11Z` → `04:24:14Z`). `Production root image (manual opt-in)` is `SKIPPED`. `copilot-pull-request-reviewer` is `FAILURE`.

Failed names: Python 3.11 offline tests; DS005620 E2E Mock Run; Root sim engine CPU/base image; ontology-claim-language; core-tests; Cross-system smoke; Python 3.12 offline tests; Awareness Studio image; awareness-tests.

That rollup supports **`BLOCKED_BY_CI`** as a check-surface label. It does **not** support **`BLOCKED_BY_TESTS`**: a ~3s completion is not a pytest-node log. Lead did not copy billing text from the older `#242` / `be277ecd` snapshot onto this new head without a new Copilot/billing read.

Author-claimed isolated run on the `#236` body (415 files / 75 batches / 64 passed / 8 failed / 3 timed out / exit 124) is **unverified** here.

---

## Reported SHAs vs live OID

Work-order / prior packs reported `be277ecdac301d49dca27ef9612ebe6c560245ad` and short `af3ac584`.

| SHA | Live fact | Lead label |
| --- | --- | --- |
| `af3ac584419148ddcfc57cb565c416eba6328725` | Live `headRefOid`. Message: “Complete release validation evidence”. Parent is `be277ecd`. | **`CURRENT_INTEGRATION_HEAD` only.** `OPEN_REVIEW` + `BLOCKED_BY_CI`. **Not merged into main.** |
| `be277ecdac301d49dca27ef9612ebe6c560245ad` | Present in `#236` commit list. Immediate parent of the live head. Cited as current by draft `#242` and that pack’s `blocker_registry.yaml`. | **Intermediate / `INTEGRATED_ONLY`-candidate.** On `#236` history only. **Not merged into main.** |
| `af3ac584` (8-char prefix) | Matches the **live** full OID above. Not a second commit. | Current-head prefix. Do not treat as a distinct intermediate SHA. **Not merged into main.** |
| `af3ac584277747ae29882d3f5a39af5c4a436f22` | Cited as “Final commit” on the `#236` body. `gh api …/commits/<sha>` → **HTTP 422 No commit found**. | **`UNVERIFIED` / not found.** Prefix collision with the live head only. Never call this merged. |

`CURRENT_INTEGRATION_HEAD` is set to the live OID only. Older reports that still say `be277ecd` are stale.

---

## Seeded ownership statuses

Statuses are assigned only where GitHub metadata supports them. Otherwise `UNVERIFIED` or `NEEDS_HUMAN_REVIEW`. `BLOCKED_BY_TESTS`, `BLOCKED_BY_SCIENCE`, `DUPLICATE`, and `SUPERSEDED` are **unused** as primary row statuses in this seed (no GitHub pytest-node log, no GitHub science-hold field, no GitHub duplicate-close, no GitHub un-merge of `#216`).

| ID | PR / branch | GitHub | Status | Why |
| --- | --- | --- | --- | --- |
| `nts-io-pr-236` | `#236` | OPEN, not draft, not merged | `OPEN_REVIEW` (`ci_status: BLOCKED_BY_CI`) | Live integration vehicle. `UNSTABLE` + 9× FAILURE ~3s. |
| `nts-io-pr-242` | `#242` | OPEN **draft**, not merged | `OPEN_REVIEW` (`ci_status: BLOCKED_BY_CI`) | Release blocker-triage pack. Do not modify. Cited head `be277ecd` is stale. |
| `nts-io-pr-237` | `#237` | OPEN, not draft, not merged | `OPEN_REVIEW` (`ci_status: BLOCKED_BY_CI`) | Retirement register. `#236` body: do-not-merge. `core-tests` FAILURE after ~46m — log unread; not `BLOCKED_BY_TESTS`. Do not modify. |
| `nts-io-pr-225` | `#225` | OPEN, not merged | `OPEN_REVIEW` | Inventory-docs PR still open vs main. Also appears in `#236` history (`c8f8a694`) → that presence is `INTEGRATED_ONLY` on `#236`, not a main merge. Required-check rollup missing on the fetched page → CI `UNVERIFIED`. |
| `nts-io-pr-216` | `#216` | **MERGED** into `main` `2026-09-06T22:32:36Z` | **`VERIFIED`** | Merge commit `a91913c` is on `origin/main`. Author `#225`/`#236` “supersede inventory docs” text is **not** a GitHub un-merge. Not labeled `SUPERSEDED`. |
| `nts-io-pr-214` | `#214` | MERGED into `main` | **`VERIFIED`** | Merge commit `3970b0a` on `origin/main`. Pair `#214/#220`. |
| `nts-io-pr-220` | `#220` | MERGED, **base = `#212` branch** | **`INTEGRATED_ONLY`** | `merged=true` into `codex/interop-signal-contracts`, not `main`. Merge commit `8094f5d` is **not** on `origin/main`. Present on `#236`. |
| `nts-io-pr-222` | `#222` | OPEN, not merged | `OPEN_REVIEW` | Pair `#222/#227`. Fetched check_runs: Copilot only → CI `UNVERIFIED`. |
| `nts-io-pr-227` | `#227` | OPEN; base = `#213` branch | `OPEN_REVIEW` (`ci_status: BLOCKED_BY_CI`) | Stacked on already-merged `#213`. ~3s FAILURE rollup. Also on `#236` history (`ea2d30ff`). |
| `nts-io-pr-219` | `#219` | MERGED into `main` | **`VERIFIED`** | Merge commit `93b98cf` on `origin/main`. Bayes-hardening PR. Proxy Bayes still ≠ formal `K`. |
| `nts-io-branch-scientific-falsification-contract` | `codex/scientific-falsification-contract` | Branch tip `111d4fc`; **no PR** | `UNVERIFIED` (presence on `#236`: `INTEGRATED_ONLY`) | `gh pr list --head` empty. `#236` body: topology-only retained; `#219` authoritative for Bayesian. Not merged into `main` as this branch. |
| `nts-io-pr-211` | `#211` | MERGED into `main` | **`VERIFIED`** | Merge commit `a661d0a` on `origin/main`. Chain root `#211→#215→#224`. |
| `nts-io-pr-215` | `#215` | MERGED, **base = `#211` branch** | **`INTEGRATED_ONLY`** | Stacked merge after `#211` already landed on `main`. Merge commit `1feb71c` **not** on `origin/main`. |
| `nts-io-pr-224` | `#224` | OPEN; base = `#215` branch | `OPEN_REVIEW` (`ci_status: BLOCKED_BY_CI`) | Still open stacked child. Also on `#236` history. |
| `nts-io-sha-be277ecd-intermediate` | `#236` ancestor | Not on `main` | **`INTEGRATED_ONLY`** | Intermediate / `INTEGRATED_ONLY`-candidate. |

`#206`, `#207`, `#208` remain `OPEN` (`mergedAt=null`) as named leftovers on the `#236` body. Recorded as context `OPEN_REVIEW` only.

Companions already on `origin/main` and named by `#236` (`#209`, `#210`, `#212`, `#213`, `#217`, `#218`, `#221`) are `VERIFIED` companions, not this pack’s write set.

---

## Alfred ownership graph (folded)

Alfred’s lane is **organization / ownership audit + duplicate decisions only**. It is done. Lead recorded the graph; Lead does not merge.

| Role | Who | Scope |
| --- | --- | --- |
| Human | Christian V. | Human owner |
| Lead Developer | Lead | Work-order owner/assigner; record decisions; **no merge** |
| Alfred | Alfred | Organization/ownership audit + duplicate decisions only (**done**) |
| Integration | Integration | Contracts and dependency order; **reject competing queues** |
| Research and Tooling | Research and Tooling | Official-source tooling, **this-repo** lane |
| QA | QA | Reproduce/diff when a repair is boarded |
| Release | Release | **Sole evidence authority** for packs `#216` / `#225` / `#237` / `#242` — no second evidence authority |
| Codex C | Codex C | **Sole merger** — do not compete |

`alfred_ownership_graph.status` is `recorded`. `CURRENT_INTEGRATION_HEAD` stays the live GitHub `#236` OID.

### This-wave duplicate / NO ACT

These are **not** GitHub merge statuses. They are Alfred duplicate-bot decisions so competing queues are not opened.

| Bot | Decision | This wave |
| --- | --- | --- |
| Researchy (vs Research and Tooling) | **out** | NO ACT |
| Nightly Audit Engineer | **out** | NO ACT |
| Lingxi’s Engineer Bot | **out until Lead assigns post-audit** | NO ACT |
| Chief of Staff | **digest later only** | NO ACT |
| tinkabot | **out** | NO ACT |
| New empty bots | **default zero** | NO ACT |

`researchy_findings` / `nightly_findings` / `lingxi_findings` remain `null` because those bots do **not** act this wave. Do not wait on them for this pack.

---

## What later phases must not do from this pack

- Do not invent a second evidence authority beside Release for `#216` / `#225` / `#237` / `#242`.
- Release: do not invent `scripts/validate_integration_ownership.py` in this Lead write set.
- QA: reproduce/diff only when a repair is boarded; do not invent `tests/release/test_integration_ownership.py` here.
- Integration: contracts/dependency order only; reject competing queues (Researchy / Nightly / Lingxi / tinkabot / empty bots).
- Do not rewrite `#216` / `#225` / `#237` / `#242`.
- Do not treat `#220` or `#215` as `VERIFIED` on `main` because GitHub `merged=true` on a **stacked** base.
- Do not treat `#236` or `af3ac584…` as merged into `main`.
- Do not promote synthetic or proxy-Bayes rows to empirical `PASS`.
- Do not compete with Codex C on merge.

---

## Next

**NEXT = Alfred folded; this-wave duplicates are NO ACT. Do not merge.**

1. Alfred ownership graph is recorded (`status: recorded`).
2. Researchy / Nightly / tinkabot / new empty bots are **out**. Lingxi waits for a Lead post-audit assignment. Chief of Staff is digest-later only.
3. Integration may order contracts/dependencies; it must reject competing queues.
4. Codex C remains the only merger. **Do not merge this PR.**

---

## Research claim labeling

**Phase:** RESEARCH (additive on Lead inventory).
**Classifier:** Research and Tooling (`research_and_tooling`).
**Classified:** 2026-09-07.
**Base Lead commit:** `95e910a015f5a0256458a96fedc6137cfac1c35a`.
**CURRENT_INTEGRATION_HEAD (unchanged):** `af3ac584419148ddcfc57cb565c416eba6328725`.
**Researchy:** **NO ACT** this wave. Research and Tooling owns this labeling. Do not wait on Researchy findings.

This section **does not** change Lead `status` values (`VERIFIED` / `INTEGRATED_ONLY` / `OPEN_REVIEW` / `UNVERIFIED` / etc.). It separates **engineering facts** (GitHub-supported) from **scientific claims**. The inventory is not evidence. `empirical_pass_from_this_pack: false`. Synthetic remains **`NOT_SUPPORTED`**. Proxy Bayes ≠ formal `K`. **`INTEGRATED_ONLY` ≠ merged into `main`.**

Author body SHA `af3ac584277747ae29882d3f5a39af5c4a436f22` stays **`UNVERIFIED`** (HTTP 422). Live `#236` head is `af3ac5844191…`; `be277ecd` is intermediate.

Alfred six-member graph and this-wave NO ACT list stay as Lead recorded.

### Work-item labels

| ID | `fact_kind` | scientific `claim_status` | `exceeds_evidence` | Note |
| --- | --- | --- | --- | --- |
| `nts-io-pr-236` | mixed | `NOT_SUPPORTED` | true | OPEN vs main; `BLOCKED_BY_CI` ~3s; 140 files; head `af3ac5844191`. Author isolated counts unverified. Body Final commit SHA UNVERIFIED if treated as live head. Synthetic `NOT_SUPPORTED`. |
| `nts-io-pr-242` | mixed | none | false | Governance/engineering blocker triage. Cited head `be277ecd` stale. Inventory not evidence. Do not rewrite. |
| `nts-io-pr-237` | governance | none | false | Retirement register. Inventory not evidence. Do not rewrite. |
| `nts-io-pr-225` | governance | none | false | OPEN inventory supersede claim. `#216` still `VERIFIED` on main. Do not mark `#216` `SUPERSEDED`. Inventory not evidence. |
| `nts-io-pr-216` | governance | none | false | `VERIFIED` on main is an engineering fact, not scientific `PASS`. Evidence pack — do not rewrite. |
| `nts-io-pr-214` | engineering | none | false | `VERIFIED` EEG streaming. Not `PASS`. |
| `nts-io-pr-220` | engineering | none | false | `INTEGRATED_ONLY` (merged to `#212` branch, not main). Adapters ≠ scientific `PASS`. |
| `nts-io-pr-222` | engineering | none | false | OPEN CI work. ~3s FAILURE ≠ pytest. Not science. |
| `nts-io-pr-227` | engineering | none | false | OPEN CI work. ~3s FAILURE ≠ `BLOCKED_BY_TESTS`. Not science. |
| `nts-io-pr-219` | mixed | `proxy_not_formal` | true | `VERIFIED` on main (engineering). Proxy Bayes ≠ formal `K`. Exceeds evidence if treated as formal `K`. |
| `nts-io-branch-scientific-falsification-contract` | mixed | `proxy_not_formal` | true | `UNVERIFIED` / `BRANCH_ONLY` + `INTEGRATED_ONLY` on `#236`. No PR. Not main merge. Proxy ≠ formal. |
| `nts-io-pr-211` | engineering | `NOT_SUPPORTED` | true | `VERIFIED` performance stand-in / synthetic fixtures. Not `PASS`. |
| `nts-io-pr-215` | engineering | none | false | `INTEGRATED_ONLY` (stacked). RSS/tracemalloc telemetry. Not `PASS`. Not main. |
| `nts-io-pr-224` | engineering | none | false | OPEN stacked. Not `PASS`. |
| `nts-io-sha-be277ecd-intermediate` | engineering | none | false | `INTEGRATED_ONLY`. Not current. Not main. |

Context `#206` / `#207` / `#208`: engineering `OPEN_REVIEW`; not science.
Companions `#209` / `#210` / `#212` / `#213` / `#217` / `#218` / `#221`: `VERIFIED` on main are engineering facts only; not scientific `PASS`.

### Scientific claim issues (exceed evidence if promoted)

See `scientific_claim_issues` in `configs/release/integration_ownership.yaml`. In short: isolated 415/75/64/8/3/exit124 unverified; body SHA `af3ac5842777…` UNVERIFIED as live head; synthetic as `PASS`; proxy Bayes as formal `K`; `VERIFIED` merge as scientific `PASS`; adapters as `PASS`; `INTEGRATED_ONLY` as main merge; empty-step ~3s FAILURE as `BLOCKED_BY_TESTS`; OPEN `#225` as `SUPERSEDED` of `#216`.

### Hand-off

**NEXT_ACTION = QA.** Reproduce/diff the two owned files only. Do not invent `scripts/validate_integration_ownership.py` or `tests/release/test_integration_ownership.py` unless a repair is boarded. Do not rewrite packs `#216` / `#225` / `#237` / `#242`.

**Researchy NO ACT.** Merger: **do not merge.** Never close/retarget PRs. Codex C remains the sole merger.
