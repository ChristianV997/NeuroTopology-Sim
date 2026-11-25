# Integration regression closure

This report records the bounded replay performed for
`codex/integration-regression-closure`. The branch starts at the verified
integration head `af3ac584419148ddcfc57cb565c416eba6328725` and does not modify
PR #236, PR #251, or the primary checkout.

## Evidence and classifications

All commands used fresh Python subprocesses through
`scripts.run_tests_isolated`, with a hard process-tree timeout. Peak memory is
the runner's process telemetry; `null` means that the worker ended before a
sample was available.

| Area | Reproduction | Result | Classification |
| --- | --- | --- | --- |
| `tests/test_pitnn.py` | one fresh process, 90 s | 8 passed, 62.57 s, 100,000-step long-horizon audit now completes | actual regression repaired |
| `tests/test_pipelines.py` | one fresh process, 60 s | 18 passed, 15.31 s, 210.83 MiB | pass |
| PITNN cohort/integration | two fresh processes, 60 s each | 32 passed / 19.55 s / 229.24 MiB; 5 passed / 28.63 s / 197.20 MiB | pass |
| research/replay group | one fresh process, 120 s | pass, 84.34 s | pass |
| reconciliation core | one fresh process, 120 s | 10 passed, 118.80 s / 90.62 MiB | slow but bounded; no failure |
| reconciliation stacking | fresh processes, 120 s | 9 passed and 2 fixture failures; no timeout | fixture inconsistency |
| topology / optional `cripser` | fresh process | skipped because `cripser` is unavailable | optional dependency unavailable |
| cross-modal fusion / optional `torch` | fresh process | import failure: `ModuleNotFoundError: torch` | optional dependency unavailable |
| MNE/BIDS, benchmark, job/report pipeline | fresh processes | all targeted groups passed | pass |
| Windows preflight/symlink capability | fresh process | capability reported as unavailable where privilege is absent; test group passed | platform limitation, explicit |
| T-real CLI stats wiring | fresh process, 120 s | timeout before PR #251 was an ancestor of this integration head | prerequisite branch state; not duplicated |

The initial integrated-head replay also found the two expected stacked-branch
tests failing because their fixture references
`origin/stacked-on-feature-a`, but the fixture setup creates no such ref. The
failure is reproducible as `None` from `git diff`, not as a production stack
calculation error. This branch does not synthesize that ref or edit the
prohibited fixture/conftest surface. `tools.integration_repair.fixture_audit`
records this state as `fixture_inconsistency` without network access.

## Production repairs

1. The reconciliation model now carries current check/lifecycle status, stack
   metadata, effective base-relative file changes, scientific gate hints,
   duplicate candidates, and ancestry-based supersession. The integration
   entry point now wires the existing stack, duplicate, CI-interpretation, and
   scientific-gate modules into the report instead of leaving those public
   fields disconnected.
2. Git snapshot and diff collection now resolves refs once per operation and
   avoids redundant existence probes. This reduced the repeated subprocess
   overhead that amplified reconciliation batches near the hard timeout.
3. Check conclusions retain the existing strict contract: only an explicit
   `success` conclusion is passing. Neutral/skipped/unknown conclusions are
   not silently promoted to passing.
4. The low-level compatibility LLG step path reuses fixed scratch buffers and
   cached coefficients. It preserves the seeded global NumPy noise source,
   Heun update, torque, projection, and public return shape while making the
   100,000-step stability audit complete in a bounded process.

No scientific verdict, Bayes-factor/K gate, dataset, adapter, runner, or
platform utility was changed.

## Remaining blockers

- The stacked reconciliation tests remain blocked by the missing local fixture
  ref. The safe repair belongs in the fixture-owning branch and should create
  `stacked-on-feature-a` from `feature-a`; this branch intentionally does not
  alter that prohibited surface.
- `torch` and `cripser` remain optional and unavailable in this environment.
  Their tests must remain capability-aware rather than being reported as
  production passes.
- The current integration head does not contain PR #251. T-real missing-signal
  behavior is therefore a dependency/branch-state blocker, not a new repair
  in this branch.
- The reconciliation core is still close to the 120-second batch boundary on
  Windows because its fixture setup creates many temporary Git repositories.
  It passed at 118.80 seconds in this replay; fixture/runner ownership should
  address further scheduling margin.

## Reproduction environment

The replay ran on Windows (`win32`), Python 3.14.7, with no `torch` or
`cripser` installed and without network access from the diagnostics. Reports
were written under `%TEMP%\\nt-closure-*` and are local telemetry artifacts,
not generated repository outputs.
