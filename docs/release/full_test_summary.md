# Full test summary

## Targeted validation

- CI/governance/tooling/provenance: `93 passed`.
- Repaired scientific, portability, benchmark, and batch-runner set: `32
  passed`.
- Streaming, interop, scientific semantics, cohort, TDA, integration, and
  reconciliation: `344 passed, 2 skipped`.
- YAML/config parse: `10 files passed`.
- Earlier integration evidence: `66 passed, 1 Windows symlink-privilege skip`,
  `78 reconciliation passed`, and `242 targeted regressions passed`.

The two skips are explicit environment classifications: missing optional
`cripser` for the topology-only test file and unavailable Windows symlink
creation privilege (`WinError 1314`). No assertion failure was converted into
a skip.

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
