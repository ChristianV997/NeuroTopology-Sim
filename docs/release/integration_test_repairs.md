# Integration test repairs

## Scope and baseline

This note records fresh, isolated reproductions from `be277ecdac301d49dca27ef9612ebe6c560245ad` in the dedicated
`codex/integration-regression-repair` worktree. The primary checkout and
`codex/integration-all-open-prs` were not modified.

The historical integration evidence reports 401 files, 63 passing batches, 6
failed batches, and 4 timed-out batches. A fresh discovery in this checkout
currently finds 422 test files and 76 batches, so that historical aggregate is
not silently presented as a new full-suite result. The broad replay was stopped
after reproducing early bounded timeouts; suspect groups were then replayed as
fresh subprocesses with explicit hard limits.

Every result below records the process-level result from the isolated runner.
Peak memory is the runner's process-tree RSS when the worker completed; a
timed-out worker has no reliable final RSS sample and is recorded as `null`.

## Reproduction and classification

| Evidence | Fresh result | Classification | Action |
| --- | --- | --- | --- |
| `tests/test_benchmarks_registry.py` | 26 passed; 24.99 s; peak RSS 66.32 MiB | repaired integration boundary | Verified; no new change needed here |
| `tests/test_cross_modal_fusion.py` | collection exit 2; `ModuleNotFoundError: No module named 'torch'`; 36.57 s; 70.39 MiB | optional dependency unavailable | Preserved as a dependency-profile result; not converted to a skip or claimed as a code failure |
| `tests/test_job_runner.py` | 10 passed; 40.59 s; peak RSS 84.27 MiB | transient/baseline environment failure | Direct rerun did not reproduce the historical permission failure |
| MNE-BIDS schema/validation files | 2 isolated files passed; 18.72 s | repaired path serialization boundary | Verified forward-slash artifact path contract |
| `tests/integration/test_preflight.py` | 16 passed, 1 skipped; 42.83 s; peak RSS 65.80 MiB | platform capability limitation | The skip is only for Windows `WinError 1314` symlink privilege |
| `tests/test_oss_opportunity_cli.py` | passed; 14.96 s | platform capability handled | Existing capability-aware symlink guard verified |
| `tests/test_topology.py` | exit 5 with one `cripser`-required test skipped; 63.37 s; peak RSS 65.13 MiB | optional dependency unavailable | No production topology result is claimed when `cripser` is absent |
| integration reconciliation stacking tests | missing `origin/stacked-on-feature-a` fixture ref causes `changed_files()` to return `None`; two assertions fail; one file times out in the grouped replay | baseline fixture defect | Left failing. The task forbids changing the shared fixture, and fabricating a missing Git ref would corrupt reconciliation evidence |

The historical four timeout groups were replayed with a 120-second worker
bound. The T-real timeout was reproduced directly; the reconciliation replay
also exposed the missing stacked-ref fixture; the PITNN/pipeline and mixed
research/record groups completed when replayed explicitly at this checkout.

## Production repair

`sciencer_d.btc_icft.level_t.base_real_topology.build_ml_decoding_report` now
requires signal-derived, non-degenerate topology rows before launching the
cross-validated permutation classifier. Real-mode extraction already reports a
missing source file as a warning-bearing zero row. Such a row is a diagnostic
placeholder, not an observation. Previously, the CLI passed those rows to a
1,000-permutation ML report, which caused all three deterministic real-mode
T-real cases to exceed the 120-second isolated bound and could treat missing
signals as reproducible numerical features.

The repaired behavior returns `not_applicable` with exclusion counts when no
eligible rows exist. Valid signal-derived rows continue through the existing
classifier and permutation method unchanged. No timeout was increased, no
data were imputed, and no scientific verdict was promoted.

Regression coverage is in
`tests/integration_repair/test_t_real_missing_signal_guard.py`. The complete
`tests/btc_icft/test_t_real_cli_stats_wiring.py` file then completed in 79.91
seconds with zero isolated timeouts.

## Remaining limitations

- `torch` and `cripser` availability remains environment-dependent and must be
  supplied by the appropriate optional dependency profile when those tests are
  required.
- Windows symlink creation requires a host capability/privilege that is not
  guaranteed. The code path is tested where supported; the privilege-only case
  reports an explicit skip.
- The stacked reconciliation fixture remains inconsistent with its tests and
  is intentionally not changed here because `conftest.py` is out of scope.
- The current full discovery was not represented as green: the broad runner
  was bounded and interrupted before a complete aggregate report could be
  written. Historical CI billing/disk failures remain infrastructure evidence,
  not test success or failure evidence.
