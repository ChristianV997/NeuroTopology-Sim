# Live repository PR ownership and CI audit

- Captured: `2026-10-19T01:20:09Z` (UTC)
- Repository: [`ChristianV997/NeuroTopology-Sim`](https://github.com/ChristianV997/NeuroTopology-Sim)
- Verified `origin/main`: [`19c3203573082f8bc41f7da226b52dc20a49fdb0`](https://github.com/ChristianV997/NeuroTopology-Sim/commit/19c3203573082f8bc41f7da226b52dc20a49fdb0)
- Posture: **HOLD / SYNTHETIC_ONLY**
- Timestamped snapshot; refresh live GitHub metadata before merges.

## Inventory summary

- Open PRs examined: **64**; drafts: **12**; stale base refs: **40**.
- Exact overlapping paths: **15**; path-pair incidences: **65**. These are ownership overlaps, not Git conflict determinations.
- Observed workflow check state: 62 failed PRs, 1 passing PRs, 1 unknown/pending.
- Readiness: `ready`=0, `draft`=12, `blocked`=51, `conflicted`=1, `unknown`=0.
- PR #405 merged at `19c3203573082f8bc41f7da226b52dc20a49fdb0`; Wilson interface is present on current main.

## Required checks and branch rules

- Effective rules: deletion, non_fast_forward, copilot_code_review.
- Classic branch-protection endpoint returned HTTP 404; required-check configuration is **UNKNOWN**.
- Current-main runs:
  - [Smoke #39001665794](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665794): `success` at `19c3203573`.
  - [Required Checks #39001665754](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754): `failure` at `19c3203573`.
  - [Ontology Claim Language #39001665809](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665809): `success` at `19c3203573`.
- Awareness failure: [3 failed, 413 passed, 1 skipped](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754/job/117305700895); exact test names are in the JSON. No shared root cause is inferred.

## PR #425 and experimental discovery

- PR #425 at capture: base `19c3203573082f8bc41f7da226b52dc20a49fdb0`, head `689c4c465506630e856f8fa134fc254abadbcbae`, draft `False`, mergeable `MERGEABLE`, state `UNSTABLE`, review decision `unknown`.
- Current observed checks: ontology-claim-language=success, core-tests=success, Cross-system smoke=success, awareness-tests=failure, Mergify Merge Protections=neutral, Mergify Merge Queue=neutral, Summary=success.
- [PR #425 hosted helper run 39166611111](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39166611111/job/117790768938) returned **NOT_APPLICABLE**; no experimental lane ran.
- Helper map covers **16 components / 78 implementation-test pairs**; open-PR scan found 0 unmapped candidate paths.
- Local candidate probes: **BLOCKED before collection**; see exact refs, combined commits, and attempt counts below. Zero candidate tests ran.

### Local combined candidate probes

| Lane | PR refs (head SHA) | Combined tree | Component(s) | Isolated attempts | Collected | Outcome |
|---|---|---|---|---:|---:|---|
| geometry | #416 `04d5af7321`, #421 `14c218750b` | `7ae91ac78c` | planar_geometry | 2 | 0 | BLOCKED |
| spherical_csd | #414 `24ad946c1c`, #419 `fa8f0f7c1f` | `12adc0d4c4` | spherical_csd | 2 | 0 | BLOCKED |
| four_sphere | #418 `e316933282`, #409 `2ce74f5e24` | `dc3de2e405` | four_sphere | 3 | 0 | BLOCKED |
| winding_hodge | #413 `3328dd15a9`, #423 `a1efd82252` | `99d0a97e38` | hodge_2d, phase_winding | 2 | 0 | BLOCKED |
| dmd | #415 `d3072e8963`, #420 `1b0500dbef` | `05afa8b566` | dmd_crouzeix | 2 | 0 | BLOCKED |
| surrogate | #417 `25c5afeac3`, #398 `095349199b` | `b3ce80bbf5` | surrogate_nulls, surrogate_audit | 10 | 0 | BLOCKED |
| synthetic_roc | #426 `55115149c7`, #427 `e64304087d` | `f8741b95cc` | synthetic_roc | 2 | 0 | BLOCKED |

Probe procedure after a permitted environment setup: run `python .github/workflows/round6_experimental_tests.py --base <verified-main-sha> --head <combined-tree-sha> --root <candidate-worktree> --report <report.json>` in the repository-declared CPU environment. Do not call it a pass until the result shows collection and completed tests.

### Separate hosted candidate suite

- [PR #429 core-tests run 39183911375](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39183911375/job/117842224967) on head `18ba01d6f852502cb82aa612f47891070353ccc0` executed the seven listed `tests/surrogate_nulls/` files within 16 isolated batches: **16 passed, 0 skipped, 0 failed**. This is PR #429's explicit core-test addition, not evidence that PR #425's discovery helper was exercised.

## Integration lanes

| Lane | Implementation PR(s) | Direct/adversarial test PR(s) | Main candidate files present | Mapped tests |
|---|---|---|---|
| geometry | #416 | #421 | 0/3 | tests/experimental/test_planar_triangulation.py, tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py |
| spherical_csd | #414 | #419 | 0/13 | tests/experimental/test_spherical_csd_parity.py, tests/mne_csd_reference_audit/test_isolation_and_pin.py, tests/mne_csd_reference_audit/test_kkt_operator.py, tests/mne_csd_reference_audit/test_legendre_constants.py, tests/mne_csd_reference_audit/test_mne_integration_optional.py, tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py |
| four_sphere | #418 | #409 | 0/5 | tests/experimental_audits/test_four_shell_bvp_oracle.py, tests/physics/eeg_forward/test_four_sphere.py, tests/physics/test_four_sphere_oracle.py |
| winding_hodge | #413, #423 |  | 0/21 | tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py, tests/experimental/phase_cochain_reference/test_coboundary_exactness.py, tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py, tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py, tests/neurotopology_sim/experimental/topology/test_hodge_2d.py, tests/neurotopology_sim/experimental/topology/test_phase_winding.py, tests/tools/hodge_decomposition_audit/test_hodge_audit.py |
| dmd_crouzeix | #415 | #420 | 0/3 | tests/dmd_crouzeix_contract/test_production_contract.py, tests/experimental/test_dmd_crouzeix.py |
| phase_surrogate | #417, #398, #403 |  | 0/28 | tests/neurotopology_sim/experimental/topology/test_phase_winding.py, tests/phase_uncertainty/test_calibration_coverage.py, tests/phase_uncertainty/test_candidate_contract.py, tests/phase_uncertainty/test_synthetic_fixtures.py, tests/surrogate_audit/test_invalid_inputs.py, tests/surrogate_audit/test_mv_fpr.py, tests/surrogate_audit/test_mv_iaaft.py, tests/surrogate_nulls/test_cholesky_csd.py, tests/surrogate_nulls/test_csd_estimators.py, tests/surrogate_nulls/test_edge_cases.py, tests/surrogate_nulls/test_hardening_diagnostics.py, tests/surrogate_nulls/test_mv_iaaft.py, tests/surrogate_nulls/test_phase_nulls.py, tests/surrogate_nulls/test_real_part_and_validity.py |
| synthetic_roc | #426 | #427 | 0/3 | tests/experimental/test_synthetic_roc_calibration_split.py, tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py |

## Exact changed-path overlaps

| Path | PR owners | Meaning |
|---|---|---|
| `.github/workflows/required-checks.yml` | #425, #429 | Ownership overlap only; Git conflict unknown. |
| `apps/awareness_studio/src/awareness_studio/orchestrator/orchestrator.py` | #357, #372 | Ownership overlap only; Git conflict unknown. |
| `data/bids_ingest.py` | #357, #369 | Ownership overlap only; Git conflict unknown. |
| `docs/experimental/planar_triangulation.md` | #416, #421 | Ownership overlap only; Git conflict unknown. |
| `neurotopology_sim/__init__.py` | #413, #414, #415, #416, #421, #423, #426 | Ownership overlap only; Git conflict unknown. |
| `neurotopology_sim/experimental/__init__.py` | #413, #414, #415, #416, #421, #423, #426 | Ownership overlap only; Git conflict unknown. |
| `neurotopology_sim/experimental/geometry/__init__.py` | #416, #421 | Ownership overlap only; Git conflict unknown. |
| `neurotopology_sim/experimental/geometry/planar_triangulation.py` | #416, #421 | Ownership overlap only; Git conflict unknown. |
| `tests/experimental/__init__.py` | #420, #421 | Ownership overlap only; Git conflict unknown. |
| `tests/neurotopology_sim/__init__.py` | #413, #416, #421, #423 | Ownership overlap only; Git conflict unknown. |
| `tests/neurotopology_sim/experimental/__init__.py` | #413, #416, #421, #423 | Ownership overlap only; Git conflict unknown. |
| `tests/neurotopology_sim/experimental/geometry/__init__.py` | #416, #421 | Ownership overlap only; Git conflict unknown. |
| `tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py` | #416, #421 | Ownership overlap only; Git conflict unknown. |
| `tests/neurotopology_sim/experimental/topology/__init__.py` | #413, #423 | Ownership overlap only; Git conflict unknown. |
| `tools/stream_process_dandi000458.py` | #357, #368 | Ownership overlap only; Git conflict unknown. |

## Full live open-PR inventory

| PR | Title | Base → head | Draft | GitHub mergeability / state | Review | Observed CI | Required CI | Readiness | Paths |
|---:|---|---|---|---|---|---|---|---|---:|
| [#357](https://github.com/ChristianV997/NeuroTopology-Sim/pull/357) | Wire registered research execution and harden evidence integrity | `ad1d480828` → `b0c34699f9` | no | DIRTY / False | no_reviews (0 approvals) | unknown | unknown | conflicted | 122 |
| [#366](https://github.com/ChristianV997/NeuroTopology-Sim/pull/366) | Bound C2–C3 PITNN .vhdr/.vmrk sidecar fetches | `3f3fe85933` → `d74f6ad2c0` | yes | UNSTABLE / True | no_reviews (0 approvals) | fail | unknown | draft | 2 |
| [#367](https://github.com/ChristianV997/NeuroTopology-Sim/pull/367) | fix(streaming): fail-closed C1 — no unbounded S3 download_file | `3f3fe85933` → `864788e897` | yes | UNSTABLE / True | no_reviews (0 approvals) | fail | unknown | draft | 5 |
| [#368](https://github.com/ChristianV997/NeuroTopology-Sim/pull/368) | Harden bounded DANDI/NWB ingestion (fail-closed) | `3f3fe85933` → `fde059629e` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 7 |
| [#369](https://github.com/ChristianV997/NeuroTopology-Sim/pull/369) | Add provenance-preserving metadata-first BIDS adapter | `3f3fe85933` → `2796bf8cf5` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 15 |
| [#370](https://github.com/ChristianV997/NeuroTopology-Sim/pull/370) | Batch 2: release-readiness security harness | `3f3fe85933` → `7e1d7c09f1` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 24 |
| [#371](https://github.com/ChristianV997/NeuroTopology-Sim/pull/371) | feat(benchmarks): Batch-2 pipeline performance suite (synthetic, local-only) | `3f3fe85933` → `2c69429b58` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 18 |
| [#372](https://github.com/ChristianV997/NeuroTopology-Sim/pull/372) | feat(awareness-studio): gate orchestrator outputs by explicit evidence state | `3f3fe85933` → `fb8c9291d0` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#373](https://github.com/ChristianV997/NeuroTopology-Sim/pull/373) | feat(level_t): prevent silent zero imputation and enforce cohort missingness gates | `3f3fe85933` → `56890f373e` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 4 |
| [#374](https://github.com/ChristianV997/NeuroTopology-Sim/pull/374) | feat(dual_engine): deterministic structure-sensitive fusion validation and null models | `3f3fe85933` → `9037957275` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 4 |
| [#375](https://github.com/ChristianV997/NeuroTopology-Sim/pull/375) | Batch 3: provenance-rich literature and public-source mining package | `3f3fe85933` → `69fb8af983` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#376](https://github.com/ChristianV997/NeuroTopology-Sim/pull/376) | Add Batch 3 adversarial falsification matrix | `3f3fe85933` → `989c483bbb` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#377](https://github.com/ChristianV997/NeuroTopology-Sim/pull/377) | Higher-order runtime streaming invariance contracts | `3f3fe85933` → `5f5fa72215` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#378](https://github.com/ChristianV997/NeuroTopology-Sim/pull/378) | feat(adapters): fail-closed MNE CSD wrapper with provenance (Batch 2 / Agent C) | `3f3fe85933` → `369af1a575` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 14 |
| [#379](https://github.com/ChristianV997/NeuroTopology-Sim/pull/379) | Add offline MOABB metadata-to-protocol conformance validator | `3f3fe85933` → `9a94d89b63` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 15 |
| [#380](https://github.com/ChristianV997/NeuroTopology-Sim/pull/380) | feat(adapters): in-memory MNE canonical signal-block contract (Batch 2 / Agent A) | `3f3fe85933` → `93c3447bf3` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#381](https://github.com/ChristianV997/NeuroTopology-Sim/pull/381) | Add Batch 3 offline integration fixture runner | `3f3fe85933` → `d88998584b` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 18 |
| [#382](https://github.com/ChristianV997/NeuroTopology-Sim/pull/382) | test: offline source-mining evidence boundary contracts | `3f3fe85933` → `b54951ce23` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 2 |
| [#383](https://github.com/ChristianV997/NeuroTopology-Sim/pull/383) | Add offline research-plan rubric evaluation harness | `3f3fe85933` → `7f825d2cf8` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 31 |
| [#384](https://github.com/ChristianV997/NeuroTopology-Sim/pull/384) | feat(measurement): add two-layer measurement/hypothesis mapping validator | `19c3203573` → `56ef76a7dd` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 22 |
| [#385](https://github.com/ChristianV997/NeuroTopology-Sim/pull/385) | feat(experimental): simplicial phase cochains and weighted Hodge decomposition reference | `3f3fe85933` → `f4b0c0430a` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 11 |
| [#386](https://github.com/ChristianV997/NeuroTopology-Sim/pull/386) | Batch 1 (claude-d): OSS adoption gates and candidate compatibility review | `19c3203573` → `5211ef81ba` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 6 |
| [#387](https://github.com/ChristianV997/NeuroTopology-Sim/pull/387) | feat(integration): offline synthetic pipeline replay and structural conformance harness | `3f3fe85933` → `930b63b1e3` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 10 |
| [#388](https://github.com/ChristianV997/NeuroTopology-Sim/pull/388) | feat(dual_engine): synthetic EEG forward-model contract and verification fixture | `3f3fe85933` → `b19eeb2931` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 4 |
| [#389](https://github.com/ChristianV997/NeuroTopology-Sim/pull/389) | feat(tda): semantic conformance harness for topology backends (Batch 2 / Agent A) | `3f3fe85933` → `3c363231a5` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 14 |
| [#390](https://github.com/ChristianV997/NeuroTopology-Sim/pull/390) | Batch 3: add advisory report-language checker | `19c3203573` → `53cfbea94e` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#391](https://github.com/ChristianV997/NeuroTopology-Sim/pull/391) | Safe bounded public-repository source packs | `19c3203573` → `ffd24dbc9f` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 6 |
| [#392](https://github.com/ChristianV997/NeuroTopology-Sim/pull/392) | Batch 3: read-only provenance join auditor | `19c3203573` → `5e38aa2334` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#393](https://github.com/ChristianV997/NeuroTopology-Sim/pull/393) | Batch 3: theory-to-measurement review (Grok Chat A) | `3f3fe85933` → `5634a707db` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#394](https://github.com/ChristianV997/NeuroTopology-Sim/pull/394) | Add Batch 3 cross-dataset replication feasibility package | `3f3fe85933` → `82a4dacb87` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#395](https://github.com/ChristianV997/NeuroTopology-Sim/pull/395) | feat(ds005620): reconcile metadata provenance in evidence packet | `3f3fe85933` → `2f70dd9bd0` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 8 |
| [#396](https://github.com/ChristianV997/NeuroTopology-Sim/pull/396) | Add independent Round-6 Hodge decomposition numerical audit | `3f3fe85933` → `01271b0d99` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 12 |
| [#397](https://github.com/ChristianV997/NeuroTopology-Sim/pull/397) | audit(batch2): independent Round 6 finite chain-complex oracle (HOLD) | `3f3fe85933` → `188c8246d9` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 14 |
| [#398](https://github.com/ChristianV997/NeuroTopology-Sim/pull/398) | Batch 2: synthetic MV-FPR / MV-IAAFT surrogate audit (HOLD) | `3f3fe85933` → `095349199b` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 13 |
| [#399](https://github.com/ChristianV997/NeuroTopology-Sim/pull/399) | feat(audits): independent Round 6 winding/charge discrete-identity oracle (Batch 2 / Agent A) | `3f3fe85933` → `c1dd4780e7` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 10 |
| [#400](https://github.com/ChristianV997/NeuroTopology-Sim/pull/400) | test: add independent DMD EP2 matrix-log oracle | `3f3fe85933` → `2588bd2810` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 2 |
| [#401](https://github.com/ChristianV997/NeuroTopology-Sim/pull/401) | feat(bids): synthetic-only inventory audit and payload-checksum boundary | `19c3203573` → `635b2f7d28` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 28 |
| [#402](https://github.com/ChristianV997/NeuroTopology-Sim/pull/402) | Add independent NumPy reference audit for MNE CSD constants and operator | `3f3fe85933` → `c339e89662` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 15 |
| [#403](https://github.com/ChristianV997/NeuroTopology-Sim/pull/403) | feat(calibration): audit and calibration harness for Round 6 phase-uncertainty estimator (Batch 2 / Agent A) | `3f3fe85933` → `42f8f9ccdb` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 10 |
| [#404](https://github.com/ChristianV997/NeuroTopology-Sim/pull/404) | docs: independent Batch 3 provenance firewall audit | `19c3203573` → `5c2c58f1a8` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 1 |
| [#406](https://github.com/ChristianV997/NeuroTopology-Sim/pull/406) | Batch 1: source-backed OSS compatibility audit (HOLD / SYNTHETIC_ONLY) | `19c3203573` → `c67d2c445b` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#407](https://github.com/ChristianV997/NeuroTopology-Sim/pull/407) | audit(statistics): Round 6 train/test whitening audit, leakage invariants, and SPD disclosure | `3f3fe85933` → `f0494445dc` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 11 |
| [#408](https://github.com/ChristianV997/NeuroTopology-Sim/pull/408) | feat(sim): reproducible synthetic nuisance-scenario factory for operating-characteristic sweeps | `3f3fe85933` → `6ec0153e6e` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 14 |
| [#409](https://github.com/ChristianV997/NeuroTopology-Sim/pull/409) | audit: independent four-shell spherical BVP oracle | `19c3203573` → `2ce74f5e24` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 4 |
| [#410](https://github.com/ChristianV997/NeuroTopology-Sim/pull/410) | audit: verify Round 6 finite-jitter triangulation claims | `3f3fe85933` → `45090a89a9` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 3 |
| [#411](https://github.com/ChristianV997/NeuroTopology-Sim/pull/411) | Add Batch 3 EEG replication metadata audit | `3f3fe85933` → `8598a87f2b` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#412](https://github.com/ChristianV997/NeuroTopology-Sim/pull/412) | Batch 3: Round 6 claim audit (Grok Chat A) | `3f3fe85933` → `c483aa3ea6` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 1 |
| [#413](https://github.com/ChristianV997/NeuroTopology-Sim/pull/413) | feat(topology): oriented integer phase-winding production module (Batch 2 / Cursor B) | `19c3203573` → `3328dd15a9` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#414](https://github.com/ChristianV997/NeuroTopology-Sim/pull/414) | feat(experimental): NumPy spherical-spline CSD transform (MNE 1.13.2 pin) | `19c3203573` → `24ad946c1c` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#415](https://github.com/ChristianV997/NeuroTopology-Sim/pull/415) | feat(dynamics): HOLD/synthetic exact DMD + EP/Crouzeix diagnostics (Batch 2 / Agent D) | `19c3203573` → `d3072e8963` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 6 |
| [#416](https://github.com/ChristianV997/NeuroTopology-Sim/pull/416) | feat(geometry): robust 2D planar triangulation with exact-sign predicates (Batch 2 / Agent A) | `19c3203573` → `04d5af7321` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#417](https://github.com/ChristianV997/NeuroTopology-Sim/pull/417) | Batch 1: surrogate-null contract and stdlib generators (synthetic, HOLD) | `19c3203573` → `25c5afeac3` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 12 |
| [#418](https://github.com/ChristianV997/NeuroTopology-Sim/pull/418) | feat(physics): add experimental four-shell EEG forward model (HOLD / SYNTHETIC_ONLY) | `19c3203573` → `e316933282` | yes | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | draft | 4 |
| [#419](https://github.com/ChristianV997/NeuroTopology-Sim/pull/419) | test(experimental): independent spherical CSD parity suite and MNE 1.13.2 reference fixtures | `19c3203573` → `fa8f0f7c1f` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 2 |
| [#420](https://github.com/ChristianV997/NeuroTopology-Sim/pull/420) | test(dynamics): independent DMD regression suite and EP2/Crouzeix oracles (Batch 2 / Agent D) | `19c3203573` → `1b0500dbef` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 2 |
| [#421](https://github.com/ChristianV997/NeuroTopology-Sim/pull/421) | audit(geometry): independent adversarial test suite for planar triangulation and embedding validity (Batch 2 / Agent A) | `19c3203573` → `14c218750b` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 13 |
| [#422](https://github.com/ChristianV997/NeuroTopology-Sim/pull/422) | fix(awareness-studio): declare registered execution memory dependency | `19c3203573` → `93c69ffea1` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 2 |
| [#423](https://github.com/ChristianV997/NeuroTopology-Sim/pull/423) | feat(topology): production weighted 2D discrete Hodge decomposition (Batch 2 / Antigravity B) | `19c3203573` → `a1efd82252` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 9 |
| [#424](https://github.com/ChristianV997/NeuroTopology-Sim/pull/424) | Hold synthetic grid plan v2 behind class floors and source pins | `19c3203573` → `d688b5ec33` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 3 |
| [#425](https://github.com/ChristianV997/NeuroTopology-Sim/pull/425) | docs(audits): snapshot live PR ownership and CI state | `19c3203573` → `689c4c4655` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 6 |
| [#426](https://github.com/ChristianV997/NeuroTopology-Sim/pull/426) | feat(benchmarks): synthetic operating-characteristics API (HOLD / SYNTHETIC_ONLY) | `19c3203573` → `55115149c7` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 5 |
| [#427](https://github.com/ChristianV997/NeuroTopology-Sim/pull/427) | Add independent synthetic ROC calibration-split contract tests | `19c3203573` → `e64304087d` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 1 |
| [#428](https://github.com/ChristianV997/NeuroTopology-Sim/pull/428) | fix(docker): repair container test build contexts | `93c69ffea1` → `24dfd88618` | no | CLEAN / True | automated_comment_only (0 approvals) | pass | unknown | blocked | 3 |
| [#429](https://github.com/ChristianV997/NeuroTopology-Sim/pull/429) | CI: run tests/surrogate_nulls in core-tests (stacked on #417) | `25c5afeac3` → `18ba01d6f8` | no | UNSTABLE / True | automated_comment_only (0 approvals) | fail | unknown | blocked | 1 |

## CI failure classifications

- **awareness_registered_execution** — `confirmed_on_main_and_sampled_pr_heads`. Current main Required Checks and sampled PR logs show the same three registered-execution tests failing. This does not establish a shared production cause.
- **pr422_docker_workflow** — `confirmed_only_on_pr_422_head_then_passed_on_stacked_pr_428`. PR #422 logs show pip cache purge failure with cache disabled and Awareness image collection errors. Later PR #428 Docker CPU/base and Awareness image jobs passed; production-root image remained manual/skipped.
- **round6_candidate_test_discovery** — `confirmed_workflow_coverage_gap_on_main_partial_candidate_execution_on_pr_429`. Main does not invoke the PR #425 helper. PR #425 helper returns NOT_APPLICABLE with no lane. PR #429 independently executes surrogate_nulls in core-tests but does not validate the PR #425 helper.

## Caveats

- This dated snapshot is not a live source of truth; refresh GitHub metadata before any merge.
- Classic branch protection returned HTTP 404. Effective rules were returned but contained no required-status-check rule; other/organization gates remain unknown.
- Review submissions do not expose unresolved inline-thread state; it remains unknown.
- Exact changed-path overlap is an ownership collision only and does not establish a Git conflict.
- Local candidate probes used exact live heads and stopped before collection because bundled Python lacks pytest and pytest-timeout. No dependencies were installed; zero candidate tests ran locally.
- PR #429 hosted core-tests executed tests/surrogate_nulls within 16 isolated file batches on a branch stacked on #417; this did not exercise PR #425 helper.
- PR #425 hosted helper run was on the pre-refresh head and returned NOT_APPLICABLE because no candidate implementation/test paths changed.
- No participant data, EEG data, ds005620 content, or external datasets were accessed. Posture remains HOLD / SYNTHETIC_ONLY.

## Reproducible candidate probe

The hosted PR #425 run cannot validate candidate suites when the candidate implementation and its direct adversarial tests are absent from that PR diff. The smallest safe probe is a disposable worktree containing the exact PR #425 CI/helper head plus only one implementation/test pair (or the listed two-PR lane pair); do not merge these probe commits. The current exact refs and prior probe results are recorded under `main_ci.round6_candidate_discovery.local_candidate_probe.candidate_probes` in the JSON snapshot.

Using the full SHAs recorded there, fetch each lane's candidate PR head into a unique local ref, then:

```sh
git worktree add --detach <probe-root> <PR425_HEAD_SHA>
git -C <probe-root> merge --no-edit --no-ff <IMPLEMENTATION_HEAD_SHA>
git -C <probe-root> merge --no-edit --no-ff <ADVERSARIAL_TEST_HEAD_SHA>
git -C <probe-root> rev-parse HEAD
python <probe-root>/.github/workflows/round6_experimental_tests.py \
  --root <probe-root> --base 19c3203573082f8bc41f7da226b52dc20a49fdb0 \
  --head <COMBINED_HEAD_SHA> --report <probe-root>/round6-candidate-report.json
```

Repeat in a fresh disposable worktree for each listed lane; for a single-PR lane use its candidate head and omit the second merge. The runner must have the repository's declared pytest and `pytest-timeout` dependencies already available. If not, report the helper's pre-collection failure as **BLOCKED**; do not install dependencies in this procedure, reinterpret no collection as a pass, or claim hosted execution. A complete probe requires non-empty test collection, zero skips/failures/timeouts, valid runner telemetry, and valid JUnit output. The current local attempts did not meet that condition because the bundled runtime lacked pytest and pytest-timeout.

## Evidence links

- [git](https://github.com/ChristianV997/NeuroTopology-Sim/commit/19c3203573082f8bc41f7da226b52dc20a49fdb0) — origin/main verified at 2026-10-19T01:20:09Z.
- [github_api](https://api.github.com/repos/ChristianV997/NeuroTopology-Sim/pulls?state=open&per_page=100) — All 64 open PR heads/bases/status/reviews and paginated changed-path lists retrieved at 2026-10-19T01:20:09Z.
- [github_api](https://api.github.com/repos/ChristianV997/NeuroTopology-Sim/rules/branches/main) — Effective rules list deletion, non_fast_forward, and copilot_code_review; no required status-check rule returned.
- [github_api](https://api.github.com/repos/ChristianV997/NeuroTopology-Sim/branches/main/protection) — Classic branch-protection endpoint returned HTTP 404; mark gate state unknown.
- [github_actions](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39001665754) — Current-main Required Checks run at verified main SHA; awareness-test failure confirmed in job log.
- [github_actions](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39166611111/job/117790768938) — PR #425 pre-refresh hosted helper log: NOT_APPLICABLE, no candidate lane.
- [github_actions](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39183911375/job/117842224967) — PR #429 core-tests log confirms explicit surrogate_nulls suite execution; separate from PR #425 helper.
- [github](https://github.com/ChristianV997/NeuroTopology-Sim/pull/405) — PR #405 merged as 19c3203573082f8bc41f7da226b52dc20a49fdb0; Wilson interface verified in current main.
