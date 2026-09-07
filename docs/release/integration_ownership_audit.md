# Integration ownership audit — Lead decisions log

**Phase:** Lead only (coordinate + record)  
**Inspected:** 2026-09-07  
**Repository:** https://github.com/ChristianV997/NeuroTopology-Sim  
**Live `origin/main`:** `62aa8fee786abf916ab0aa2b7e7b91c570fee119` (`#221`)  
**Evidence source:** `gh` + GitHub API (live). Disposable worktree from `origin/main`. Primary checkout left untouched.  
**Owned files:** `configs/release/integration_ownership.yaml`, this log.  
**Not created:** `scripts/validate_integration_ownership.py` (Release), `tests/release/test_integration_ownership.py` (QA).  
**Not modified:** production scientific code, reconciliation tools, merge-gate, CI, adapters, topology, streaming, Bayesian, artifacts, datasets, credentials, packs `#216` / `#225` / `#237` / `#242`.

This pack is an **audit inventory**. It is not a merger, not compiled evidence, and not a scientific verdict.

**CURRENT_INTEGRATION_HEAD:** `af3ac584419148ddcfc57cb565c416eba6328725`

**Merger:** Codex C is the sole merger. Do not merge. Do not close. Do not retarget PRs.

---

## Required decisions (read first)

1. **Codex C is the sole merger.** This Lead pack records GitHub metadata. It does not merge, close, or retarget any PR.
2. **This pack is audit-only.** Inventory rows are not evidence and cannot establish scientific `PASS`.
3. **Synthetic is `NOT_SUPPORTED`.** Synthetic, invalid, incomplete-provenance, and proxy comparisons cannot produce empirical `PASS`.
4. **Proxy Bayes ≠ formal.** On-main and integration Bayes-factor paths remain RSS / Gaussian-likelihood proxies. They are not formal marginal-likelihood `K`. Formal likelihood validation is still required before strong empirical interpretation.
5. **`INTEGRATED_ONLY` ≠ merged into main.** Presence on `codex/integration-all-open-prs` (PR `#236`) or a GitHub merge into a **non-main** base is not a main-line merge. `VERIFIED` is used only when GitHub reports `merged=true` **and** the merge commit is on `origin/main`.

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

## Placeholders (null until supplied)

| Slot | Value | Owner |
| --- | --- | --- |
| `alfred_ownership_graph` | `null` | Alfred |
| `researchy_findings` | `null` | Researchy |
| `nightly_findings` | `null` | Nightly |
| `lingxi_findings` | `null` | Lingxi |

Lead does not invent an Alfred graph or Researchy / Nightly / Lingxi classifications.

---

## What later phases must not do from this pack

- Release: do not invent `scripts/validate_integration_ownership.py` until handed this inventory and the Alfred graph.
- QA: do not invent `tests/release/test_integration_ownership.py` yet.
- Do not rewrite `#216` / `#225` / `#237` / `#242`.
- Do not treat `#220` or `#215` as `VERIFIED` on `main` because GitHub `merged=true` on a **stacked** base.
- Do not treat `#236` or `af3ac584…` as merged into `main`.
- Do not promote synthetic or proxy-Bayes rows to empirical `PASS`.

---

## Next

**NEXT = wait Alfred, then Researchy.**

1. Alfred supplies `alfred_ownership_graph` (still `null`).
2. Researchy (then Nightly / Lingxi) classify findings into the null slots.
3. Codex C remains the only merger. **Do not merge this PR.**
