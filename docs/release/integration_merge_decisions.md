# Integration merge decisions

## Run metadata

- Integration branch: `codex/integration-all-open-prs`
- Integration checkout: dedicated clone at `C:\Users\HP\OneDrive\Documentos\GitHub\NeuroTopology-Sim-integration`
- Target repository: `ChristianV997/NeuroTopology-Sim`
- Target base: `origin/main` at `62637a4b9c82c0c258bfc49e28dee1af757b1c25`
- Primary checkout: `C:\Users\HP\OneDrive\Documentos\GitHub\ScienceR-Dsim`
- Primary branch: `agent/aws-preflight-passrole`
- Primary dirty files preserved exactly: `.serena/.gitignore`, `.serena/project.yml` (both untracked)
- The task mirror's `origin` fetch was authentication-blocked; the merger used a fresh clone whose `origin/main` and PR refs were fetched directly from GitHub. No primary files were changed.

## Operating gates

- No force-push, main rewrite, or deletion of unmerged branches.
- No AWS, QPU, cloud, or external dataset execution during integration.
- Synthetic data remains `NOT_SUPPORTED`; invalid data cannot become evidence.
- RSS/AICc/BIC ratios remain proxies, never formal Bayes factors.
- Graph beta-1, spatial winding, and topological charge remain separate metrics.
- Dashboard/API paths must remain solver-free.
- Every accepted logical group gets targeted tests, governance/import checks, secret scanning, dashboard isolation checks, finite-number/schema checks, and an overlap audit.

## Candidate inventory

| Item | Head | Base | Initial decision |
|---|---|---|---|
| PR #206 | `cursor/setup-dev-environment-52dc` | `main` | Review only; draft and CI-invalid, no integration need established. |
| PR #207 | `cursor/pitnn-perf-opt-52dc` | `main` | Review only; draft performance change requires isolated validation. |
| PR #208 | `cursor/disorder-modes-runrecord-sidecar-v1-04d8` | `main` | Review only; draft and outside requested dependency graph. |
| PR #209 | `grok-bot/retrofit-inventory` | `main` | Candidate; offline inventory only, must pass guardrail tests. |
| PR #210 | `claude/ecosystem-integration` | `main` | Candidate after dependency matrix reconciliation. |
| PR #211 | `cursor/streaming-performance-benchmarks` | `main` | Candidate after performance and semantic tests. |
| PR #212 | `codex/interop-signal-contracts` | `main` | Candidate after contract/governance tests. |
| PR #213 | `antigravity/test-isolation-dependency-profiles` | `main` | Candidate foundation; CI/runner overlap with #222. |
| PR #214 | `antigravity/mne-scipy-streaming-eeg` | `main` | Candidate after #212 contract compatibility and EEG tests. |
| PR #215 | `cursor/rss-memory-telemetry` | `cursor/streaming-performance-benchmarks` | Candidate only after #211; stacked. |
| PR #216 | `grok-bot/evidence-bundle-release` | `main` | Do not merge; title and evidence semantics explicitly mark it as release/compiler work requiring final state. |
| PR #217 | `grok/tool-registry-admission` | `main` | Candidate after offline optional-backend review. |
| PR #218 | `claude/integration-reconciliation` | `main` | Candidate after graph changes; read-only governance tooling. |
| PR #219 | `codex/bayes-falsification-hardening` | `main` | Candidate; preferred Bayesian implementation over branch-only overlap. |
| PR #220 | `antigravity/native-signal-adapters` | `codex/interop-signal-contracts` | Candidate only after #212; stacked. |
| PR #221 | `antigravity/legacy-timeout-repair` | `main` | Candidate after targeted Windows/path and timeout regression tests. |
| PR #222 | `codex/ci-root-cause-and-green` | `main` | Candidate only through selective conflict resolution with #213; checks currently invalid. |
| Branch-only | `codex/scientific-falsification-contract` | `main` | Preserve distinct topology-contract additions; replace overlapping Bayesian file with #219. |

## Dependency graph and intended order

1. `codex/scientific-falsification-contract` (retain topology-only additions)
2. PR #219 (authoritative Bayesian/falsification implementation)
3. PR #213 (dependency profiles and baseline isolation)
4. PR #222 (selective CI/runner reconciliation with #213)
5. PR #211, then PR #215 (streaming, then RSS telemetry)
6. PR #212, then PR #220 (signal contracts, then native adapters)
7. PR #214 (EEG streaming adapter; contract compatibility checked)
8. PR #209 and PR #217 (offline inventory and optional-tool admission)
9. PR #221 (legacy repairs)
10. PR #218 (reconciliation tooling against the resulting graph)
11. PR #210 (dependency matrix updated to actual integrated components)
12. PR #216 remains unmerged; final release evidence is generated from the validated integration state.

## Decision log

| Group | Decision | Evidence | Result |
|---|---|---|---|
| Baseline | Use actual GitHub `origin/main` because task-mirror fetch requires unavailable credentials. | Fresh clone resolves `origin/main` to `62637a4`; API PR base OIDs match. | Recorded; primary checkout untouched. |

Additional entries are appended after each logical merge group and final validation.

### 2026-09-06 — falsification contract group

- Merged branch-only `codex/scientific-falsification-contract` as the source of the distinct graph-beta-1 and spatial-winding contract modules and tests.
- Merged PR #219 with an explicit conflict resolution in `sim/pitnn/bayesian_falsification.py`: PR #219 supersedes the branch-only Bayesian implementation because it adds stronger finite-value handling, multiplicity gates, effective-sample checks, explicit proxy/formal separation, and expanded compatibility metadata.
- Validation: `python -m pytest -q tests/science_contracts` passed (12 tests) before the #219 replacement; the combined Bayesian/falsification group is re-run after the merge commit.
- Compatibility repair: retained the #219 BIC-proxy default while restoring legacy `parameter_count`/log fields, added tri-state nested control recognition, differentiated missing versus incomplete empirical provenance, and updated the older branch test to assert the authoritative BIC-proxy contract. No scientific gate was widened.

### 2026-09-06 — CI/dependency profile group

- Merged PR #213 as the dependency-profile and baseline isolation foundation.
- Reconciled PR #222's overlapping files without taking its duplicate implementation wholesale:
  - kept #213's modular dependency profiles, profile-specific CI suites, tested `run_batch`/`run_batches` API, telemetry report schema, network guard, deterministic seeds, and full marker registry;
  - added #222's heavy-test singleton batching, process-group termination, bounded subprocess defaults, explicit pytest-timeout requirement, headless plotting/thread caps, per-batch log directory, continuation after failures/timeouts, and machine-readable `batch_summary.json` compatibility fields;
  - retained #222's workflow hardening in non-overlapping workflow files, while using profile-scoped `requirements-*` installs and no pip cache in the reconciled root CI jobs;
  - included #222's CI isolation documentation and regression tests.
- Validation: 14 runner/isolation tests passed; governance passed; Python compilation passed; all workflow YAML parsed.

### 2026-09-06 — streaming and memory group

- Merged PR #211, then the stacked PR #215 after #211's exact head was present.
- Kept the allocation-reduced PITNN kernel and bounded streaming utilities; added process RSS telemetry without changing solver or signal semantics.
- Validation: performance/streaming suite passed (46 tests after #215), governance passed, and affected modules compiled.

### 2026-09-06 — signal interoperability and EEG group

- Merged PR #212 before stacked PR #220, preserving the contract/adapter ownership boundary and lazy optional dependency behavior.
- Merged PR #214 after the interoperability contract was present; its MNE/SciPy streaming path remains provenance-rich, memory-bounded, and offline by default.
- Validation: 28 interoperability/adapter tests and 39 EEG tests passed; governance and compilation passed. No optional network, MNE download, solver, AWS, or QPU execution was performed.

### 2026-09-06 — integration bridge group

- Merged PR #210 after the dependency graph was present. Its read-only bridge, artifact, quality, and dashboard-isolation surfaces remain solver-free and offline by default.
- Updated the dependency matrix/reconciliation note after merge so the state is not left claiming that #209, #211, #212, #214, or the falsification contract are unavailable.
- Portability repair: the symlink rejection test now skips only when Windows denies symlink creation (`WinError 1314`); the preflight implementation remains tested where symlink support is available.
- Validation: 66 integration tests passed and 1 Windows privilege-limited symlink test skipped; governance and compilation passed.

### 2026-09-06 — inventory, admission, repair, and reconciliation groups

- Merged PR #209 for the offline retrofit inventory, PR #217 for optional
  tool admission, PR #221 for legacy timeout/path repairs, and PR #218 for
  read-only integration reconciliation tooling.
- The exact branch named `grok/tool-admission-research` was not fetched or
  reconstructed; PR #217 is the actual available tool-registry branch.
- Validation: 67 inventory tests, 19 tooling tests, 22 legacy-repair tests,
  and 78 reconciliation tests passed; governance, compilation, and overlap
  checks passed. No credentials, sockets, package installation, or external
  datasets were used by these validations.

### 2026-09-06 — documentation and artifact-state reconciliation

- Updated `docs/integration_acceptance.md` and
  `configs/integration/dependency_matrix.yaml` from PR #210's pre-merge
  scaffold narrative to the actual integrated branch state.
- Corrected the consumed `tools.streaming` symbol list to the public exports
  `bounded_stream`, `iter_chunks`, and `iter_windows`.
- The synthetic bridge smoke produced exactly the four documented artifacts;
  both `quality_report.json.status` and `RunRecord.json.verdict` were
  `NOT_SUPPORTED`, all numeric fields were finite, and the manifest schema was
  `NTS.IntegrationArtifactManifest.v1`.

### 2026-09-06 — final validation and handoff

- Targeted final validation passed: integration 66 passed/1 platform-limited
  skip; reconciliation 78 passed; scientific/performance/interop/EEG/tooling/
  inventory/legacy/isolation group 242 passed; governance, compileall, YAML,
  diff-check, secret scan, and synthetic artifact checks passed.
- The full isolated runner completed all 401 discovered files in 73 batches:
  63 batches passed, 6 had failures, and 4 timed out; exit code 124. The
  failure log is external to the checkout at
  `%TEMP%\\nts-isolated-final-20260906`.
- The six non-timeout classifications are: an unchanged benchmark absolute
  path assertion; missing optional `torch` during cross-modal collection;
  one transient job-queue output-file permission failure (the node passed on
  direct rerun); a pre-existing Windows path-separator expectation in the
  MNE-BIDS fixture; Windows symlink privilege `WinError 1314`; and one
  optional `cripser`-only file with all tests skipped. The four timeouts are
  bounded workers for `test_t_real_cli_stats_wiring.py`, the mixed
  reconciliation/interop batch, the PITNN/pipeline batch, and the mixed
  research/record batch. None of these failure test files is changed by the
  accepted integration PRs.
- GitHub required checks for representative accepted PRs remain red and jobs
  terminate before steps/logs are available; this is recorded as CI
  infrastructure unavailable, not as a local scientific failure. No GitHub
  Actions billing entitlement was required or exercised, and no AWS/QPU/cloud
  execution or credentialed operation was attempted.

### 2026-09-06 — live post-wave PR audit and extension

- The live GitHub inventory contained PRs #223–#238 in addition to the earlier
  inventory. The integration branch was extended only after fetching and
  inspecting each current head/base, changed-file list, draft state, body, and
  check status.
- Accepted additive groups, merged in dependency order:
  - #223 capability snapshot sidecar after #217;
  - #224 adaptive streaming after #211/#215, then #232 checkpoint/replay;
  - #226 consumer-safe Bayesian semantics after #219, then #234 artifact
    consumer migration;
  - #228 merge-gate policy after reconciliation;
  - #229 dataset provenance;
  - #230 performance-regression policy;
  - #227 CI install reliability after #213/#222, with six workflow conflicts
    manually reconciled in favor of CPU/base profiles, bounded pip temp space,
    diagnostics, and the existing core/EEG/ML test jobs;
  - #231 CI evidence preflight;
  - #233 interoperability conformance;
  - #235 paired-cohort manifest/readiness;
  - #238 optional TDA adapters;
  - #225 release-state classification, superseding #216's release inventory.
- PR #237 remains intentionally excluded because its own body says “do not
  merge”; it is an inventory input, not production or release authority.
- PRs #206, #207, and #208 remain unmerged for draft/review-only or
  out-of-graph scope. The branch-only `grok/tool-admission-research` ref was
  not recreated. No duplicate Bayesian implementation was retained: #219 is
  authoritative, with #226 and #234 layered at consumer boundaries.
- Validation of the extension: CI/governance/tooling/provenance group `93
  passed`; streaming/interop/scientific/cohort/TDA/integration group `344
  passed, 2 skipped`; YAML parsing passed for 10 files. The skips are explicit
  optional/platform classifications, not converted failures.
- GitHub checks for every newly inspected PR and the integration PR fail before
  steps/logs are available. No CI success is claimed; the branch remains open
  for review and infrastructure diagnosis.

### 2026-09-06 — post-run classification and focused repairs

- The mandated isolated run discovered 415 files in 75 bounded batches and
  returned `64 passed, 8 failed, 3 timed out` with exit code 124. These results
  remain recorded as local evidence; the full run is not represented as green.
- Fixed genuine compatibility defects at integration boundaries: propagated
  explicit source mode/provenance and declared single-test multiplicity in the
  empirical and MEG callers; made valid proxy comparisons explicitly
  `NOT_SUPPORTED`; made benchmark absolute-path rejection portable across
  POSIX and Windows path grammars; and serialized BIDS artifact paths with
  forward slashes.
- Verified repairs with `32 passed`, including empirical, MEG, falsification
  semantics, benchmark, batch-runner, and MNE-BIDS tests. The broad validation
  group remains `344 passed, 2 skipped`; the CI/governance/tooling/provenance
  group remains `93 passed`.
- The remaining optional/platform cases are explicitly classified: absent
  `torch`, absent `cripser`, and unavailable Windows symlink privilege
  (`WinError 1314`). Only the privilege-specific symlink case is skipped; no
  real assertion failure is converted into a skip. Remaining bounded timeout
  groups are unresolved and keep the scientific/release status inconclusive.
- GitHub Actions checks still terminate before steps or logs for the
  integration PR and inspected source PRs. This is classified as
  infrastructure/billing blocked; no CI success is claimed, no merge is
  forced, and PR #236 remains open.

### 2026-09-07 — requested release-validation rerun

- Requested interoperability, provenance, cohort-manifest/statistics,
  topology-adapter, falsification, CI diagnostics, merge-gate, release-report,
  performance-policy, checkpoint/replay, platform, dashboard-isolation,
  no-secret, and finite-JSON checks were executed.
- The first release-report run exposed two real defects: Windows `cp1252`
  stdout could not emit a Unicode report symbol, and a release test asserted
  the obsolete 19-entry inventory while the current merger snapshot contains
  27 contributions. Both were repaired without skips.
- The requested validation set completed with `339 passed, 2 skipped`, plus
  the separately recorded `142 passed, 1 skipped`
  platform/performance/finite-JSON set. The two requested-set skips were
  optional `ripser` capability checks; the platform-set skip was unavailable
  Windows symlink privilege. The release suite then completed with `55
  passed`; no assertion failure was converted to a skip.

### 2026-09-07 — Batch 2 live audit and integration decisions

- Live PR #236 was verified open at `af3ac584419148ddcfc57cb565c416eba6328725`;
  `origin/main` was `62aa8fee786abf916ab0aa2b7e7b91c570fee119`. The latter is
  an ancestor of the integration branch, so no main-sync merge was needed.
- Live GitHub state supersedes old handoffs: #209–#221 are merged into main,
  including #216. Therefore #216 is not classified as superseded by #225;
  #225 is an open, explicit-do-not-merge inventory duplicate whose docs were
  not reintroduced as a second release authority.
- #249 and #257 have the same five-file effective CI repair. #257’s newer
  head (`16e7d4c0…`) was selected; #249 (`49be8441…`) was excluded as a
  duplicate. #222/#227 remain the earlier CI lineage and are not claimed as
  main-merged.
- #254 was merged into the integration branch with a manual conflict
  resolution. Its isolated process groups, graceful/forced tree termination,
  and concurrent stdout/stderr draining were retained; existing heavy-test
  singleton scheduling, compatibility helpers, and report-directory output
  were preserved. A real report-initialization regression was found and fixed.
- #240, #246, #247, #248, #250, #251, #258, #259, #260, #261, #263, #264,
  and #266 were additive and passed focused local suites. #262 was excluded
  because its effective implementation duplicates #246. #239, #241, #243,
  #244, #252, #253, #255, #256, #267, #268, and #269 remain review-only or
  unintegrated; no draft was silently treated as validated release code.
- #263 exposed four real stacked-diff fixture failures. The fixture was
  repaired by adding the missing dependent branch and remote ref; the repair
  is included in the integration branch and was not converted to a skip.
- Mandatory conflict decisions remain explicit: #214 versus #220 keeps the
  lazy native-adapter layer over the streaming contract; #211→#215→#224→#232
  remains the streaming dependency order; #219 remains authoritative over
  branch-only Bayesian work; #229 remains the provenance contract over typed
  readers (#240); #238 is the adapter base with #250 hardening; #218 remains
  the reconciliation source for #255 state-lock work; #230 remains the
  performance policy with #258 as evidence normalization; and #241 is not a
  substitute for #254’s isolated test-runner repair.
- The branch contains 283 effective changed paths relative to `origin/main`.
  No datasets, binary trajectories, credentials, or generated plots were
  added. The primary dirty checkout was not modified.

### 2026-09-07 — final mandated local run

- The exact required command
  `python scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120`
  completed `459 files / 81 batches`: `73 passed, 4 failed, 4 timed out`,
  exit code `1`. This is preserved as non-green local evidence.
- The isolated runner explicitly surfaced the absent-`torch` collection
  failure in `tests/test_cross_modal_fusion.py` and the absent-`cripser`
  no-tests-collected result for `tests/test_topology.py`; neither was
  converted into a skip or pass. Remaining failures/timeouts remain unresolved
  execution blockers.
- PR #236 was pushed at `c8b96eb` and remains open. GitHub required checks
  still fail before job steps with the billing/runner infrastructure condition;
  main was not merged.

### 2026-09-07 — consolidated open-PR pass

- The live open-PR set was re-fetched and reassessed. Distinct useful work
  integrated into this lane includes #206, #207, #208, #225, #239, #241,
  #242, #243, #244, #248, #252, #253, #255, #262, #264, and #267–#283,
  in addition to the previously integrated #223–#240 and #245–#261 lineage.
- #279's export conflict was resolved by retaining both triadic-connectivity
  and directed-hypergraph APIs with non-colliding schema names. The resulting
  higher-order suite passed.
- Local validation found and repaired three portability defects: Windows UTF-8
  release-blocker output, Windows benchmark crash probes, and the runner
  acceptance harness's unsupported pytest passthrough/too-short flood timeout.
  The process-isolated benchmark child also needed to add the repository root
  to `sys.path` when launched by absolute path. Its focused suite is now
  `15 passed, 1 skipped`; cohort-statistics validation is `19 passed`.
- #262 was retained as a real cohort-statistics refinement and merged with its
  edge-case tests. #222, #249, and #271 are broad aggregate CI rewrites whose
  deletions/replacements are already superseded by the narrower reconciled
  CI lineage; they are not merged wholesale. #237 and #256 explicitly say
  do-not-merge and remain audit inputs only. #265 introduces live AWS/daemon/
  autonomous orchestration paths and is excluded from the scientific release
  lane.
