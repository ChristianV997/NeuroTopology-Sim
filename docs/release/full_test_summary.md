# Full test summary

## Targeted validation

- CI/governance/tooling/provenance: `93 passed`.
- Repaired scientific, portability, benchmark, and batch-runner set: `32
  passed`.
- Streaming, interop, scientific semantics, cohort, TDA, integration, and
  reconciliation: `344 passed, 2 skipped`.
- Release-report rerun: `55 passed` after repairing Windows UTF-8
  stdout handling and updating the stale inventory-size assertion to the
  current 27-entry merger snapshot.
- YAML/config parse: `10 files passed`.
- Earlier integration evidence: `66 passed, 1 Windows symlink-privilege skip`,
  `78 reconciliation passed`, and `242 targeted regressions passed`.

The skips are explicit environment classifications: missing optional
`cripser`/`ripser` capabilities and unavailable Windows symlink creation
privilege (`WinError 1314`). No assertion failure was converted into a skip.

## Full isolated runner

Command:

`python scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120 --report-dir %TEMP%\\nts-integration-final-20260906`

- Discovery: 415 test files in 75 bounded batches.
- Result: `64 passed, 8 failed, 3 timed out`; exit code `124`.
- The full run was executed before the focused source/test repairs below; its
  failures remain preserved rather than retroactively relabelled as passes.

Explicit classifications from the isolated report:

- Optional dependency: `tests/test_cross_modal_fusion.py` could not collect
  because `torch` is absent; `tests/test_topology.py` had only the optional
  `cripser` path skipped and exited with no collected tests.
- Platform capability: symlink escape test hit Windows `WinError 1314`.
- Baseline portability: benchmark absolute POSIX path was not recognized on a
  Windows host; fixed with host-independent path grammar checks and verified.
- Baseline portability: MNE-BIDS artifact path used Windows separators; fixed
  at the serialization boundary and verified.
- Scientific compatibility: empirical/MEG callers failed to propagate source
  mode/provenance into the hardened gate; fixed and verified. Synthetic and
  proxy results remain `NOT_SUPPORTED`, while invalid empirical inputs remain
  `INCONCLUSIVE`.
- Batch-runner failure: the focused `max_jobs` test passed on rerun.
- Timeouts: bounded heavy suites remain in `test_t_real_cli_stats_wiring.py`,
  the reconciliation group, the PITNN/pipeline group, and one mixed research
  group. They are unresolved execution-time blockers, not skips.

The complete batch-level evidence is retained at
`%TEMP%\\nts-integration-final-20260906\\batch_summary.json` on the validation
host. CI remains separately infrastructure-blocked; local evidence does not
claim CI success.

## Batch 2 focused validation

- Provenance/platform/cohort statistics: `48 passed`.
- Cohort topology/TDA: `41 passed`.
- Research/release artifacts: `117 passed`.
- Interop/admission/CI: `61 passed, 1 skipped`; the skip is an optional
  capability check.
- Null calibration/performance evidence: `31 passed`.
- Reconciliation after #263 initially reported four real stacked-fixture
  failures; the fixture was repaired and the focused stacked-diff cases passed.

These focused results do not replace the non-green full isolated run and do
not imply GitHub CI success.

## Final mandated isolated run — 2026-09-07

Exact command:

`python scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120`

- Discovery: `459` files in `81` bounded fresh-process batches.
- Result: `73 passed, 4 failed, 4 timed out`; exit code `1`; duration about
  `2970s`.
- Batch 36 (`tests/test_cross_modal_fusion.py`) is an absent-`torch` optional
  dependency collection failure. Batch 74 (`tests/test_topology.py`) is the
  absent-`cripser` no-tests-collected condition. Both remain non-green runner
  outcomes and are classified explicitly; neither is represented as a pass.
- The remaining ordinary failure and timeout batches remain unresolved local
  execution evidence. They are not scientific evidence, and the run is not a
  release pass.
