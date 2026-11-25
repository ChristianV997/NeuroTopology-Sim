# Research-cycle wave 1 integration audit

**Agent:** Codex D — Merger Agent
**Audit date:** 2026-09-11
**Authoritative base:** `origin/main` at `618ca081039759510d27a7a772cd47c95985600f`
**Integration branch:** `codex/research-cycle-wave1-integration-20260910`

This is a live re-audit record. The earlier release documents under
`docs/release/` are historical snapshots and are not authoritative where they
disagree with live GitHub metadata or git ancestry.

## Live PR matrix

All rows below were compared against the live `origin/main` above. Every open
head was non-ancestor at audit time; effective file counts are three-dot diffs
against that main head.

| PR | State | Draft | Head | Effective files | Decision |
|---:|---|:---:|---|---:|---|
| 296 | OPEN | yes | `af0d6a050b1b` | 10 | Retain open; provenance fabrication blocker |
| 297 | OPEN | yes | `90c70842cfcf` | 9 | Retain open; future-sample interpolation blocker |
| 298 | OPEN | yes | `129bf24da3f6` | 9 | Audit-only; explicit “do not merge” |
| 300 | OPEN | yes | `e6dd03b6daac` | 7 | Integrated; topology snapshot reuse is additive |
| 301 | OPEN | no | `d8702e279356` | 19 | Integrated; four conflicts resolved in favor of the richer evidence-aware implementation |
| 302 | OPEN | yes | `4ea1f8c88505` | 11 | Integrated; deterministic plan-quality rubric |
| 303 | OPEN | yes | `d21aa03809c3` | 10 | Integrated after removing a hidden full-copy benchmark reference path |
| 304 | OPEN | yes | `133f4860a834` | 7 | Integrated; read-only lineage extractor |
| 305 | OPEN | no | `d08aff5046cb` | 5 | Integrated; immutable local ledger |
| 306 | OPEN | yes | `26ec5223ba1e` | 5 | Integrated; fail-closed claim gate |
| 307 | OPEN | yes | `52137e13b72a` | 11 | Excluded; runner lacks a real offline subprocess boundary and permits output-path escape |
| 308 | OPEN | yes | `271f8d275b04` | 10 | Integrated with cache-integrity and containment hardening |
| 309 | OPEN | yes | `5f854b0ce180` | 35 | Integrated as fixture-only black-box contract tests; pending-module expectations updated |

The only direct raw-file overlap among the open heads was #300/#307 on
`tools/simulation_runtime/__init__.py`; #301 also overlapped existing
integration-reconciliation ownership and required explicit conflict resolution.

## Scientific and operational decisions

- #296 remains blocked because reverse adaptation uses `unknown_source` and
  `derived_from_ledger` in place of absent provenance/checksums.
- #297 remains blocked because `resample_causal_linear` uses the future
  `idx_ceil` sample and its lag-correlation output is synthetic rather than
  measured.
- #298 remains audit-only while its author’s “Draft — do not merge” instruction
  remains present.
- #303 now computes its bounded cache candidate checksum from the bounded heap;
  it no longer materializes a second full reference list.
- #308 is network-disabled by default, manifest-first, budget-bounded, and now
  rejects a cached object whose expected checksum does not match before
  reporting a cache hit. Manifest cached paths are also containment-checked.
- #307 was not promoted: an arbitrary child command can still perform network
  I/O, and declared absolute outputs can escape the campaign output root.
  Its useful checkpoint/process code remains available for a future hardened
  extraction rather than being silently promoted.
- Synthetic, proxy, partial, failed, unavailable, and incomplete artifacts are
  never promoted to empirical evidence or scientific PASS.

## Closed and superseded audit

#299 is the only PR merged after the previous merger run; its merge commit is
`618ca081039759510d27a7a772cd47c95985600f`, reachable from live main. It is
the safe extraction of #275. #275 is closed as superseded. The useful higher-
order work from #291/#293 is already represented by merged #292/#295, and the
validated higher-order functionality from #278/#279 is present on main.

#265, #256, #237, #271, #249, #222, and #227 remain excluded/retired per
their unsafe, audit-only, or superseded lineage. They were not resurrected.

## Validation record

The integrated focused/adjacent command completed with **580 passed** in
12m07s. It covered feature contracts, higher-order suites, research-cycle and
research-record suites, Awareness Studio loop and ledger tests,
integration-reconciliation, wave-1 PR suites, workflow contracts, dashboard
isolation, no-network checks, and finite-JSON checks. Compile/import checks and
`git diff --check` also passed.

GitHub checks for the open wave PRs are not usable release evidence: sampled
jobs report `failure` with zero executed steps. They are classified as
`BLOCKED_BY_INFRASTRUCTURE`, not as code-green or code-corrupt.
