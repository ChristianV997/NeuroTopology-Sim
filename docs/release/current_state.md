# Current state — evidence-bundle-release Lead inventory + Research classification

**Inventory date:** 2026-09-06  
**Repository:** https://github.com/ChristianV997/NeuroTopology-Sim  
**Live `origin/main` SHA (refreshed):** `62637a4b9c82c0c258bfc49e28dee1af757b1c25`  
**Main tip:** merge of PR #205 (`Merge pull request #205 …`)  
**Inspector:** Lead phase, disposable worktree from `origin/main`  
**Evidence source:** GitHub API / `gh` (live). Caller handoff used only for the dirty-checkout prohibition and the required scientific warnings below.  
**Scope:** Lead inventory only. No schema, no compiler, no production solvers, no CI edits, no MarketOS.  
**Research addendum:** claim classification appended below (2026-09-06, classifier `research_and_tooling`, base Lead commit `be80bdd5`). Still no schema/compiler.

This document is a **snapshot of contribution location and merge status**.
It is not a test report and not a scientific verdict.

---

## Required warnings (read first)

1. **PRs #210, #211, and #212 are NOT merged.** Independently confirmed on
   GitHub on 2026-09-06: `#210` draft/open, `#211` draft/open, `#212`
   open (not draft). `mergedAt` is null on all three. Do not treat them
   as landed on `main`.
2. **`codex/scientific-falsification-contract` has no confirmed PR.**
   Branch exists at `111d4fc008a1cf967243631367104e0561014e4a` (ahead of
   `main` by 1 commit, behind 0). `gh pr list --head
   codex/scientific-falsification-contract` returned an empty list.
3. **Missing Antigravity / Grok implementation reports = unverified.**
   `gh search issues` and PR search found no implementation-report
   artifacts for Antigravity or Grok lanes. Branch/PR existence is not a
   substitute for those reports.
4. **Synthetic data cannot establish scientific `PASS`.** On-main docs
   (`docs/empirical_falsification_phase1.md`) and campaign sidecar PR
   text already treat synthetic fixtures as `NOT_SUPPORTED`. Inventory
   rows that mention author-claimed pytest counts are engineering notes,
   not empirical evidence.
5. **Proxy Bayesian method requires correction / formal likelihood
   validation** before any strong empirical interpretation. On `main`,
   `sim/pitnn/bayesian_falsification.py` states that `bayes_factor` is a
   “descriptive Bayes-factor proxy” (Gaussian residual likelihood ratio /
   RSS). The unmerged falsification-contract branch draft further
   separates formal marginal-likelihood `K` from `bayes_factor_proxy_from_rss`.
   Lead does not validate that branch scientifically.

**Merger: do not merge this inventory PR. Do not mark ready.**

---

## MERGED

These PRs are independently verified merged on GitHub. They are listed
because they define the live `main` baseline or the already-landed
evidence / disorder-modes substrate that later unmerged work attaches to.

| ID | PR | Merge commit | Head | Notes |
| --- | --- | --- | --- | --- |
| `nts-pr-205` | [#205](https://github.com/ChristianV997/NeuroTopology-Sim/pull/205) | `62637a4b9c82c0c258bfc49e28dee1af757b1c25` | `351c8c31f8d2bc28dae908a7c3cb2f6f7cf63f52` | Current `main` tip. OSS trend scout + integration opportunity registry. Branch name `claude/consciousness-transitions-tests-ggx7ph` is a reused lane, not a transitions-science claim. |
| `nts-pr-189` | [#189](https://github.com/ChristianV997/NeuroTopology-Sim/pull/189) | `60503e5e282d62e4b74deffe567dc2c16448fd8f` | `ff3e71272ff5ea720db1082bbaac11a258ecb977` | Evidence Report Generator v1 (`reports/`). Landed 2026-08-11. |
| `nts-pr-188` | [#188](https://github.com/ChristianV997/NeuroTopology-Sim/pull/188) | `2cd7ee0919ee760cc0ab17b3167ef212e69be5e0` | `619d9aa058f573ea5e1f15544d1b3aa2a9ec2fb3` | `evidence/` governed EvidenceBundle layer. Landed 2026-08-11. |
| `nts-pr-184` | [#184](https://github.com/ChristianV997/NeuroTopology-Sim/pull/184) | `1031a9399680f9d388d2652c68672b78e744d08b` | `abba063fddffb4a6cbabefe3f8dd2816863a6d8e` | Disorder-averaged collective-modes campaign. Landed 2026-08-04. The leftover remote branch of the same name is **not** new unmerged work (see BLOCKED). |

PRs #185–#204 are also merged onto the same `main` line (2026-08-11 /
2026-08-12 wave: transitions, phase-space, adapters, report pipeline,
benchmark packs, CI audit). They are **not** re-inventoried row-by-row
here. Presence on `main` was verified by `origin/main` = `#205` merge
and by `gh pr list --state merged`. That list is substrate, not new
evidence.

No merged PR in this snapshot is treated as a scientific `PASS`.

---

## OPEN / DRAFT

All of the following are independently verified **not merged**
(`state=OPEN`, `mergedAt=null`). GitHub reports `mergeable=MERGEABLE`
and `mergeStateStatus=UNSTABLE` on every one (checks red). `MERGEABLE`
here means Git can merge the diff; it is **not** a QA or scientific
sign-off.

### Named by the work order (#208–#212)

| ID | PR | Draft? | Branch | Final commit | Mergeable note |
| --- | --- | --- | --- | --- | --- |
| `nts-pr-208` | [#208](https://github.com/ChristianV997/NeuroTopology-Sim/pull/208) | draft | `cursor/disorder-modes-runrecord-sidecar-v1-04d8` | `5c2bfe045158cf788a658cda6f43121e91e053c7` | MERGEABLE / UNSTABLE. Work order `NTS-SLICE-A-RUNRECORD-SIDECAR-01`. Opt-in `RunRecordV1` sidecar. Author text: sidecar verdict `NOT_SUPPORTED` or `INCONCLUSIVE` only. |
| `nts-pr-209` | [#209](https://github.com/ChristianV997/NeuroTopology-Sim/pull/209) | draft | `grok-bot/retrofit-inventory` | `3a3cf3dfd60416876914bb90f8604ab9e9e8d360` | MERGEABLE / UNSTABLE. Retrofit inventory Phases 1–5 (scanner, registry, validators, reports, CLI). Author text: inventory is not scientific evidence; reports never emit scientific `PASS`. |
| `nts-pr-210` | [#210](https://github.com/ChristianV997/NeuroTopology-Sim/pull/210) | draft | `claude/ecosystem-integration` | `2d46f863bfcc142de34dd052719be5d838ec42a1` | **NOT MERGED.** MERGEABLE / UNSTABLE. Scaffold only. PR body claimed seven dependency branches were absent **at authoring time** (2026-09-06T02:10Z). Those branches **do exist now** (see OPEN rows and BRANCH_ONLY). Treat the PR-body absence claim as stale vs this snapshot. |
| `nts-pr-211` | [#211](https://github.com/ChristianV997/NeuroTopology-Sim/pull/211) | draft | `cursor/streaming-performance-benchmarks` | `54c246943e7c3ba8171066eec24c67a1408b2956` | **NOT MERGED.** MERGEABLE / UNSTABLE. Bounded streaming + PITNN NumPy Heun fallback. Author-claimed pytest/benchmark numbers are **unverified** here. |
| `nts-pr-212` | [#212](https://github.com/ChristianV997/NeuroTopology-Sim/pull/212) | no (open) | `codex/interop-signal-contracts` | `a21dcb2461cdf94da0b41a684a2ac1353153ab35` | **NOT MERGED.** MERGEABLE / UNSTABLE. Signal interop contracts + lazy registry. |

### Other live open PRs on the same `62637a4` baseline

| ID | PR | Draft? | Branch | Final commit | Mergeable note |
| --- | --- | --- | --- | --- | --- |
| `nts-pr-206` | [#206](https://github.com/ChristianV997/NeuroTopology-Sim/pull/206) | draft | `cursor/setup-dev-environment-52dc` | `52118e741a20897e7f28a41cf7491d2af0d73107` | MERGEABLE / UNSTABLE. Cloud Agent env config only. |
| `nts-pr-207` | [#207](https://github.com/ChristianV997/NeuroTopology-Sim/pull/207) | draft | `cursor/pitnn-perf-opt-52dc` | `a0038fd0fe368fbb2f22b5b93104736bccbe9c6e` | MERGEABLE / UNSTABLE. Lindblad RK4 buffer reuse. Overlaps numerically with `#211` (different file: `tryptophan_lindblad.py` vs `kernels_fast.py`). |
| `nts-pr-213` | [#213](https://github.com/ChristianV997/NeuroTopology-Sim/pull/213) | no (open) | `antigravity/test-isolation-dependency-profiles` | `f23c7ef74b133d65c355d7c4e7778d63a08cc8eb` | MERGEABLE / UNSTABLE. No Antigravity implementation report located. Edits CI/requirements — out of this Lead write set; recorded only. |
| `nts-pr-214` | [#214](https://github.com/ChristianV997/NeuroTopology-Sim/pull/214) | no (open) | `antigravity/mne-scipy-streaming-eeg` | `8aed328fa23af07737882566d6b60aaca74ac4fb` | MERGEABLE / UNSTABLE. No Antigravity implementation report located. Touches EEG adapters / `validation/analytic_phase.py`. |

Every listed open PR’s first unique commit parent is `62637a4b` (live
`main`). None is behind `main`.

---

## BRANCH_ONLY

| ID | Branch | Tip | vs `main` | PR |
| --- | --- | --- | --- | --- |
| `nts-branch-scientific-falsification-contract` | `codex/scientific-falsification-contract` | `111d4fc008a1cf967243631367104e0561014e4a` | ahead 1 / behind 0 | **none** (`gh pr list --head` empty) |
| `nts-branch-grok-tool-admission-research` | `grok/tool-admission-research` | `1dac04d62912bcb32245cfad20315d3363b41220` | ahead 5 / behind 0 | **none** |

`scientific-falsification-contract` changed files (GitHub compare, not
scientifically reviewed here):

- `analysis/connectivity_topology.py`
- `docs/scientific_falsification_contract.md` (added)
- `sim/pitnn/bayesian_falsification.py`
- `tests/science_contracts/test_bayesian_contract.py` (added)
- `tests/science_contracts/test_topology_contract.py` (added)
- `topo_monitor/graph_persistence.py`
- `topo_monitor/spatial_phase.py`

`grok/tool-admission-research` is an offline tool-admission registry /
review-notes branch. No Grok implementation report was found. Do not
treat the catalog as an admission decision or as evidence.

---

## BLOCKED

| ID | What | Why blocked for this Lead run |
| --- | --- | --- |
| `nts-blocked-disorder-modes-leftover-abba063` | Remote `codex/disorder-averaged-collective-modes` still points at `abba063fddffb4a6cbabefe3f8dd2816863a6d8e` | Caller forbade touching that dirty primary checkout / leftover branch. GitHub shows the commit **already merged** as PR #184. Compare vs current `main` is `diverged` (ahead 1 / behind 51) because the remote branch was not deleted and `main` moved on. Lead did **not** inspect any dirty working tree. New sidecar work is PR #208, not this leftover tip. |
| GitHub Required Checks on the September open-PR wave | `core-tests` / `ontology-claim-language` / `Cross-system smoke` red | Independently sampled job logs for `#206`, `#208`, `#210`, `#211`, `#212` show `OSError: [Errno 28] No space left on device` during `pip install -r requirements.txt` **before pytest**. That is an environment/disk failure, not a compiled scientific result. Jobs for `#209`, `#213`, `#214` failed in ~3s with empty step lists — root cause **unread**. Awareness-tests passed on several PRs (`#206`–`#208`, `#210`–`#212`) and failed immediately on `#209`, `#213`, `#214`. |

Lead does not rerun CI, does not slim `requirements.txt`, and does not
declare those red checks as caused-by-current-change.

---

## UNVERIFIED

| ID | Item | Why unverified |
| --- | --- | --- |
| `nts-unverified-antigravity-implementation-reports` | Antigravity lane reports for `#213` / `#214` | No issue, gist, or PR-attached implementation report found via `gh` search. |
| `nts-unverified-grok-implementation-reports` | Grok / grok-bot lane reports for `grok/tool-admission-research` and `#209` | Same: no implementation report found. PR `#209` text is not a substitute report. |
| `nts-unverified-proxy-bayesian-likelihood` | Formal Bayes factor / likelihood | On-main method is a proxy. Unmerged contract branch is unpublished (no PR). No formal likelihood validation was independently performed in this Lead run. |
| Author-claimed test counts | pytest / benchmark numbers in PR bodies (`#206`–`#214`, `#209` in particular) | Not re-run here. Do not copy them into a compiled evidence bundle as verified results. |
| Scientific `PASS` | Any empirical or topology-as-proof claim | None independently verified. None should be inferred from inventory. |

---

## CI notes (readable failures only)

Independently read `core-tests` failed logs:

- PR #206 job `101243532368`: `Errno 28` during root `pip install`.
- PR #208 job `101252966226`: `Errno 28` during root `pip install`.
- PR #210 job `101412547695`: `Errno 28` during root `pip install`.
- PR #211 job `101412998793`: `Errno 28` during root `pip install`.
- PR #212 job `101413702579`: runner warning “61 MB” then `Errno 28`.

Not a pytest-node failure in those sampled logs. This does **not** prove
the PR diffs would pass tests.

`#209` / `#213` / `#214`: checks `fail` in 2–6 seconds; Actions job
payloads have `steps: []` and no log body. Classification: **unread**.

---

## Scientific / governance blockers (warnings only)

These are **warnings for Research**, not executed falsification results.

- Do not compile scientific `PASS` from synthetic fixtures, author-claimed
  pytest, or performance stand-in workloads (`#211` states its benchmark
  is not a scientific computation).
- Do not treat `#209` retrofit inventory output as evidence
  (`scientific_claim_status` is author-described as always `not_evidence`).
- Do not treat `#208` sidecar `RunRecord.json` as campaign replacement or
  as `PASS` (author: `PASS` reserved for Bayes factor `K > 100`; this
  lattice campaign does not compute `K`).
- Do not interpret on-main `bayes_factor` as a formal marginal-likelihood
  Bayes factor.
- Do not assume `#210` consumed the seven dependency branches — its own
  body says it did not; those branches appeared later the same day.
- `#213` / `#214` lack implementation reports → keep unverified.
- `scientific-falsification-contract` is branch-only; do not cite it as a
  merged contract.

---

## Next action (Research)

Classify each matrix row:

1. **Claim surface** — engineering-runtime vs scientific-interpretation.
2. **Data mode** — synthetic / local-unknown / none (docs-only).
3. **Merge reality** — especially `#210`, `#211`, `#212` remain unmerged.
4. **Missing reports** — Antigravity and Grok implementation reports.
5. **Bayesian method** — mark proxy-vs-formal; require correction /
   formal likelihood validation before any empirical reading.
6. Hand a classified inventory to QA for `evidence_schema.yaml`.
   Do not invent the schema in this Lead pack.

Exact merger instruction: **do not merge.**

---

## Research claim classification

Research phase landed 2026-09-06 on Lead inventory
`be80bdd5db85b417dd5f15a5445d6c6a6bfd3368`. Every contribution row now
has a `research_classification` block. Inventory remains **not
evidence**. `empirical_pass_allowed` is `false` on every row.
`empirical_pass_from_this_pack` is `false`. This pack does **not** add
`configs/release/evidence_schema.yaml`,
`scripts/compile_repository_evidence.py`, or
`tests/release/test_evidence_compiler.py`.

### Required warnings (Research; verbatim)

1. PRs #210, #211, #212 are NOT merged unless independently verified as merged.
2. scientific-falsification branch has no confirmed PR unless one is found.
3. Missing Antigravity/Grok implementation reports are unverified.
4. Synthetic data cannot establish a scientific PASS.
5. Current proxy Bayesian method requires correction / formal likelihood validation before strong empirical interpretation.

### Classification of all inventory rows

| ID | value_class | claim_class | bayesian_warning | Note |
| --- | --- | --- | --- | --- |
| `nts-pr-205` | tooling (+governance) | none | false | Engineering opportunity registry only; not scientific evidence. |
| `nts-pr-189` | engineering (+governance) | none | false | Report formatter is not an empirical result. |
| `nts-pr-188` | governance (+engineering) | none | false | Substrate for a later compiler; not a theory result. |
| `nts-pr-184` | engineering (+scientific) | synthetic | false | Synthetic lattice campaign is not empirical biology; no K>100 PASS from this PR. |
| `nts-pr-206` | tooling | none | false | Cloud Agent env config only; not scientific evidence. |
| `nts-pr-207` | engineering | synthetic | false | Bit-identity/speedup unverified; not a scientific PASS. |
| `nts-pr-208` | engineering (+governance) | synthetic | **true** | NOT MERGED; synthetic lattice sidecar is not empirical; no K computed. |
| `nts-pr-209` | tooling (+governance) | none | false | Inventory is not evidence; never PASS; Grok impl report missing. |
| `nts-pr-210` | engineering | unsupported | false | **NOT MERGED** (verified open draft). Scaffold does not prove integration; author absence-claim stale. |
| `nts-pr-211` | engineering | synthetic | false | **NOT MERGED**. Performance stand-in, not scientific computation; synthetic ≠ PASS. |
| `nts-pr-212` | governance (+engineering) | none | false | **NOT MERGED**. Contracts are not empirical results. |
| `nts-pr-213` | engineering (+tooling) | unsupported | false | Antigravity implementation report missing → unverified. |
| `nts-pr-214` | engineering (+tooling) | unsupported | false | Antigravity report missing; streaming/preprocessing ≠ empirical PASS. |
| `nts-branch-scientific-falsification-contract` | scientific (+governance) | proxy | **true** | No confirmed PR. Do not cite as landed. Proxy vs formal K split. |
| `nts-branch-grok-tool-admission-research` | tooling (+governance) | none | false | Catalog ≠ admission decision ≠ scientific evidence; Grok report missing. |
| `nts-blocked-disorder-modes-leftover-abba063` | engineering | synthetic | false | Leftover tip of already-merged #184; not new work. |
| `nts-unverified-antigravity-implementation-reports` | governance | unsupported | false | Missing Antigravity implementation reports remain unverified. |
| `nts-unverified-grok-implementation-reports` | governance | unsupported | false | Missing Grok implementation reports remain unverified. |
| `nts-unverified-proxy-bayesian-likelihood` | scientific | proxy | **true** | On-main `bayes_factor` is a descriptive proxy; needs formal likelihood validation. |

### Explicit limits (do not invent merge status)

- **#210 / #211 / #212 are NOT MERGED.** Lead merge_status remains
  draft / draft / open. Research did not change those fields.
- **`scientific-falsification` branch has no confirmed PR.** Branch-only
  row `nts-branch-scientific-falsification-contract`. Do not cite as
  landed.
- **Antigravity / Grok implementation reports are unverified.**
- **Synthetic data cannot establish a scientific PASS.**
- **Proxy Bayes needs formal likelihood validation** before strong
  empirical interpretation. `bayesian_warning: true` on `nts-pr-208`,
  `nts-branch-scientific-falsification-contract`, and
  `nts-unverified-proxy-bayesian-likelihood`.

### Hand off (QA)

QA may now own `configs/release/evidence_schema.yaml` and
`tests/release/test_evidence_compiler.py`. Do **not** invent the schema
in this Research pack. Schema must refuse scientific `PASS` from
synthetic data and refuse unverified author-claimed test counts as
compiled evidence.

**Merger: do not merge.**
