# Live repository / PR ownership snapshot

Captured: **2026-10-18T21:06:58Z**
Repository: [ChristianV997/NeuroTopology-Sim](https://github.com/ChristianV997/NeuroTopology-Sim)
Live origin/main: 19c3203573082f8bc41f7da226b52dc20a49fdb0
Posture: **HOLD / SYNTHETIC_ONLY**

This is a timestamped coordination and software-CI snapshot, not a live source of truth. Refresh GitHub metadata before any merge. The JSON record contains complete changed paths and per-PR workflow/review observations. PR #425's row reflects the live GitHub state at capture; this snapshot update itself was still uncommitted.

## Evidence key

- **Fact:** retrieved from Git metadata, GitHub PR/rules API, Actions results/logs, or checked-in workflow at the recorded main SHA.
- **Inference:** integration ordering or interpretation, not a Git conflict or scientific dependency.
- **Unknown:** not observable from the connected API; never treated as pass.

## Live main and policy facts

- **Fact:** origin/main is 19c3203573082f8bc41f7da226b52dc20a49fdb0. PR #405 is merged into this commit and exports analysis.binomial_planning.wilson_score_interval.
- **Fact:** main Required Checks failed at the latest run attached to this SHA: core-tests passed, Awareness tests failed (3 failed, 413 passed, 1 skipped), ontology-language passed, and Cross-system smoke passed. Logs confirm assertion mismatches plus KeyError: 'resumed'; no production cause is inferred.
- **Fact:** 63 PRs are currently open. 13 exact changed-path overlaps create 63 pairwise ownership collisions; these are not Git conflicts.
- **Fact:** 39 PR base SHAs differ from current main; PR #428 is stacked on #422. GitHub reports 1 mergeable=CONFLICTING signal(s).
- **Fact:** effective main rules list deletion, non-fast-forward, and Copilot code review; no required_status_checks rule was returned. The traditional branch-protection endpoint returned HTTP 404. Observed workflow status is diagnostic, not enforced required-check policy.
- **Fact:** no current human APPROVED review submission was observed in the open set. Automated Copilot quota comments are not approvals. Review-thread resolution is unknown.
- **Inference:** no PR is certified ready in this snapshot: none has human approval, several observed workflow checks fail, and PR #428 is stacked. Re-fetch all state before any merge.

## Required Checks candidate discovery

- The helper .github/workflows/round6_experimental_tests.py has 15 explicit components and 72 source/test pairs. Exact triggers, pairs, and required test files are recorded under main_ci.round6_candidate_discovery in JSON.
- Changed candidate paths select a lane and must resolve to explicit implementation/test pairs. Missing source/tests or an unmapped candidate path blocks execution; empty collection, any skip/failure/error, invalid telemetry, or timeout fails the lane. Each test file uses a fresh isolated process.
- A change outside candidate lanes emits NOT_APPLICABLE, not a pass.
- Coverage over current open PR paths: #385, #389, #390, #392, #396, #397, #398, #399, #402, #403, #409, #413, #414, #416, #417, #418, #419, #421, #423, #424, #426, #427. Unmapped candidate paths: none.
- **Local candidate probe:** PR #424 head 2f8e2c8: actual test command python -m unittest tests.simulation_runtime.test_grid_plan -v passed 28 tests. The isolated helper did not collect tests because the bundled Python lacks pytest-timeout; requirements-base.txt declares it, and no package was installed. The isolated run is not a pass.
- **Hosted state:** no hosted Actions run has executed the new helper against an actual changed candidate lane. PR #425's latest hosted head did not touch a candidate path; its core-tests success does not establish candidate execution.

## Current open PR inventory

Observed CI summarizes live GitHub check-run conclusions. The effective branch rules showed no required status-check rule; this does not turn failed/pending workflows into passes. Full changed paths are in the JSON snapshot.

| PR | Title | Head branch | Base → head | Draft | Mergeability signal | Observed CI | Review | Classification | Paths |
|---:|---|---|---|---|---|---|---|---|---:|
| [#357](https://github.com/ChristianV997/NeuroTopology-Sim/pull/357) | Wire registered research execution and harden evidence integrity | codex/overnight-execution-integration | ad1d480 → b0c3469 | no | CONFLICTING | unknown | no_reviews (0 approvals) | conflicted | 100 |
| [#366](https://github.com/ChristianV997/NeuroTopology-Sim/pull/366) | Bound C2â€“C3 PITNN .vhdr/.vmrk sidecar fetches | lingxi/bound-pitnn-header-fetch-c2c3-20260914 | 3f3fe85 → d74f6ad | yes | MERGEABLE | fail | no_reviews (0 approvals) | draft | 2 |
| [#367](https://github.com/ChristianV997/NeuroTopology-Sim/pull/367) | fix(streaming): fail-closed C1 â€” no unbounded S3 download_file | cursor/fail-closed-s3-sync-c1-d374 | 3f3fe85 → 864788e | yes | MERGEABLE | fail | no_reviews (0 approvals) | draft | 5 |
| [#368](https://github.com/ChristianV997/NeuroTopology-Sim/pull/368) | Harden bounded DANDI/NWB ingestion (fail-closed) | cursor/dandi-nwb-bounded-64cc | 3f3fe85 → fde0596 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 7 |
| [#369](https://github.com/ChristianV997/NeuroTopology-Sim/pull/369) | Add provenance-preserving metadata-first BIDS adapter | cursor/bids-adapter-provenance-96c3 | 3f3fe85 → 2796bf8 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 15 |
| [#370](https://github.com/ChristianV997/NeuroTopology-Sim/pull/370) | Batch 2: release-readiness security harness | cursor/batch2-security-harness-6c11 | 3f3fe85 → 7e1d7c0 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 24 |
| [#371](https://github.com/ChristianV997/NeuroTopology-Sim/pull/371) | feat(benchmarks): Batch-2 pipeline performance suite (synthetic, local-only) | cursor/batch2-pipeline-benchmarks-d374 | 3f3fe85 → 2c69429 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 18 |
| [#372](https://github.com/ChristianV997/NeuroTopology-Sim/pull/372) | feat(awareness-studio): gate orchestrator outputs by explicit evidence state | claude/consciousness-transitions-tests-ggx7ph | 3f3fe85 → fb8c929 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#373](https://github.com/ChristianV997/NeuroTopology-Sim/pull/373) | feat(level_t): prevent silent zero imputation and enforce cohort missingness gates | antigravity/missingness-and-cohorts-20261016 | 3f3fe85 → 56890f3 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 4 |
| [#374](https://github.com/ChristianV997/NeuroTopology-Sim/pull/374) | feat(dual_engine): deterministic structure-sensitive fusion validation and null models | antigravity/fusion-validation-null-models-20261016 | 3f3fe85 → 9037957 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 4 |
| [#375](https://github.com/ChristianV997/NeuroTopology-Sim/pull/375) | Batch 3: provenance-rich literature and public-source mining package | grok/batch3-literature-mining-20261016 | 3f3fe85 → 69fb8af | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#376](https://github.com/ChristianV997/NeuroTopology-Sim/pull/376) | Add Batch 3 adversarial falsification matrix | grok/batch3-adversarial-falsification | 3f3fe85 → 989c483 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#377](https://github.com/ChristianV997/NeuroTopology-Sim/pull/377) | Higher-order runtime streaming invariance contracts | batch2/cursor-d-streaming-invariance | 3f3fe85 → 5f5fa72 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#378](https://github.com/ChristianV997/NeuroTopology-Sim/pull/378) | feat(adapters): fail-closed MNE CSD wrapper with provenance (Batch 2 / Agent C) | batch2/cursor-c-mne-csd-adapter | 3f3fe85 → 369af1a | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 14 |
| [#379](https://github.com/ChristianV997/NeuroTopology-Sim/pull/379) | Add offline MOABB metadata-to-protocol conformance validator | batch2/cursor-b-moabb-protocol-conformance | 3f3fe85 → 9a94d89 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 15 |
| [#380](https://github.com/ChristianV997/NeuroTopology-Sim/pull/380) | feat(adapters): in-memory MNE canonical signal-block contract (Batch 2 / Agent A) | batch2/cursor-a-mne-signal-block-contract | 3f3fe85 → 93c3447 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#381](https://github.com/ChristianV997/NeuroTopology-Sim/pull/381) | Add Batch 3 offline integration fixture runner | batch3/codex-b-offline-integration | 3f3fe85 → d889985 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 18 |
| [#382](https://github.com/ChristianV997/NeuroTopology-Sim/pull/382) | test: offline source-mining evidence boundary contracts | batch1/hermes-bots-source-boundaries | 3f3fe85 → b54951c | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 2 |
| [#383](https://github.com/ChristianV997/NeuroTopology-Sim/pull/383) | Add offline research-plan rubric evaluation harness | batch1/claude-a-plan-rubric-eval | 3f3fe85 → 7f825d2 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 31 |
| [#384](https://github.com/ChristianV997/NeuroTopology-Sim/pull/384) | feat(measurement): add two-layer measurement/hypothesis mapping validator | batch1/claude-b-measurement-hypothesis-map | 19c3203 → 56ef76a | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 22 |
| [#385](https://github.com/ChristianV997/NeuroTopology-Sim/pull/385) | feat(experimental): simplicial phase cochains and weighted Hodge decomposition reference | batch2/antigravity-c-cochain-hodge-reference | 3f3fe85 → f4b0c04 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 11 |
| [#386](https://github.com/ChristianV997/NeuroTopology-Sim/pull/386) | Batch 1 (claude-d): OSS adoption gates and candidate compatibility review | batch1/claude-d-oss-compat-review | 19c3203 → 5211ef8 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 6 |
| [#387](https://github.com/ChristianV997/NeuroTopology-Sim/pull/387) | feat(integration): offline synthetic pipeline replay and structural conformance harness | batch2/antigravity-d-pipeline-replay | 3f3fe85 → 930b63b | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 10 |
| [#388](https://github.com/ChristianV997/NeuroTopology-Sim/pull/388) | feat(dual_engine): synthetic EEG forward-model contract and verification fixture | batch2/antigravity-b-forward-model-contract | 3f3fe85 → b19eeb2 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 4 |
| [#389](https://github.com/ChristianV997/NeuroTopology-Sim/pull/389) | feat(tda): semantic conformance harness for topology backends (Batch 2 / Agent A) | batch2/antigravity-a-tda-backend-conformance | 3f3fe85 → 3c36323 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 14 |
| [#390](https://github.com/ChristianV997/NeuroTopology-Sim/pull/390) | Batch 3: add advisory report-language checker | batch3/codex-d-report-firewall | 19c3203 → e7fe825 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#391](https://github.com/ChristianV997/NeuroTopology-Sim/pull/391) | Safe bounded public-repository source packs | batch1/hermes-a-safe-source-harvest | 19c3203 → ffd24db | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 6 |
| [#392](https://github.com/ChristianV997/NeuroTopology-Sim/pull/392) | Batch 3: read-only provenance join auditor | batch3/codex-c-provenance-join | 19c3203 → bb02e88 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#393](https://github.com/ChristianV997/NeuroTopology-Sim/pull/393) | Batch 3: theory-to-measurement review (Grok Chat A) | batch3/grok-chat-a-theory-to-measurement | 3f3fe85 → 5634a70 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#394](https://github.com/ChristianV997/NeuroTopology-Sim/pull/394) | Add Batch 3 cross-dataset replication feasibility package | batch3/grok-chat-b-replication-dataset-feasibility | 3f3fe85 → 82a4dac | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#395](https://github.com/ChristianV997/NeuroTopology-Sim/pull/395) | feat(ds005620): reconcile metadata provenance in evidence packet | batch1/hermes-b-ds005620-manifest | 3f3fe85 → 2f70dd9 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 8 |
| [#396](https://github.com/ChristianV997/NeuroTopology-Sim/pull/396) | Add independent Round-6 Hodge decomposition numerical audit | batch2/cursor-b-hodge-decomposition-audit | 3f3fe85 → 01271b0 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 12 |
| [#397](https://github.com/ChristianV997/NeuroTopology-Sim/pull/397) | audit(batch2): independent Round 6 finite chain-complex oracle (HOLD) | batch2/cursor-c-3d-chain-audit | 3f3fe85 → 188c824 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 14 |
| [#398](https://github.com/ChristianV997/NeuroTopology-Sim/pull/398) | Batch 2: synthetic MV-FPR / MV-IAAFT surrogate audit (HOLD) | batch2/cursor-d-surrogate-audit | 3f3fe85 → 0953491 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 13 |
| [#399](https://github.com/ChristianV997/NeuroTopology-Sim/pull/399) | feat(audits): independent Round 6 winding/charge discrete-identity oracle (Batch 2 / Agent A) | batch2/cursor-a-winding-charge-audit | 3f3fe85 → c1dd478 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 10 |
| [#400](https://github.com/ChristianV997/NeuroTopology-Sim/pull/400) | test: add independent DMD EP2 matrix-log oracle | batch1/hermes-bots-dmd-ep2-oracle | 3f3fe85 → 2588bd2 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 2 |
| [#401](https://github.com/ChristianV997/NeuroTopology-Sim/pull/401) | feat(bids): synthetic-only inventory audit and payload-checksum boundary | batch1/claude-b-bids-prereg-integrity | 19c3203 → 635b2f7 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 28 |
| [#402](https://github.com/ChristianV997/NeuroTopology-Sim/pull/402) | Add independent NumPy reference audit for MNE CSD constants and operator | batch1/claude-a-mne-csd-reference-audit | 3f3fe85 → c339e89 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 15 |
| [#403](https://github.com/ChristianV997/NeuroTopology-Sim/pull/403) | feat(calibration): audit and calibration harness for Round 6 phase-uncertainty estimator (Batch 2 / Agent A) | batch2/antigravity-a-phase-uncertainty | 3f3fe85 → 42f8f9c | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 10 |
| [#404](https://github.com/ChristianV997/NeuroTopology-Sim/pull/404) | docs: independent Batch 3 provenance firewall audit | batch3/codex-d-provenance-firewall-review | 19c3203 → 6e06ba0 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 1 |
| [#406](https://github.com/ChristianV997/NeuroTopology-Sim/pull/406) | Batch 1: source-backed OSS compatibility audit (HOLD / SYNTHETIC_ONLY) | batch1/claude-d-oss-compatibility-map | 19c3203 → c67d2c4 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#407](https://github.com/ChristianV997/NeuroTopology-Sim/pull/407) | audit(statistics): Round 6 train/test whitening audit, leakage invariants, and SPD disclosure | batch2/antigravity-b-whitening-audit | 3f3fe85 → f049444 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 11 |
| [#408](https://github.com/ChristianV997/NeuroTopology-Sim/pull/408) | feat(sim): reproducible synthetic nuisance-scenario factory for operating-characteristic sweeps | batch2/antigravity-d-synthetic-scenarios | 3f3fe85 → 6ec0153 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 14 |
| [#409](https://github.com/ChristianV997/NeuroTopology-Sim/pull/409) | audit: independent four-shell spherical BVP oracle | batch1/hermes-a-shell-bvp-oracle | 19c3203 → 7ccc59a | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 3 |
| [#410](https://github.com/ChristianV997/NeuroTopology-Sim/pull/410) | audit: verify Round 6 finite-jitter triangulation claims | batch1/hermes-b-mesh-geometry-audit | 3f3fe85 → 45090a8 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 3 |
| [#411](https://github.com/ChristianV997/NeuroTopology-Sim/pull/411) | Add Batch 3 EEG replication metadata audit | batch3/grok-chat-b-metadata-audit | 3f3fe85 → 8598a87 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#412](https://github.com/ChristianV997/NeuroTopology-Sim/pull/412) | Batch 3: Round 6 claim audit (Grok Chat A) | batch3/grok-chat-a-round6-claim-audit | 3f3fe85 → c483aa3 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 1 |
| [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413) | feat(topology): oriented integer phase-winding production module (Batch 2 / Cursor B) | cursor/phase-winding-64cc | 19c3203 → 015eb3b | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#414](https://github.com/ChristianV997/NeuroTopology-Sim/pull/414) | feat(experimental): NumPy spherical-spline CSD transform (MNE 1.13.2 pin) | cursor/spherical-csd-production-d374 | 19c3203 → 241b078 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#415](https://github.com/ChristianV997/NeuroTopology-Sim/pull/415) | feat(dynamics): HOLD/synthetic exact DMD + EP/Crouzeix diagnostics (Batch 2 / Agent D) | cursor/dmd-crouzeix-6c11 | 19c3203 → 41df806 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 6 |
| [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416) | feat(geometry): robust 2D planar triangulation with exact-sign predicates (Batch 2 / Agent A) | batch2/cursor-a-planar-triangulation | 19c3203 → e4a44f6 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#417](https://github.com/ChristianV997/NeuroTopology-Sim/pull/417) | Batch 1: surrogate-null contract and stdlib generators (synthetic, HOLD) | batch1/claude-d-surrogate-nulls | 19c3203 → f8939ee | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 11 |
| [#418](https://github.com/ChristianV997/NeuroTopology-Sim/pull/418) | feat(physics): add experimental four-shell EEG forward model (HOLD / SYNTHETIC_ONLY) | batch1/claude-a-four-sphere-forward-model | 19c3203 → 330f8f6 | yes | MERGEABLE | fail | automated_comment_only (0 approvals) | draft | 4 |
| [#419](https://github.com/ChristianV997/NeuroTopology-Sim/pull/419) | test(experimental): independent spherical CSD parity suite and MNE 1.13.2 reference fixtures | batch2/antigravity-c-spherical-csd-parity | 19c3203 → fa8f0f7 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 2 |
| [#420](https://github.com/ChristianV997/NeuroTopology-Sim/pull/420) | test(dynamics): independent DMD regression suite and EP2/Crouzeix oracles (Batch 2 / Agent D) | batch2/antigravity-d-dmd-regression | 19c3203 → 53fe976 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 2 |
| [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | audit(geometry): independent adversarial test suite for planar triangulation and embedding validity (Batch 2 / Agent A) | batch2/antigravity-a-planar-triangulation | 19c3203 → 8fb8c98 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 13 |
| [#422](https://github.com/ChristianV997/NeuroTopology-Sim/pull/422) | fix(awareness-studio): declare registered execution memory dependency | codex/registered-execution-dependency-fix | 19c3203 → 93c69ff | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 2 |
| [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423) | feat(topology): production weighted 2D discrete Hodge decomposition (Batch 2 / Antigravity B) | batch2/antigravity-b-hodge-2d | 19c3203 → a1efd82 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 9 |
| [#424](https://github.com/ChristianV997/NeuroTopology-Sim/pull/424) | fix(simulation-runtime): declare grid metrics and pre-run bounds | batch3/grok-bots-benchmark-grid-config | 19c3203 → 2f8e2c8 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 3 |
| [#425](https://github.com/ChristianV997/NeuroTopology-Sim/pull/425) | docs(audits): snapshot live PR ownership and CI state | codex/live-repo-pr-ownership-map-20261017 | 19c3203 → 7b2e162 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 6 |
| [#426](https://github.com/ChristianV997/NeuroTopology-Sim/pull/426) | feat(benchmarks): synthetic operating-characteristics API (HOLD / SYNTHETIC_ONLY) | batch3/grok-chat-a-synthetic-operating-characteristics | 19c3203 → 5511514 | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 5 |
| [#427](https://github.com/ChristianV997/NeuroTopology-Sim/pull/427) | Add independent synthetic ROC calibration-split contract tests | batch3/grok-chat-b-roc-calibration-tests | 19c3203 → 27d451f | no | MERGEABLE | fail | automated_comment_only (0 approvals) | blocked | 1 |
| [#428](https://github.com/ChristianV997/NeuroTopology-Sim/pull/428) | fix(docker): repair container test build contexts | codex/docker-build-repair-on-422 | 93c69ff → 24dfd88 | no | MERGEABLE | pass | automated_comment_only (0 approvals) | blocked | 3 |

## Exact changed-path ownership overlaps

git_conflict is null for every overlap: these are not verified merge conflicts.

| Path | PRs | Interpretation |
|---|---|---|
| apps/awareness_studio/src/awareness_studio/orchestrator/orchestrator.py | [#357](https://github.com/ChristianV997/NeuroTopology-Sim/pull/357), [#372](https://github.com/ChristianV997/NeuroTopology-Sim/pull/372) | Exact ownership overlap; Git conflict unknown |
| data/bids_ingest.py | [#357](https://github.com/ChristianV997/NeuroTopology-Sim/pull/357), [#369](https://github.com/ChristianV997/NeuroTopology-Sim/pull/369) | Exact ownership overlap; Git conflict unknown |
| docs/experimental/planar_triangulation.md | [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| neurotopology_sim/__init__.py | [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413), [#414](https://github.com/ChristianV997/NeuroTopology-Sim/pull/414), [#415](https://github.com/ChristianV997/NeuroTopology-Sim/pull/415), [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421), [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423), [#426](https://github.com/ChristianV997/NeuroTopology-Sim/pull/426) | Exact ownership overlap; Git conflict unknown |
| neurotopology_sim/experimental/__init__.py | [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413), [#414](https://github.com/ChristianV997/NeuroTopology-Sim/pull/414), [#415](https://github.com/ChristianV997/NeuroTopology-Sim/pull/415), [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421), [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423), [#426](https://github.com/ChristianV997/NeuroTopology-Sim/pull/426) | Exact ownership overlap; Git conflict unknown |
| neurotopology_sim/experimental/geometry/__init__.py | [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| neurotopology_sim/experimental/geometry/planar_triangulation.py | [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| tests/experimental/__init__.py | [#420](https://github.com/ChristianV997/NeuroTopology-Sim/pull/420), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| tests/neurotopology_sim/__init__.py | [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413), [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421), [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423) | Exact ownership overlap; Git conflict unknown |
| tests/neurotopology_sim/experimental/__init__.py | [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413), [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421), [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423) | Exact ownership overlap; Git conflict unknown |
| tests/neurotopology_sim/experimental/geometry/__init__.py | [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py | [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416), [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | Exact ownership overlap; Git conflict unknown |
| tests/neurotopology_sim/experimental/topology/__init__.py | [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413), [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423) | Exact ownership overlap; Git conflict unknown |

## Integration order (inference)

- **Geometry:** pair implementation #416 with direct adversarial tests #421.
- **Spherical CSD:** pair implementation #414 with parity #419; #402 is a NumPy/reference audit. Optional MNE skips are not a pass.
- **Topology/Hodge:** assess #423 with independent audits #385/#396 and direct tests; keep phase winding #413 distinct.
- **Four-sphere:** pair implementation #418 with oracle #409 and run both mapped test files.
- **Phase/surrogate:** separately exercise winding #413, surrogate contract #417, phase uncertainty #403, and surrogate audit #398.
- **Synthetic ROC:** pair #426 with independent tests #427; synthetic operating characteristics are not empirical evidence.
- **Additional explicit lanes:** simulation grid planner #424, report firewall #390, provenance join #392, topology backend conformance #389, finite-chain audit #397, and winding/charge audit #399.

## Readiness disposition

- Counts at capture: **0 ready, 12 draft, 50 blocked, 1 conflicted, 0 unknown**.
- mergeable=true is GitHub's mergeability signal only, not approval, passing CI, or readiness. Refresh current checks/reviews/branches before any merge.
- Structural CI conformance is not scientific validation. No biological, causal, consciousness, or empirical claim is established.

## Limitations

- This timestamped coordination/software-CI snapshot is not a live source of truth; refresh GitHub metadata before any merge.
- Review-thread resolution is unknown because review submission data does not expose unresolved inline-thread state.
- GitHub mergeability is only an API signal, not approval or readiness. Exact path overlap is not a Git conflict.
- No hosted Actions run has executed this discovery change against a changed candidate lane. PR #425's recorded hosted head predates these local edits.
- The local isolated runner probe was blocked because the bundled runtime lacks pytest-timeout; requirements-base.txt declares pytest-timeout>=2.3.0 and no package was installed.
- Open PRs were inspected through metadata/file lists and logs; no PR branch was checked out except PR #424's disposable detached worktree for a real local test.
- No participant data, EEG data, ds005620 content, or external datasets were accessed. Posture remains HOLD / SYNTHETIC_ONLY.
