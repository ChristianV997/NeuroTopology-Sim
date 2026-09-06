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
