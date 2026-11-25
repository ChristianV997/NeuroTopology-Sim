# Research-cycle Batch 2 integration audit

**Agent:** Codex D — Merger Agent
**Audit date:** 2026-09-11
**Integration branch:** `codex/research-cycle-batch2-integration-20260910`
**Starting live main:** `eb99d6332df27dd2576ad0c0cc1c5fcfc9972ccc`
**Final live main at audit close:** `87893139d5bd8f08a275b8f1760eb3816f9b0a6d`

This is an audit and release-gate record. It does not promote any audit-only,
synthetic, proxy, incomplete, or unavailable result to scientific evidence.
Live GitHub metadata and git ancestry are authoritative over older handoff text.

## PR matrix and ancestry

The live matrix covered PRs #275 through #318 that belonged to the research-cycle
infrastructure wave. Merged heads for #276-#283, #292, #294-#295, #299-#306,
#308-#316, #317, and #318 are reachable from the final live main. Their effective
three-dot diffs against live main are empty. Closed heads for #284-#291 and #293
are also ancestors through the validated merged lineage and were not resurrected.

Open heads remain non-ancestors:

- #296 `af0d6a050b1b313f88df9f1b41d5a3313ce6684d`, draft: contract adapter.
- #297 `90c70842cfcfdea2e4315dbf7b09faaf8cbedde1`, draft: embodied controls.
- #298 `129bf24da3f6de51334e3a643c2f607c111f1ed0`, draft: audit-only validation.
- #307 `52137e13b72ab80d08ff2b9eeffee8526774bb01`, draft: reliable runner.

PR #275 remains closed and its unsafe follow-up head `de2cb93e419cc67bad44fe27a63ddab86a288e62` is not an ancestor. Its safe subset was extracted through #299.

## Decisions

- #296 is retained open. Focused tests pass, but reverse adaptation fabricates
  `unknown_source` and `derived_from_ledger` when provenance is absent.
- #297 is retained open. Focused tests pass, but causal-linear resampling uses a
  future `idx_ceil` sample and lag correlation values are synthetic rather than
  measured coupling.
- #298 remains audit-only because its author explicitly says “Draft — do not
  merge.” Its diagnostics were not promoted into schemas or evidence.
- #307 is retained open. Its useful checkpoint/process code was not extracted
  because arbitrary child commands lack an enforceable offline boundary and
  declared absolute outputs can escape the campaign output root.
- #301 required four explicit conflict resolutions in the integration-reconciliation
  surface. The richer evidence-aware implementation was retained and its focused
  suite passed.
- #303, #308, #312, #313, and #314 received targeted safety hardening before
  integration. These changes cover bounded cache checks, checksum validation,
  platform-safe operator paths, strict non-finite JSON rejection, and fail-closed
  unknown evidence verdicts.
- No GPL/AGPL license marker or high-confidence credential marker was found in
  the wave paths. No source was copied from a GPL/AGPL project without review.

## Validation

- Merged-main bounded validation: 747 passed, 4 skipped in 14m08s.
- Retained-draft focused validation: #296 11 passed, #297 20 passed, #298 24
  passed, and #307 13 passed. Passing tests did not override the safety findings.
- Cache regression suite: 20 passed.
- No-network, dashboard-isolation, finite-JSON, and offline acceptance checks:
  33 passed.
- `python -m compileall -q shared tools scripts tests apps/awareness_studio/src ops` passed.
- `git diff --check` across the wave passed after two non-semantic cleanup PRs
  (#317 and #318), both confirmed merged by GitHub and reachable from main.

GitHub checks for the wave and cleanup PRs remain `BLOCKED_BY_INFRASTRUCTURE`:
the reported failures have no usable executed steps or logs. They are not
reported as CI success or as evidence of code corruption.

## Release gate

The accepted code remains provenance-safe locally and preserves synthetic/proxy,
causal, topology, physiological, finite-JSON, dashboard, cache, and offline
boundaries. Release is not ready while #296, #297, #298, #307 and the unusable
GitHub CI evidence remain unresolved.
