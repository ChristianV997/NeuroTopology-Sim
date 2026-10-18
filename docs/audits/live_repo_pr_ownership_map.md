# Live repository / PR ownership snapshot

Captured: **2026-10-18T08:02:49Z**
Repository: [ChristianV997/NeuroTopology-Sim](https://github.com/ChristianV997/NeuroTopology-Sim)
Live `origin/main`: `19c3203573082f8bc41f7da226b52dc20a49fdb0`
Posture: **HOLD / SYNTHETIC_ONLY**

This is a timestamped coordination and software-CI snapshot, not a live source of truth. Refresh GitHub metadata before any merge. The JSON record contains the full changed paths and per-PR workflow/review observations.

## Evidence key

- **Fact:** retrieved from Git metadata, GitHub PR API, Actions results/logs, or checked-in workflow at the recorded main SHA.
- **Inference:** integration ordering or interpretation, not a Git conflict or scientific dependency.
- **Unknown:** not observable from the connected API; never treated as pass.

## Confirmed facts

- 63 PRs were open at capture time. Live `origin/main` is `19c3203573082f8bc41f7da226b52dc20a49fdb0`; PR #405 is merged into that commit and exports `analysis.binomial_planning.wilson_score_interval`.
- Current main Required Checks failed in Awareness Studio: 3 failed, 413 passed, 1 skipped. `core-tests`, ontology-language, and cross-system smoke succeeded. The log confirms assertion mismatches and `KeyError: 'resumed'`; no production root cause is inferred.
- Five current PR heads (#392, #416, #419, #421, #427) were rechecked and show the same three Awareness failures. This is confirmed only for these sampled heads, not every failed PR.
- On main, fixed test lists omit the Round 6 geometry, topology/Hodge, spherical CSD, four-sphere, phase/surrogate, and ROC suites. The updated workflow mapping explicitly selects implementation/test pairs from changed paths and runs selected files through singleton isolated subprocesses, with JUnit collection and zero-skip/pass enforcement. The new workflow behavior has not yet run on hosted CI.
- PR #428's Docker run succeeded: author-reported Awareness container tests 417 passed/1 skipped; root CPU image ran 9 isolated batches, 9 passed, no skips/failures/timeouts. Production root image remains manual opt-in. #428 is stacked on #422, not main.
- 15 exact changed-path overlaps were found, involving 65 pairwise PR overlaps. These are ownership collisions only; overlap does not establish a Git merge conflict.
- 39 PR base SHAs differ from live main. #428 explicitly targets #422's branch. PR #357 reports GitHub `mergeable=false`; no conflicting file list was returned.
- No human approval was observed in the retrieved review submissions. Automated Copilot quota comments are not approvals.

## Unknowns

- Branch-protection/required-check configuration is **unknown**: the connected unauthenticated endpoint returned HTTP 401. Thus a successful observed workflow cannot certify required checks.
- Review-thread resolution remains unknown. The GitHub mergeable boolean does not mean approved, check-green, or merge-ready.
- No post-change hosted Actions run has shown the new candidate-test discovery gate executing real experimental candidate suites. Missing candidate implementation/test pairs or any skipped candidate test fail closed in the helper, but remote behavior remains unverified.

## Current open PR inventory

`Observed CI` summarizes fetched run conclusions on the recorded head. `Required checks` remain unknown for every PR. Full changed paths are in the [JSON snapshot](live_repo_pr_ownership_map.json).

| PR | Title | Head branch | Base → head | Draft | Mergeable signal | Observed CI | Review | Classification | Paths |
|---:|---|---|---|---|---|---|---|---|---:|
| #357 | Wire registered research execution and harden evidence integrity | `codex/overnight-execution-integration` | `ad1d480 → b0c3469` | no | false | unknown | no_reviews (0 approvals) | conflicted | 122 |
| #366 | Bound C2–C3 PITNN .vhdr/.vmrk sidecar fetches | `lingxi/bound-pitnn-header-fetch-c2c3-20260914` | `3f3fe85 → d74f6ad` | yes | true | fail | no_reviews (0 approvals) | draft | 2 |
| #367 | fix(streaming): fail-closed C1 — no unbounded S3 download_file | `cursor/fail-closed-s3-sync-c1-d374` | `3f3fe85 → 864788e` | yes | true | fail | no_reviews (0 approvals) | draft | 5 |
| #368 | Harden bounded DANDI/NWB ingestion (fail-closed) | `cursor/dandi-nwb-bounded-64cc` | `3f3fe85 → fde0596` | no | true | fail | automated_comment_only (0 approvals) | blocked | 7 |
| #369 | Add provenance-preserving metadata-first BIDS adapter | `cursor/bids-adapter-provenance-96c3` | `3f3fe85 → 2796bf8` | no | true | fail | automated_comment_only (0 approvals) | blocked | 15 |
| #370 | Batch 2: release-readiness security harness | `cursor/batch2-security-harness-6c11` | `3f3fe85 → 7e1d7c0` | no | true | fail | automated_comment_only (0 approvals) | blocked | 24 |
| #371 | feat(benchmarks): Batch-2 pipeline performance suite (synthetic, local-only) | `cursor/batch2-pipeline-benchmarks-d374` | `3f3fe85 → 2c69429` | no | true | fail | automated_comment_only (0 approvals) | blocked | 18 |
| #372 | feat(awareness-studio): gate orchestrator outputs by explicit evidence state | `claude/consciousness-transitions-tests-ggx7ph` | `3f3fe85 → fb8c929` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #373 | feat(level_t): prevent silent zero imputation and enforce cohort missingness gates | `antigravity/missingness-and-cohorts-20261016` | `3f3fe85 → 56890f3` | no | true | fail | automated_comment_only (0 approvals) | blocked | 4 |
| #374 | feat(dual_engine): deterministic structure-sensitive fusion validation and null models | `antigravity/fusion-validation-null-models-20261016` | `3f3fe85 → 9037957` | no | true | fail | automated_comment_only (0 approvals) | blocked | 4 |
| #375 | Batch 3: provenance-rich literature and public-source mining package | `grok/batch3-literature-mining-20261016` | `3f3fe85 → 69fb8af` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #376 | Add Batch 3 adversarial falsification matrix | `grok/batch3-adversarial-falsification` | `3f3fe85 → 989c483` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #377 | Higher-order runtime streaming invariance contracts | `batch2/cursor-d-streaming-invariance` | `3f3fe85 → 5f5fa72` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #378 | feat(adapters): fail-closed MNE CSD wrapper with provenance (Batch 2 / Agent C) | `batch2/cursor-c-mne-csd-adapter` | `3f3fe85 → 369af1a` | no | true | fail | automated_comment_only (0 approvals) | blocked | 14 |
| #379 | Add offline MOABB metadata-to-protocol conformance validator | `batch2/cursor-b-moabb-protocol-conformance` | `3f3fe85 → 9a94d89` | no | true | fail | automated_comment_only (0 approvals) | blocked | 15 |
| #380 | feat(adapters): in-memory MNE canonical signal-block contract (Batch 2 / Agent A) | `batch2/cursor-a-mne-signal-block-contract` | `3f3fe85 → 93c3447` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #381 | Add Batch 3 offline integration fixture runner | `batch3/codex-b-offline-integration` | `3f3fe85 → d889985` | no | true | fail | automated_comment_only (0 approvals) | blocked | 18 |
| #382 | test: offline source-mining evidence boundary contracts | `batch1/hermes-bots-source-boundaries` | `3f3fe85 → b54951c` | yes | true | fail | automated_comment_only (0 approvals) | draft | 2 |
| #383 | Add offline research-plan rubric evaluation harness | `batch1/claude-a-plan-rubric-eval` | `3f3fe85 → 7f825d2` | yes | true | fail | automated_comment_only (0 approvals) | draft | 31 |
| #384 | feat(measurement): add two-layer measurement/hypothesis mapping validator | `batch1/claude-b-measurement-hypothesis-map` | `19c3203 → 56ef76a` | yes | true | fail | automated_comment_only (0 approvals) | draft | 22 |
| #385 | feat(experimental): simplicial phase cochains and weighted Hodge decomposition reference | `batch2/antigravity-c-cochain-hodge-reference` | `3f3fe85 → f4b0c04` | no | true | fail | automated_comment_only (0 approvals) | blocked | 11 |
| #386 | Batch 1 (claude-d): OSS adoption gates and candidate compatibility review | `batch1/claude-d-oss-compat-review` | `19c3203 → 5211ef8` | no | true | fail | automated_comment_only (0 approvals) | blocked | 6 |
| #387 | feat(integration): offline synthetic pipeline replay and structural conformance harness | `batch2/antigravity-d-pipeline-replay` | `3f3fe85 → 930b63b` | no | true | fail | automated_comment_only (0 approvals) | blocked | 10 |
| #388 | feat(dual_engine): synthetic EEG forward-model contract and verification fixture | `batch2/antigravity-b-forward-model-contract` | `3f3fe85 → b19eeb2` | no | true | fail | automated_comment_only (0 approvals) | blocked | 4 |
| #389 | feat(tda): semantic conformance harness for topology backends (Batch 2 / Agent A) | `batch2/antigravity-a-tda-backend-conformance` | `3f3fe85 → 3c36323` | no | true | fail | automated_comment_only (0 approvals) | blocked | 14 |
| #390 | Batch 3: add advisory report-language checker | `batch3/codex-d-report-firewall` | `19c3203 → e7fe825` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #391 | Safe bounded public-repository source packs | `batch1/hermes-a-safe-source-harvest` | `19c3203 → ffd24db` | yes | true | fail | automated_comment_only (0 approvals) | draft | 6 |
| #392 | Batch 3: read-only provenance join auditor | `batch3/codex-c-provenance-join` | `19c3203 → 0d9eb2b` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #393 | Batch 3: theory-to-measurement review (Grok Chat A) | `batch3/grok-chat-a-theory-to-measurement` | `3f3fe85 → 5634a70` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #394 | Add Batch 3 cross-dataset replication feasibility package | `batch3/grok-chat-b-replication-dataset-feasibility` | `3f3fe85 → 82a4dac` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #395 | feat(ds005620): reconcile metadata provenance in evidence packet | `batch1/hermes-b-ds005620-manifest` | `3f3fe85 → 2f70dd9` | yes | true | fail | automated_comment_only (0 approvals) | draft | 8 |
| #396 | Add independent Round-6 Hodge decomposition numerical audit | `batch2/cursor-b-hodge-decomposition-audit` | `3f3fe85 → 01271b0` | no | true | fail | automated_comment_only (0 approvals) | blocked | 12 |
| #397 | audit(batch2): independent Round 6 finite chain-complex oracle (HOLD) | `batch2/cursor-c-3d-chain-audit` | `3f3fe85 → 188c824` | no | true | fail | automated_comment_only (0 approvals) | blocked | 14 |
| #398 | Batch 2: synthetic MV-FPR / MV-IAAFT surrogate audit (HOLD) | `batch2/cursor-d-surrogate-audit` | `3f3fe85 → 0953491` | no | true | fail | automated_comment_only (0 approvals) | blocked | 13 |
| #399 | feat(audits): independent Round 6 winding/charge discrete-identity oracle (Batch 2 / Agent A) | `batch2/cursor-a-winding-charge-audit` | `3f3fe85 → c1dd478` | no | true | fail | automated_comment_only (0 approvals) | blocked | 10 |
| #400 | test: add independent DMD EP2 matrix-log oracle | `batch1/hermes-bots-dmd-ep2-oracle` | `3f3fe85 → 2588bd2` | no | true | fail | automated_comment_only (0 approvals) | blocked | 2 |
| #401 | feat(bids): synthetic-only inventory audit and payload-checksum boundary | `batch1/claude-b-bids-prereg-integrity` | `19c3203 → 635b2f7` | yes | true | fail | automated_comment_only (0 approvals) | draft | 28 |
| #402 | Add independent NumPy reference audit for MNE CSD constants and operator | `batch1/claude-a-mne-csd-reference-audit` | `3f3fe85 → c339e89` | yes | true | fail | automated_comment_only (0 approvals) | draft | 15 |
| #403 | feat(calibration): audit and calibration harness for Round 6 phase-uncertainty estimator (Batch 2 / Agent A) | `batch2/antigravity-a-phase-uncertainty` | `3f3fe85 → 42f8f9c` | no | true | fail | automated_comment_only (0 approvals) | blocked | 10 |
| #404 | docs: independent Batch 3 provenance firewall audit | `batch3/codex-d-provenance-firewall-review` | `19c3203 → 6e06ba0` | no | true | fail | automated_comment_only (0 approvals) | blocked | 1 |
| #406 | Batch 1: source-backed OSS compatibility audit (HOLD / SYNTHETIC_ONLY) | `batch1/claude-d-oss-compatibility-map` | `19c3203 → c67d2c4` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #407 | audit(statistics): Round 6 train/test whitening audit, leakage invariants, and SPD disclosure | `batch2/antigravity-b-whitening-audit` | `3f3fe85 → f049444` | no | true | fail | automated_comment_only (0 approvals) | blocked | 11 |
| #408 | feat(sim): reproducible synthetic nuisance-scenario factory for operating-characteristic sweeps | `batch2/antigravity-d-synthetic-scenarios` | `3f3fe85 → 6ec0153` | no | true | fail | automated_comment_only (0 approvals) | blocked | 14 |
| #409 | audit: independent four-shell spherical BVP oracle | `batch1/hermes-a-shell-bvp-oracle` | `19c3203 → 7ccc59a` | yes | true | fail | automated_comment_only (0 approvals) | draft | 3 |
| #410 | audit: verify Round 6 finite-jitter triangulation claims | `batch1/hermes-b-mesh-geometry-audit` | `3f3fe85 → 45090a8` | yes | true | fail | automated_comment_only (0 approvals) | draft | 3 |
| #411 | Add Batch 3 EEG replication metadata audit | `batch3/grok-chat-b-metadata-audit` | `3f3fe85 → 8598a87` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #412 | Batch 3: Round 6 claim audit (Grok Chat A) | `batch3/grok-chat-a-round6-claim-audit` | `3f3fe85 → c483aa3` | no | true | fail | automated_comment_only (0 approvals) | blocked | 1 |
| #413 | feat(topology): oriented integer phase-winding production module (Batch 2 / Cursor B) | `cursor/phase-winding-64cc` | `19c3203 → 0de1b63` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #414 | feat(experimental): NumPy spherical-spline CSD transform (MNE 1.13.2 pin) | `cursor/spherical-csd-production-d374` | `19c3203 → 241b078` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #415 | feat(dynamics): HOLD/synthetic exact DMD + EP/Crouzeix diagnostics (Batch 2 / Agent D) | `cursor/dmd-crouzeix-6c11` | `19c3203 → 41df806` | no | true | fail | automated_comment_only (0 approvals) | blocked | 6 |
| #416 | feat(geometry): robust 2D planar triangulation with exact-sign predicates (Batch 2 / Agent A) | `batch2/cursor-a-planar-triangulation` | `19c3203 → 88b21cc` | no | true | fail | automated_comment_only (0 approvals) | blocked | 9 |
| #417 | Batch 1: surrogate-null contract and stdlib generators (synthetic, HOLD) | `batch1/claude-d-surrogate-nulls` | `19c3203 → 69e9778` | no | true | fail | automated_comment_only (0 approvals) | blocked | 10 |
| #418 | feat(physics): add experimental four-shell EEG forward model (HOLD / SYNTHETIC_ONLY) | `batch1/claude-a-four-sphere-forward-model` | `19c3203 → a1a7517` | yes | true | fail | automated_comment_only (0 approvals) | draft | 4 |
| #419 | test(experimental): independent spherical CSD parity suite and MNE 1.13.2 reference fixtures | `batch2/antigravity-c-spherical-csd-parity` | `19c3203 → 7f5c5df` | no | true | fail | automated_comment_only (0 approvals) | blocked | 2 |
| #420 | test(dynamics): independent DMD regression suite and EP2/Crouzeix oracles (Batch 2 / Agent D) | `batch2/antigravity-d-dmd-regression` | `19c3203 → 53fe976` | no | true | fail | automated_comment_only (0 approvals) | blocked | 2 |
| #421 | audit(geometry): independent adversarial test suite for planar triangulation and embedding validity (Batch 2 / Agent A) | `batch2/antigravity-a-planar-triangulation` | `19c3203 → 5735113` | no | true | fail | automated_comment_only (0 approvals) | blocked | 13 |
| #422 | fix(awareness-studio): declare registered execution memory dependency | `codex/registered-execution-dependency-fix` | `19c3203 → 93c69ff` | no | true | fail | automated_comment_only (0 approvals) | blocked | 2 |
| #423 | feat(topology): production weighted 2D discrete Hodge decomposition (Batch 2 / Antigravity B) | `batch2/antigravity-b-hodge-2d` | `19c3203 → d9381f2` | no | true | fail | automated_comment_only (0 approvals) | blocked | 10 |
| #424 | feat(simulation-runtime): fail-closed synthetic grid plan (HOLD / SYNTHETIC_ONLY) | `batch3/grok-bots-benchmark-grid-config` | `19c3203 → b20a256` | no | true | fail | automated_comment_only (0 approvals) | blocked | 3 |
| #425 | docs(audits): snapshot live PR ownership and CI state | `codex/live-repo-pr-ownership-map-20261017` | `19c3203 → c1fe3b8` | yes | true | fail | automated_comment_only (0 approvals) | draft | 4 |
| #426 | feat(benchmarks): synthetic operating-characteristics API (HOLD / SYNTHETIC_ONLY) | `batch3/grok-chat-a-synthetic-operating-characteristics` | `19c3203 → 9296d37` | no | true | fail | automated_comment_only (0 approvals) | blocked | 5 |
| #427 | Add independent synthetic ROC calibration-split contract tests | `batch3/grok-chat-b-roc-calibration-tests` | `19c3203 → 43ea2a8` | no | true | fail | automated_comment_only (0 approvals) | blocked | 1 |
| #428 | fix(docker): repair container test build contexts | `codex/docker-build-repair-on-422` | `93c69ff → 24dfd88` | no | true | pass | automated_comment_only (0 approvals) | blocked | 3 |

## Exact changed-path ownership overlaps

`git_conflict` is null in the machine record for each overlap: these are not verified merge conflicts.

| Path | PRs | Interpretation |
|---|---|---|
| `apps/awareness_studio/src/awareness_studio/orchestrator/orchestrator.py` | #357, #372 | Exact ownership overlap; Git conflict unknown |
| `data/bids_ingest.py` | #357, #369 | Exact ownership overlap; Git conflict unknown |
| `docs/experimental/planar_triangulation.md` | #416, #421 | Exact ownership overlap; Git conflict unknown |
| `neurotopology_sim/__init__.py` | #413, #414, #415, #416, #421, #423, #426 | Exact ownership overlap; Git conflict unknown |
| `neurotopology_sim/experimental/__init__.py` | #413, #414, #415, #416, #421, #423, #426 | Exact ownership overlap; Git conflict unknown |
| `neurotopology_sim/experimental/geometry/__init__.py` | #416, #421 | Exact ownership overlap; Git conflict unknown |
| `neurotopology_sim/experimental/geometry/planar_triangulation.py` | #416, #421 | Exact ownership overlap; Git conflict unknown |
| `neurotopology_sim/experimental/topology/__init__.py` | #413, #423 | Exact ownership overlap; Git conflict unknown |
| `tests/experimental/__init__.py` | #420, #421 | Exact ownership overlap; Git conflict unknown |
| `tests/neurotopology_sim/__init__.py` | #413, #416, #421, #423 | Exact ownership overlap; Git conflict unknown |
| `tests/neurotopology_sim/experimental/__init__.py` | #413, #416, #421, #423 | Exact ownership overlap; Git conflict unknown |
| `tests/neurotopology_sim/experimental/geometry/__init__.py` | #416, #421 | Exact ownership overlap; Git conflict unknown |
| `tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py` | #416, #421 | Exact ownership overlap; Git conflict unknown |
| `tests/neurotopology_sim/experimental/topology/__init__.py` | #413, #423 | Exact ownership overlap; Git conflict unknown |
| `tools/stream_process_dandi000458.py` | #357, #368 | Exact ownership overlap; Git conflict unknown |

## Integration order

- **Geometry:** pair implementation #416 with adversarial suite #421; overlap exists on geometry source and test/helper paths. Test-only merge before implementation is not supported.
- **Spherical CSD:** pair implementation #414 with parity #419; optional MNE skips are not a pass. #402 is a reference audit.
- **Topology/Hodge:** implementation #423 must be assessed with its tests plus related audit PRs #385/#396; keep winding (#413) separate.
- **Four-sphere:** pair implementation #418 with independent BVP oracle #409; historical skip claims require the current lane's full candidate tests.
- **Phase/surrogate:** production and audit/test PRs #398/#403/#413/#417 need direct pairing; #417 also states review ordering after #398.
- **Synthetic ROC:** implementation #426 and tests #427 are a dependency pair; #427 must not merge as a test-only suite that skips absent code.
- **Docker:** #428 depends on #422; verify dependency merge and retarget/re-run before considering #428.

These are integration-order recommendations from PR descriptions and changed paths, not scientific validation or Git conflict assertions.

## Workflow test-discovery evidence

`required-checks.yml` invokes `round6_experimental_tests.py` after core tests. The helper maps changed paths to planar geometry, Hodge 2D, spherical CSD, four-sphere, phase winding, surrogate nulls, phase uncertainty, surrogate audit, and synthetic ROC. For each selected lane it requires checked-in implementation and test files, runs every mapped test file using `scripts/run_tests_isolated.py --batch-size 1 --timeout-s 120` even when an earlier file fails, and fails the lane when isolated-runner telemetry is invalid, JUnit is absent, no tests are collected, any skip occurs, or any failure/error occurs. A non-lane diff reports `NOT_APPLICABLE` and explicitly does not certify an experimental lane. The updated workflow has not yet been validated by a hosted Actions run.

## Readiness

- **Ready:** none. Required-check configuration is unknown and no human approval was observed.
- **Blocked:** 49 PRs: #368, #369, #370, #371, #372, #373, #374, #375, #376, #377, #378, #379, #380, #381, #385, #386, #387, #388, #389, #390, #392, #393, #394, #396, #397, #398, #399, #400, #403, #404, #406, #407, #408, #411, #412, #413, #414, #415, #416, #417, #419, #420, #421, #422, #423, #424, #426, #427, #428. Reasons vary by PR (observed failing run, no approval, unknown required checks, dependency/base state).
- **Conflict signal:** PR #357 (GitHub mergeable=false; no conflict paths available).
- **Draft:** 13 PRs: #366, #367, #382, #383, #384, #391, #395, #401, #402, #409, #410, #418, #425.
- **Unknown readiness:** none categorized separately; required-check status is unknown for all PRs and PR #357's CI observation is also unknown.

No merge was performed. This audit and the workflow change are software/CI coordination only and do not alter HOLD / SYNTHETIC_ONLY or establish scientific validity.
