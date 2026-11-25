# Current blocker triage — Lead inventory (PR #236)

**Phase:** Lead only  
**Inspected:** 2026-09-07 via live `gh` against https://github.com/ChristianV997/NeuroTopology-Sim  
**This document is not compiled evidence and not a scientific verdict.**  
**Synthetic results remain `NOT_SUPPORTED`.** Do not invent `PASS`.  
**Merger: do not merge. Never close PRs.**

Research classifies these rows. Integration orders remediation later. QA/Release own the schema validator (`scripts/validate_release_blockers.py`, `tests/release/test_blocker_registry.py`) — not invented in this pack.

Marketplace bot added: **Alfred** (governance only). No other marketplace bots were invented.

---

## CURRENT_INTEGRATION_HEAD

| Field | Live `gh` value |
| --- | --- |
| PR | [#236](https://github.com/ChristianV997/NeuroTopology-Sim/pull/236) |
| Title | Integration: merge validated open PR groups |
| Draft? | **no** (`isDraft=false`) |
| Merged? | **no** (`mergedAt=null`, `state=OPEN`) |
| `headRefName` | `codex/integration-all-open-prs` |
| `headRefOid` | `be277ecdac301d49dca27ef9612ebe6c560245ad` |
| `baseRefName` | `main` |
| `baseRefOid` | `62aa8fee786abf916ab0aa2b7e7b91c570fee119` |
| Changed files | **138** (`gh` `changedFiles`; additions 18499 / deletions 1459) |
| Commits on PR | **97** |

**Mismatch vs work-order SHA `be277ecdac301d49dca27ef9612ebe6c560245ad`:** none. Live `headRefOid` **equals** that SHA. No `CURRENT_HEAD_MISMATCH` blocker was seeded.

Authoritative `CURRENT_INTEGRATION_HEAD` for this snapshot:  
`be277ecdac301d49dca27ef9612ebe6c560245ad`.

Only that OID is **current**. Recent commits on the PR branch are listed below as **intermediate** except the last row.

| Role | OID | Headline |
| --- | --- | --- |
| intermediate | `e8aa212cf73729ff1850e47bb54c888056360a66` | Merge `origin/pr/235` |
| intermediate | `b48034e636b7ad3a79884f25a3144a8cbb86463d` | Merge `origin/pr/238` |
| intermediate | `c8f8a694a93188cd06edc6c831db3a6e4080a9e9` | Merge `origin/pr/225` |
| intermediate | `ea2d30ff4ee89aee0ce3c35bfe6b16a0215df8ac` | Merge PR #227 CI install reliability |
| intermediate | `4f6519439368dd26cbaa783b1b6d78d6bfb3d6e6` | Merge `origin/pr/231` |
| intermediate | `4ed560cac57c2193b538fcce48d12aa65e25ee76` | Merge `origin/main` (conflict resolution) |
| intermediate | `ad3540ca7f3934488320f59b5911bf6de40a963e` | Finalize integration evidence and release gate |
| **current** | `be277ecdac301d49dca27ef9612ebe6c560245ad` | Merge `origin/codex/integration-all-open-prs` (`docs/release` conflicts) |

---

## Check states on the current head

`gh pr view --json statusCheckRollup` on `be277ecd`:

| Check | Workflow | Status | Conclusion | ~duration | Classification this Lead run |
| --- | --- | --- | --- | --- | --- |
| Python 3.11 — offline tests | Awareness Studio | completed | **FAILURE** | 4s | failed on rollup; **unstarted steps** |
| Python 3.12 — offline tests | Awareness Studio | completed | **FAILURE** | 3s | failed on rollup; **unstarted steps** |
| DS005620 E2E Mock Run | DS005620 E2E | completed | **FAILURE** | 3s | failed on rollup; **unstarted steps** |
| Root sim engine CPU/base image | Docker build | completed | **FAILURE** | 3s | failed on rollup; **unstarted steps** |
| Awareness Studio image | Docker build | completed | **FAILURE** | 3s | failed on rollup; **unstarted steps** |
| Production root image (manual opt-in) | Docker build | completed | **SKIPPED** | n/a | skipped (manual opt-in) |
| ontology-claim-language | Ontology Claim Language | completed | **FAILURE** | 4s | failed on rollup; **unstarted steps** |
| core-tests | Required Checks | completed | **FAILURE** | 3s | failed on rollup; `steps=[]`; log **BlobNotFound** |
| awareness-tests | Required Checks | completed | **FAILURE** | 4s | failed on rollup; `steps=[]` |
| Cross-system smoke | Smoke | completed | **FAILURE** | 2s | failed on rollup; **unstarted steps** |

Additional check-run **not** in `statusCheckRollup`: `copilot-pull-request-reviewer` **FAILURE**.

Combined classic commit status: `state=pending`, `total_count=0` (no statuses).

**Billing vs failed vs unstarted**

- **Billing:** Copilot review on the **current** head ([review 5127101733](https://github.com/ChristianV997/NeuroTopology-Sim/pull/236#pullrequestreview-5127101733)): *“The job was not started because recent GitHub Actions payments have failed or your spending limit needs to be increased.”* Same text on earlier head `3b36cb5`. PR body and head `docs/release/unresolved_blockers.md` call this infrastructure/billing-blocked, not CI success.
- **Unstarted:** Required Checks jobs completed with **empty step lists**. Job log API for `core-tests` `101581897255` returned **BlobNotFound**. That is not a pytest log.
- **Failed (rollup):** nine required/optional workflow conclusions are `FAILURE`. Lead does **not** reclassify those as code-level test failures while logs are absent.
- **Not observed on current-head logs:** disk `Errno 28`. Historical ENOSPC on source PRs #206/#208/#210/#211/#212 is cited in on-main `docs/release/current_state.md` and seeded as a **separate** `DISK_EXHAUSTION` row with `unavailable` for `be277ecd` logs.

---

## Author-claimed isolated run (not independently re-run)

Live PR #236 body (not the work-order paraphrase):

> Mandated isolated run: **415 files / 75 bounded batches; 64 passed, 8 failed, 3 timed out; exit 124.** These outcomes remain recorded and are not represented as green.

Head `docs/release/full_test_summary.md` repeats 415 / 75 / 64 / 8 / 3 and names timeout groups. The batch JSON is described as remaining on a validation-host `%TEMP%` path; **this Lead run did not fetch it.**

The work order mentioned **401 files / 63 batches / 6 failures / 4 timeouts**. Those figures were **not** on the live PR body. Lead prefers the live `gh` body and records the 401-series as **not found**.

Author-claimed pytest counts are **unverified** here. They are not compiled evidence and not scientific `PASS`.

---

## Dashboard isolation

Head `docs/release/dashboard_isolation_report.md` states status **`PASS`** for the checked integration surface (no dashboard route imports/executes a solver).

This Lead run **did not** re-run that AST scan. Independent verification is **unavailable**. The registry seeds `nts-rb-dashboard-isolation-unverified` so QA can confirm or keep unavailable — not so anyone can invent `PASS`.

---

## Scientific / provenance

Head `docs/release/scientific_gate_report.md`: `INCONCLUSIVE / NOT RELEASE-READY`. `K > 100` remains the only empirical PASS gate. Synthetic / invalid / incomplete-provenance / proxy comparisons **cannot** produce empirical PASS. RSS/AICc/BIC remain **proxy**, not formal Bayes factors.

Synthetic results remain **`NOT_SUPPORTED`**. That is recorded as `SCIENTIFIC_REVIEW` / `PROVENANCE_INCOMPLETE` scientific impact, **not** as evidence of PASS.

---

## Process rows (do not rewrite other packs)

- **#216** live GitHub: **MERGED** (`mergedAt=2026-09-06T22:32:36Z`). **#225** live: **OPEN**, titled as superseding #216 inventory. #236 body still says “#216 is superseded by #225”. Research reconciles; this pack does **not** rewrite those evidence docs.
- **#237** live: **OPEN**. Body: no retirement finalized; do not merge; do not close any PR. This pack does **not** rewrite the retirement register.
- **#206 / #207 / #208** live: still **OPEN** (`mergedAt=null`), matching #236 “intentionally unmerged”.
- Canonical stacked **#215→#211** and **#220→#212**: GitHub now shows those PRs **MERGED**. Lead does not invent them as still-unresolved parents.
- **#239 / #240** live **OPEN** and **not** in the #236 integrated list (post-snapshot work).

Memory (RSS vs tracemalloc) numbers for the isolated run on `be277ecd` are **unavailable** (not measured here).

---

## Seeded blocker ids

See [`configs/release/blocker_registry.yaml`](../../configs/release/blocker_registry.yaml).

| id | category |
| --- | --- |
| `nts-rb-billing-236-current-head` | `BILLING_OR_RUNNER_BLOCK` |
| `nts-rb-ci-workflow-failure-236-rollup` | `CI_WORKFLOW_FAILURE` |
| `nts-rb-disk-exhaustion-source-prs` | `DISK_EXHAUSTION` |
| `nts-rb-isolated-test-failures-author-claim` | `TEST_FAILURE` |
| `nts-rb-isolated-timeouts-author-claim` | `TIMEOUT` |
| `nts-rb-optional-deps-torch-cripser` | `OPTIONAL_DEPENDENCY` |
| `nts-rb-windows-symlink-privilege` | `WINDOWS_PLATFORM` |
| `nts-rb-scientific-review-synthetic-not-supported` | `SCIENTIFIC_REVIEW` |
| `nts-rb-provenance-incomplete-empirical-gate` | `PROVENANCE_INCOMPLETE` |
| `nts-rb-stacked-206-208-unmerged` | `STACKED_PR_UNRESOLVED` |
| `nts-rb-stacked-post-integration-239-240` | `STACKED_PR_UNRESOLVED` |
| `nts-rb-duplicate-216-225-supersede` | `DUPLICATE_OR_SUPERSEDED` |
| `nts-rb-dashboard-isolation-unverified` | `DASHBOARD_ISOLATION` |
| `nts-rb-memory-evidence-unavailable` | `MEMORY_EVIDENCE` |

Not seeded as open blockers: `CURRENT_HEAD_MISMATCH` (heads match), `UNKNOWN` (unread CI logs attributed to billing + empty steps).

This pack does **not** invent the Integration remediation queue.

---

## Next action (Research)

1. Classify each registry row: billing-not-started vs true CI defect; author-claimed isolated 8 fail / 3 timeout vs independently runnable evidence; engineering vs scientific surface.
2. Keep synthetic / proxy / incomplete-provenance as **`NOT_SUPPORTED`**. Refuse scientific `PASS` from this inventory.
3. Reconcile live **#216 merged** vs still-open **#225** supersede text without rewriting those packs or **#237**.
4. Hand classified blockers to QA for the schema/tests Release will validate. Do **not** invent `validate_release_blockers.py` here.
5. Integration (later) orders remediation. Merger: **do not merge. Never close PRs.**

---

## Research classification

- **Phase:** Research (`research_and_tooling`) on 2026-09-07, on Lead commit `fa1a16819fb2462630b6925fc2313efaf8ac52eb`.
- **This section classifies Lead rows.** It does not rewrite Lead evidence and is not compiled evidence.
- **CURRENT_HEAD_MISMATCH** is still **absent**. Live `CURRENT_INTEGRATION_HEAD` remains `be277ecdac301d49dca27ef9612ebe6c560245ad`.
- **Synthetic** remains **`NOT_SUPPORTED`**. Never invent `PASS`.
- **Author isolated counts** 415/75/64/8/3/exit124 remain **unverified**; not compiled evidence.
- **Marketplace bot added:** **Alfred** (governance only).
- `empirical_pass_from_this_pack` remains **false**. `treats_unsupported_claim_as_evidence` is **false** on every row.

| blocker id | class | scientific_claim_status | billing_vs_true_ci | one-line note |
| --- | --- | --- | --- | --- |
| `nts-rb-billing-236-current-head` | infrastructure | none | billing_not_started | Copilot + empty-step jobs; billing ≠ PASS. |
| `nts-rb-ci-workflow-failure-236-rollup` | infrastructure | none | true_ci_unread | Surface FAILURE; BlobNotFound/empty steps; unread until logs exist. |
| `nts-rb-disk-exhaustion-source-prs` | infrastructure | none | historical_only | Prior-source ENOSPC; unavailable on `be277ecd` — do not copy onto current head. |
| `nts-rb-isolated-test-failures-author-claim` | engineering | none | not_applicable | Live author 8 failed (not work-order 6); unverified; not PASS. |
| `nts-rb-isolated-timeouts-author-claim` | engineering | none | not_applicable | Live author 3 timeouts (not work-order 4); exit 124; not skips; not PASS. |
| `nts-rb-optional-deps-torch-cripser` | optional-dependency | none | not_applicable | Missing torch/cripser = skip/unavailable; not scientific PASS. |
| `nts-rb-windows-symlink-privilege` | platform | none | not_applicable | WinError 1314 privilege skip ≠ PASS; Lead Linux did not reproduce. |
| `nts-rb-scientific-review-synthetic-not-supported` | scientific | NOT_SUPPORTED | not_applicable | K>100 only empirical PASS gate; synthetic/proxy cannot PASS. |
| `nts-rb-provenance-incomplete-empirical-gate` | scientific | NOT_SUPPORTED | not_applicable | Incomplete provenance cannot produce empirical PASS; no label inference. |
| `nts-rb-stacked-206-208-unmerged` | engineering | none | not_applicable | #206/#207/#208 still OPEN; leave open; do not merge/close from this pack. |
| `nts-rb-stacked-post-integration-239-240` | engineering (+ documentation) | none | not_applicable | #239/#240 OPEN post-#236; overlap with `be277ecd` unavailable; do not merge. |
| `nts-rb-duplicate-216-225-supersede` | documentation | none | not_applicable | #216 MERGED vs #225 OPEN inventory supersede; no second-authority rewrite. |
| `nts-rb-dashboard-isolation-unverified` | engineering | none | not_applicable | Author-doc PASS unverified; keep unavailable until QA re-runs. |
| `nts-rb-memory-evidence-unavailable` | engineering | none | not_applicable | RSS vs tracemalloc independently unavailable on `be277ecd`. |

**#216 / #225 reconciliation (docs/inventory only):** Live GitHub shows **#216 MERGED** (2026-09-06) and **#225 still OPEN**, titled as superseding #216 inventory. That is a docs/inventory supersede claim versus already-merged schema/compiler authority on #216. This pack does **not** rewrite those evidence packs or the **#237** retirement pack. Leave **#237 OPEN**. Inventory ≠ evidence. No second-authority rewrite.

CI billing-not-started / empty-step FAILURE ≠ pytest PASS. Proxy Bayes ≠ formal Bayes factors. Dashboard author-documented PASS is unverified until QA re-runs.

### Hand-off (QA)

QA owns schema and tests (`scripts/validate_release_blockers.py`, `tests/release/test_blocker_registry.py`). **No validator is invented here.** Do not invent an Integration remediation queue.

**Merger: do not merge. Never close PRs.**
