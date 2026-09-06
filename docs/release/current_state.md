# Current state — release-evidence-compilation Lead inventory

**Inventory date:** 2026-09-06T06:06:55Z  
**Repository:** https://github.com/ChristianV997/NeuroTopology-Sim  
**Live `origin/main` SHA (refreshed):** `62637a4b9c82c0c258bfc49e28dee1af757b1c25`  
**Main tip:** merge of PR #205 (`Merge pull request #205 …`)  
**Inspector:** Lead phase only, disposable worktree from `origin/main`  
**Evidence source:** GitHub API / `gh` (live), including check-run annotations  
**Scope:** Lead inventory refresh. No schema, no compiler, no validators,
no production solvers, no CI edits, no adapters, no MarketOS.  
**This PR:** [#225](https://github.com/ChristianV997/NeuroTopology-Sim/pull/225)
(`cursor/release-evidence-compilation-9077`)  
**Supersede:** draft PR #216 inventory docs only
(`grok-bot/evidence-bundle-release` FINAL `07841284`). Do **not** open a
second evidence authority. #216 is `SUPERSEDED` for inventory docs by
#225. Schema / compiler / `tests/release/**` stay on #216.

This document is a **snapshot of contribution location and merge status**.
It is not a test report and not a scientific verdict.

**Inventory ≠ evidence.**

---

## Required explicit statements (read first)

1. **PRs are not merged unless GitHub says merged.** Independently
   confirmed on 2026-09-06: every PR in the #206–#222 wave has
   `state=OPEN` and `mergedAt=null`. That includes #210, #211, #212,
   #215, #216, #219, and #222. `mergeable=MERGEABLE` only means Git can
   apply the diff. It is not a QA or scientific sign-off.
2. **CI billing failure ≠ passing tests.** Check-run annotations on
   #209 and #213–#222 read: *“The job was not started because recent
   account payments have failed or your spending limit needs to be
   increased.”* Those jobs have empty step lists (~3–6 s). That is
   `BILLING_BLOCKED`. It does **not** mean tests passed, and it does
   **not** mean the diff is green.
3. **Disk-full CI failure ≠ passing tests.** Independently read
   `core-tests` logs for #206, #208, #210, #211, and #212 show jobs that
   **did start** and then failed during `pip install` (`OSError: [Errno
   28] No space left on device`, or annotation “Process completed with
   exit code 1” after the install step). That is `CI_BLOCKED`
   (environment / disk). Pytest was skipped. Not a compiled scientific
   result.
4. **Proxy Bayes ≠ formal Bayes factors.** On `main`,
   `sim/pitnn/bayesian_falsification.py` states that `bayes_factor` is a
   “descriptive Bayes-factor proxy” (Gaussian residual likelihood ratio
   / RSS). Do not treat on-main `bayes_factor` or author-claimed `K`
   language as a formal marginal-likelihood Bayes factor.
5. **Synthetic ≠ biological evidence.** Synthetic fixtures, lattice
   campaigns, and performance stand-in workloads cannot establish
   scientific `PASS` or biological evidence.
6. **Process-memory numbers must say RSS vs tracemalloc when known;
   else unavailable.** Lead did not re-run #211 or #215 benchmarks.
   Independently verified process-memory numbers: **unavailable**.
   Author-claimed numbers in the #215 PR body (unverified) must stay
   labeled: `tracemalloc` peak vs RSS delta vs process-lifetime peak
   RSS. Do not collapse them into one “memory” figure.
7. **Missing adapters ≠ supported.** #212 is contracts + lazy registry
   only (not merged). #220 adds adapter files but is **not merged** and
   is stacked on #212. Absence or presence of adapter files is not a
   support claim.
8. **This branch supersedes #216 inventory docs; do not open a second
   evidence authority.** QA schema, Release compiler, and
   `tests/release/**` stay on #216. This Lead pack does not copy or
   rewrite them.

**Merger: do not merge this inventory PR. Do not mark ready.**

---

## STACKED_PRS

| Child | Parent | Relationship | Verified how |
| --- | --- | --- | --- |
| **#215 → #211** | #215 `cursor/rss-memory-telemetry` @ `0dadb61b` | **STACKED** | GitHub: #215 `baseRefName=cursor/streaming-performance-benchmarks`, `baseRefOid=54c246943e7c3ba8171066eec24c67a1408b2956` (exact #211 head). PR body: “Stacked on #211.” |
| #220 → #212 | #220 `antigravity/native-signal-adapters` @ `5bd26dc5` | STACKED (related) | GitHub: #220 `baseRefName=codex/interop-signal-contracts`, `baseRefOid=a21dcb2461cdf94da0b41a684a2ac1353153ab35` (exact #212 head). |

No other PR in #206–#222 targets another open PR branch.

---

## Branch-only: `scientific-falsification-contract`

| Field | Value |
| --- | --- |
| Branch | `codex/scientific-falsification-contract` |
| Tip | `111d4fc008a1cf967243631367104e0561014e4a` |
| vs `main` | ahead 1 / behind 0 |
| PR? | **No.** `gh pr list --head ChristianV997:codex/scientific-falsification-contract` returned `[]`. |
| Status | `BRANCH_ONLY` + `SCIENTIFIC_REVIEW_REQUIRED` |

Related but **not** a PR for that branch: open #219
(`codex/bayes-falsification-hardening` @ `a7dd8e24`) also edits
`sim/pitnn/bayesian_falsification.py` with a different file set. Not
marked `DUPLICATE`. Both need scientific review. Neither is merged.

---

## MERGED (verified on GitHub)

These PRs are independently verified merged. They define the live `main`
baseline. They are **not** a scientific `PASS`.

| ID | PR | Merge commit / head | Status | Notes |
| --- | --- | --- | --- | --- |
| `nts-pr-205` | [#205](https://github.com/ChristianV997/NeuroTopology-Sim/pull/205) | merge `62637a4b` / head `351c8c31` | `VERIFIED_MERGED` | Current `main` tip. OSS trend scout. Reused Claude lane name. |
| `nts-pr-189` | [#189](https://github.com/ChristianV997/NeuroTopology-Sim/pull/189) | merge `60503e5e` / head `ff3e7127` | `VERIFIED_MERGED` | Evidence Report Generator v1. Landed 2026-08-11. |
| `nts-pr-188` | [#188](https://github.com/ChristianV997/NeuroTopology-Sim/pull/188) | merge `2cd7ee09` / head `619d9aa0` | `VERIFIED_MERGED` | `evidence/` governed EvidenceBundle layer. |
| `nts-pr-184` | [#184](https://github.com/ChristianV997/NeuroTopology-Sim/pull/184) | merge `1031a939` / head `abba063f` | `VERIFIED_MERGED` | Disorder-averaged collective-modes campaign. Leftover remote of the same name is **not** new work. |

PRs #185–#204 are also merged onto the same `main` line (2026-08-11 /
2026-08-12 wave). They are **not** re-inventoried row-by-row. Presence
on `main` was verified by `origin/main` = #205 merge and by
`gh pr list --state merged`. Substrate, not new evidence.

---

## OPEN / DRAFT (all `mergedAt=null`)

GitHub reports `mergeable=MERGEABLE` and `mergeStateStatus=UNSTABLE` on
every row below. Checks are red. None is behind live `main`
(`baseRefOid=62637a4b` except stacked PRs, whose bases are other open
heads).

### Named work-order window (#209–#219, #222) plus related #220 / #221

| ID | PR | Draft? | Head | Base SHA | Status | Check rollup (latest name→conclusion) |
| --- | --- | --- | --- | --- | --- | --- |
| `nts-pr-209` | [#209](https://github.com/ChristianV997/NeuroTopology-Sim/pull/209) Phase 1–5 retrofit inventory | draft | `grok-bot/retrofit-inventory` @ `3a3cf3df` | `62637a4b` (`main`) | `DRAFT_REVIEW`, `BILLING_BLOCKED` | ontology/core/smoke/awareness: FAILURE (jobs not started; billing annotation) |
| `nts-pr-210` | [#210](https://github.com/ChristianV997/NeuroTopology-Sim/pull/210) Ecosystem integration scaffold | draft | `claude/ecosystem-integration` @ `2d46f863` | `62637a4b` | `DRAFT_REVIEW`, `CI_BLOCKED` | awareness SUCCESS; core/ontology/smoke FAILURE (job started; disk/install) |
| `nts-pr-211` | [#211](https://github.com/ChristianV997/NeuroTopology-Sim/pull/211) Bounded streaming + PITNN NumPy kernel | draft | `cursor/streaming-performance-benchmarks` @ `54c24694` | `62637a4b` | `DRAFT_REVIEW`, `CI_BLOCKED` | awareness + Awareness Studio 3.11/3.12 SUCCESS; core/ontology/smoke FAILURE (Errno 28 during pip) |
| `nts-pr-212` | [#212](https://github.com/ChristianV997/NeuroTopology-Sim/pull/212) Native signal interop **contracts** | no | `codex/interop-signal-contracts` @ `a21dcb24` | `62637a4b` | `OPEN_REVIEW`, `CI_BLOCKED` | awareness SUCCESS; core/ontology/smoke FAILURE (install exit 1). Contracts ≠ adapters supported. |
| `nts-pr-213` | [#213](https://github.com/ChristianV997/NeuroTopology-Sim/pull/213) Test isolation / dependency profiles | no | `antigravity/test-isolation-dependency-profiles` @ `f23c7ef7` | `62637a4b` | `OPEN_REVIEW`, `BILLING_BLOCKED`, `UNVERIFIED` | All sampled required/docker/E2E FAILURE; billing annotation. No Antigravity implementation report. |
| `nts-pr-214` | [#214](https://github.com/ChristianV997/NeuroTopology-Sim/pull/214) EEG streaming / preprocessing | no | `antigravity/mne-scipy-streaming-eeg` @ `8aed328f` | `62637a4b` | `OPEN_REVIEW`, `BILLING_BLOCKED`, `UNVERIFIED` | All sampled FAILURE; billing annotation. No Antigravity implementation report. |
| `nts-pr-215` | [#215](https://github.com/ChristianV997/NeuroTopology-Sim/pull/215) Process-memory **RSS** telemetry | draft | `cursor/rss-memory-telemetry` @ `0dadb61b` | **#211** `54c24694` | `DRAFT_REVIEW`, `BILLING_BLOCKED` | **STACKED on #211.** All sampled FAILURE; billing annotation. Memory numbers: see below. |
| `nts-pr-216` | [#216](https://github.com/ChristianV997/NeuroTopology-Sim/pull/216) Evidence-bundle release (Lead/Research/QA/Release) | draft | `grok-bot/evidence-bundle-release` @ `07841284` | `62637a4b` | `SUPERSEDED`, `DRAFT_REVIEW`, `BILLING_BLOCKED` | Inventory docs superseded by **#225**. Schema/compiler stay on #216. Do not fork. |
| `nts-pr-217` | [#217](https://github.com/ChristianV997/NeuroTopology-Sim/pull/217) Optional backend capability registry | no | `grok/tool-registry-admission` @ `ffc8f6df` | `62637a4b` | `OPEN_REVIEW`, `BILLING_BLOCKED`, `UNVERIFIED` | All sampled FAILURE; billing annotation. No Grok implementation report. |
| `nts-pr-218` | [#218](https://github.com/ChristianV997/NeuroTopology-Sim/pull/218) Read-only integration reconciliation | draft | `claude/integration-reconciliation` @ `746da4df` | `62637a4b` | `DRAFT_REVIEW`, `BILLING_BLOCKED` | All sampled FAILURE; billing annotation. Tooling only. |
| `nts-pr-219` | [#219](https://github.com/ChristianV997/NeuroTopology-Sim/pull/219) Harden Bayesian falsification evidence contract | no | `codex/bayes-falsification-hardening` @ `a7dd8e24` | `62637a4b` | `OPEN_REVIEW`, `SCIENTIFIC_REVIEW_REQUIRED`, `BILLING_BLOCKED` | All sampled FAILURE; billing annotation. Proxy vs formal K language is **not** a scientific PASS. |
| `nts-pr-220` | [#220](https://github.com/ChristianV997/NeuroTopology-Sim/pull/220) Native signal interop **adapters** | no | `antigravity/native-signal-adapters` @ `5bd26dc5` | **#212** `a21dcb24` | `OPEN_REVIEW`, `BILLING_BLOCKED`, `UNVERIFIED` | **STACKED on #212.** Missing/unmerged adapters ≠ supported. Billing annotation. |
| `nts-pr-221` | [#221](https://github.com/ChristianV997/NeuroTopology-Sim/pull/221) Legacy timeout / path validation repair | no | `antigravity/legacy-timeout-repair` @ `a9aba515` | `62637a4b` | `OPEN_REVIEW`, `BILLING_BLOCKED`, `UNVERIFIED` | Billing annotation. No Antigravity implementation report. |
| `nts-pr-222` | [#222](https://github.com/ChristianV997/NeuroTopology-Sim/pull/222) Bounded isolated CI + dependency bootstrap | no | `codex/ci-root-cause-and-green` @ `14bce7f7` | `62637a4b` | `OPEN_REVIEW`, `BILLING_BLOCKED` | Author text classifies #210/#211/#212 failures as pre-test disk/CUDA install. This PR’s own checks did **not start** (billing). Author-claimed 117 tests: unverified. |

### Other live open PRs on the same `62637a4` baseline

| ID | PR | Draft? | Head | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| `nts-pr-206` | [#206](https://github.com/ChristianV997/NeuroTopology-Sim/pull/206) | draft | `cursor/setup-dev-environment-52dc` @ `52118e74` | `DRAFT_REVIEW`, `CI_BLOCKED` | Env config only. awareness SUCCESS; core failed after start (install). |
| `nts-pr-207` | [#207](https://github.com/ChristianV997/NeuroTopology-Sim/pull/207) | draft | `cursor/pitnn-perf-opt-52dc` @ `a0038fd0` | `DRAFT_REVIEW`, `CI_BLOCKED` | Lindblad RK4 buffer reuse. Author speedup table unverified. Overlaps #211 only at different PITNN files. |
| `nts-pr-208` | [#208](https://github.com/ChristianV997/NeuroTopology-Sim/pull/208) | draft | `cursor/disorder-modes-runrecord-sidecar-v1-04d8` @ `5c2bfe04` | `DRAFT_REVIEW`, `CI_BLOCKED`, `SCIENTIFIC_REVIEW_REQUIRED` | Opt-in `RunRecordV1` sidecar. Author: sidecar verdict `NOT_SUPPORTED` / `INCONCLUSIVE` only; no K computed. Synthetic ≠ biology. |

---

## BRANCH_ONLY

| ID | Branch | Tip | vs `main` | PR | Status |
| --- | --- | --- | --- | --- | --- |
| `nts-branch-scientific-falsification-contract` | `codex/scientific-falsification-contract` | `111d4fc0` | ahead 1 / behind 0 | **none** | `BRANCH_ONLY`, `SCIENTIFIC_REVIEW_REQUIRED` |
| `nts-branch-grok-tool-admission-research` | `grok/tool-admission-research` | `1dac04d6` | ahead 5 / behind 0 | **none** | `BRANCH_ONLY`, `UNVERIFIED` |

`scientific-falsification-contract` changed files (GitHub compare, not
scientifically reviewed here):

- `analysis/connectivity_topology.py`
- `docs/scientific_falsification_contract.md` (added)
- `sim/pitnn/bayesian_falsification.py`
- `tests/science_contracts/test_bayesian_contract.py` (added)
- `tests/science_contracts/test_topology_contract.py` (added)
- `topo_monitor/graph_persistence.py`
- `topo_monitor/spatial_phase.py`

Related open PR #219 uses a different path set
(`docs/scientific_falsification/README.md`,
`sim/pitnn/bayesian_falsification.py`,
`tests/test_bayesian_falsification_hardening.py`). Parallel work, not
`DUPLICATE`.

---

## SUPERSEDED / DUPLICATE

| ID | What | Status |
| --- | --- | --- |
| `nts-pr-216` | Draft evidence-bundle pack FINAL `07841284` | **`SUPERSEDED`** for **inventory docs** by [#225](https://github.com/ChristianV997/NeuroTopology-Sim/pull/225). Schema / compiler / `tests/release/**` are **not** superseded and must not be re-implemented. |
| — | Exact duplicate PRs in this snapshot | **None verified.** Related pairs that are **not** `DUPLICATE`: #219 ↔ branch-only falsification contract; #217 ↔ `grok/tool-admission-research`; #213 ↔ #222 (both touch isolation/CI); #212 ↔ #220 (contracts vs stacked adapters). |

---

## BLOCKED

| ID | What | Why |
| --- | --- | --- |
| `nts-blocked-disorder-modes-leftover-abba063` | Remote `codex/disorder-averaged-collective-modes` still at `abba063f` | Caller forbade touching that leftover / dirty primary checkout. GitHub: commit already merged as PR #184. Compare vs current `main` is diverged (ahead 1 / behind 51) because the remote was not deleted. New sidecar work is #208. |
| Billing wall on #209, #213–#222 | Required Checks / smoke / (where present) Awareness Studio + E2E | Jobs **not started**. Annotation is account payment / spending-limit. `BILLING_BLOCKED` ≠ test pass or test fail. |
| Disk / install wall on #206, #208, #210, #211, #212 | `core-tests` (and typically ontology + smoke) | Jobs **started**; install died (`Errno 28` on sampled #210/#211 logs; exit 1 annotation on #206/#208/#212). Pytest skipped. `CI_BLOCKED` ≠ test pass. |
| #222 vs that disk wall | Author claims a CPU-only bootstrap fix | This PR’s own GitHub checks did not start (billing). The fix is **unverified** on GitHub Actions. |

---

## Process-memory (RSS vs tracemalloc)

Lead did **not** re-run benchmarks. Independently verified numbers:
**unavailable**.

Author-claimed figures in the **#215** PR body (unverified; do not
compile as evidence):

| Workload (author text) | tracemalloc peak | RSS delta | peak RSS (lifetime) |
| --- | --- | --- | --- |
| streaming_full | 51.2 MB (`tracemalloc`) | ~0 MB (`RSS`) | 212.3 MB (`RSS`, process-lifetime) |
| streaming_bounded (2048) | 1.12 MB (`tracemalloc`) | ~0 MB (`RSS`) | 212.3 MB (`RSS`, process-lifetime) |
| streaming_bounded (16384) | 8.46 MB (`tracemalloc`) | ~0 MB (`RSS`) | 212.3 MB (`RSS`, process-lifetime) |
| kernel numpy / numba | 21.5 KB (`tracemalloc`) | — | 212.3 MB (`RSS`, process-lifetime) |

Author text also says: RSS deltas ~0 because allocator arenas retain
freed pages; peak RSS is a process-lifetime high-water mark; tests do
not gate on absolute wall-clock or noisy RSS deltas; providers return
`None` when unavailable. **#211** reported `tracemalloc` only (Python
allocations). Do not treat #211 tracemalloc peaks as process RSS.

---

## UNVERIFIED

| ID | Item | Why |
| --- | --- | --- |
| `nts-unverified-antigravity-implementation-reports` | Antigravity reports for #213, #214, #220, #221 | `gh` issue/PR search found no implementation-report artifacts. Branch/PR existence is not a substitute. |
| `nts-unverified-grok-implementation-reports` | Grok / grok-bot reports for #209, #217, and `grok/tool-admission-research` | Same: no report found. |
| `nts-unverified-proxy-bayesian-likelihood` | Formal Bayes factor / likelihood | On-main method is a proxy. Branch-only contract and open #219 are unpublished as merged validation. |
| Author-claimed test / timing / memory tables | PR bodies (#206–#222, especially #209, #211, #215, #222) | Not re-run here. Do not copy into a compiled evidence bundle as verified results. |
| Scientific `PASS` | Any empirical or topology-as-proof claim | None independently verified. Inventory ≠ evidence. |
| Adapter support | Native MNE/EDF/BrainVision/NumPy adapters | #220 not merged; #212 is contracts only. Missing adapters ≠ supported. |

---

## Scientific / governance blockers (warnings only)

These are **warnings for Research**, not executed falsification results.

- Do not compile scientific `PASS` from synthetic fixtures, author-claimed
  pytest, or performance stand-in workloads (#211 states its benchmark
  is not a scientific computation).
- Do not treat #209 retrofit inventory output as evidence
  (author: `scientific_claim_status` always `not_evidence`).
- Do not treat #208 sidecar `RunRecord.json` as campaign replacement or
  as `PASS` (author: `PASS` reserved for Bayes factor `K > 100`; this
  lattice campaign does not compute `K`).
- Do not interpret on-main `bayes_factor` as a formal marginal-likelihood
  Bayes factor. Proxy Bayes ≠ formal Bayes factors.
- Do not cite `scientific-falsification-contract` as a merged contract
  (no PR).
- Do not treat #219 author validation commands as a scientific PASS.
- Do not assume #210 consumed later dependency branches.
- #213 / #214 / #220 / #221 lack implementation reports → keep
  `UNVERIFIED`.
- #215 author RSS / tracemalloc table is not independently verified.
- #220 / missing adapters ≠ supported.
- Do not invent a second evidence schema, compiler, validator, or queue
  on this branch.

---

## Next action (Research)

Classify each **new or refreshed** matrix row (especially #215–#222):

1. **Claim surface** — engineering-runtime vs scientific-interpretation.
2. **Data mode** — synthetic / local-unknown / none (docs-only).
3. **Merge reality** — no PR is merged unless GitHub `mergedAt` is set.
4. **Stacked base** — keep #215→#211 (and related #220→#212) explicit.
5. **Missing reports** — Antigravity and Grok implementation reports.
6. **Bayesian method** — mark proxy-vs-formal; require correction /
   formal likelihood validation before any empirical reading.
7. **Memory figures** — keep RSS vs tracemalloc labels; mark author
   tables unverified; independently verified numbers remain unavailable.
8. **Adapters** — contracts (#212) vs unmerged adapters (#220); missing
   ≠ supported.
9. Hand a classified inventory to QA on the **existing #216 schema**.
   Do **not** invent a second `evidence_schema.yaml`.

Carried-forward `research_classification` blocks on older rows are from
#216 @ `07841284`. Lead did not re-run Research and did not add
scientific `PASS`.

Exact merger instruction: **do not merge.**
