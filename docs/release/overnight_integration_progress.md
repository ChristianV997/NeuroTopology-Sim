# Overnight integration progress

## Verified baseline

GitHub REST confirmed main at `ad1d480828b23bf9daf7272d8747302dcca138b7`.
Work is isolated on `codex/overnight-execution-integration` in
`C:/Users/HP/AppData/Local/Temp/nts-goal-audit`. The primary feature checkout
contains pre-existing tracked deletions and untracked data and was not edited.

The baseline cross-layer selection passed 117 tests. Awareness Studio's own
research-cycle selection passed 13 tests using its subproject configuration.
Root pytest deliberately excludes Awareness Studio; that is documented package
isolation, not a missing installation defect requiring a new bootstrap system.

## Changes and integrated candidates

- Commit `16dfbcb`: corrected canonical runner resume. Cached PASS now requires
  matching computation identity, current command authorization, valid outputs,
  and eligible dependencies. Local input files are hashed incrementally.
  Dependencies that execute again invalidate descendant reuse. Old manifests
  lacking the identity rerun conservatively.
- PR #353, source `39fc8cf`: simulation bridge, locally cherry-picked as `ea27d2b`.
- PR #352, source `3cd8468`: literature bridge, locally cherry-picked as `5f97ca7`.
- PR #356, source `e3dc173`: preflight, locally cherry-picked as `055490f`.

These are local integration candidates. No source PR was merged or closed.

## Validation

- Runner including new resume regressions: 25 passed.
- Runner, artifact extraction, and release evaluator: 55 passed.
- Combined preflight, simulation bridge, literature bridge, and research-cycle
  tests: 130 passed. For this explicit cross-project selection, PYTHONPATH
  contained the repository root and `apps/awareness_studio/src`.
- Governance: all four specifications passed after the resume change.
- Diff whitespace check passed after the resume change.

Test counts overlap and must not be summed as unique coverage. Bridge tests
execute local synthetic fixture writers; they are not numerical solver or
empirical dataset validation. Hosted CI has not been validated in this run.

## Outstanding integration work

Further update: registered execution now projects verified run/artifact/
validation nodes through the canonical graph builder and invokes the canonical
release evaluator, persisting both outputs in ledger events. The evaluator now
returns EVIDENCE_INCOMPLETE when any required check remains unknown. Previously
unknown resource, network, or comparability checks could fall through to ready.
Targeted regression coverage checks these missing fields and verifies that
synthetic execution does not invent empirical provenance or supported claims.

Update: `Orchestrator.run_registered` now composes canonical preflight,
explicit request binding, the simulation bridge, actual executor outcomes,
artifact verification, and ledger events. Seven new tests exercise the path,
including a real subprocess arithmetic fixture. The combined relevant suites
pass 192 tests; governance and compilation also pass. The legacy `run()` stages
below remain templates; literature-to-experiment linkage, neuroscience solver
integration, graph projection, and release evaluation are still outstanding.
See `docs/awareness_studio/registered_execution.md` for the new API and limits.

1. Wire preflight and the simulation bridge into the existing orchestrator.
   Its execute/validate stages still report NOT_IMPLEMENTED in live mode;
   its hypothesis and experiment generation remain templates. Merely importing
   the bridges does not complete the research loop.
2. Bind execution requests to the actual admitted plan and record preflight,
   execution, independently verified artifacts, and review outcomes in the
   canonical ledger. Preserve planning defaults and explicit authorization.
3. Add a bounded numerical synthetic workload using existing solver APIs and
   exercise the complete path with failure, timeout, resume, and tampering cases.
4. Review runtime boundaries before exposing broad execution: Python socket
   guarding is not an operating-system network sandbox; disk quota is currently
   checked after process exit; output streams spool before truncation; child
   cleanup and dependency content provenance need stronger acceptance evidence.
5. Review PR #346 with policy registration #354 together, then P0 migration
   #355 and legacy test repair #350. No repository-wide compliance claim is
   justified by scoped static scanner results.
6. Validate release/report/evidence graph consumers against actual produced
   artifacts, then run the required bounded full-suite profiles and inspect
   hosted CI status. No release or scientific completion claim is justified yet.

Remote references were fetched with a command-scoped Windows GitHub CLI
credential helper because the repository's existing helper points at an invalid
WSL path. Global and repository credential configuration was not changed.

Resume identity relies on an honestly supplied code revision and explicit
environment/input declarations. It does not independently resolve remote input
identifiers, hash an entire installed dependency environment, or establish
scientific provenance. Remaining work must preserve those limits in reports.
