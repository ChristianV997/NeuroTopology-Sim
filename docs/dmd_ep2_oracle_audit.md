# Round 6 DMD / EP2 / matrix-log audit (oracle, synthetic only)

**State: HOLD / SYNTHETIC_ONLY.** Independent oracle at `tests/dmd_ep2_oracle/`. Numerical diagnostics and matrix bounds do **not** establish a biological exceptional point, neural generator branch, or empirical effect.

## Run modes (keep distinct)

| Mode | Command | Production leaf |
|------|---------|-----------------|
| **oracle-only** | `python -m unittest tests.dmd_ep2_oracle.test_oracle -v` | not imported |
| **production-import** | `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v` | **required** (fail closed if absent) |
| discover (mixed) | `python -m unittest discover -s tests/dmd_ep2_oracle -v` | bridge skips with `ORACLE_ONLY:` only when the source file is absent and production is not required; when the file is present, bridge **must run** |

Owned paths only: `tests/dmd_ep2_oracle/`, `docs/dmd_ep2_oracle_audit.md`. Production DMD is **not** edited here.

Bridge helper imports load sibling `test_oracle.py` by file path so a missing production leaf is reported as `ORACLE_ONLY` / fail-closed `AssertionError`, never as `ModuleNotFoundError: test_oracle`.

The oracle test includes a subprocess import firewall that blocks
`neurotopology_sim`, `dmd_crouzeix`, NumPy, and SciPy while loading the oracle.
Its expected values are derived from the local 2×2 formulas and standard
library complex arithmetic; it does not import the candidate/production DMD
implementation. The bridge, separately, imports the production package module
and requires its resolved `__file__` to equal this checkout's
`neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` path. A same-named
module from another checkout is rejected.

`ORACLE_ONLY` is reserved for a genuinely absent production source file. If
that file exists but import fails—for example because NumPy is unavailable or
the module has a runtime error—the bridge reports a failure, not a successful
skip. `DMD_EP2_REQUIRE_PRODUCTION=1` also turns an absent source file into a
failure. The source-path check establishes which checkout supplied the module;
it does not establish numerical, physical, empirical, or biological validity.

## Oracle coverage

Pure-Python 2×2: EP2 splitting / full `N²=0`, within-trajectory pairing, signed Nyquist 240↔−10 @ 250 Hz (exact float identity), principal matrix log, branch proximity, similarity covariance `f(PBP⁻¹)=P f(B) P⁻¹`, ill-conditioned nonnormal residual budgets (`κ_proxy`-scaled, not ad hoc loosening), exact-zero/empty spectrum fail-closed branch diagnostics, shape/finite validation before matrix-function evaluation, and Nyquist fail-closed on non-finite frequency or non-positive `Fs`. The repeated-root matrix-function branch calls `assert_full_nilpotency` (full `||N²||`, not a single-entry proxy). Regression: single-entry `n00²+n01·n10` proxy is insufficient.

## Discovery note

On the last verified hosted run for head `525aedda73534da7dfbcc554722a2456d692461f` (Required Checks run `39852520708`), Round-6 selected only `tests/dmd_ep2_oracle/test_production_bridge.py` under `dmd_crouzeix`: 4 collected, 4 passed, 0 skipped/failures/errors/timeouts, JUnit matched. `tests/dmd_ep2_oracle/test_oracle.py` remained unmapped and the overall selector reported `BLOCKED`; this is not a green required check. The run predates the path/import-policy regressions in this update and must be refreshed on the final head. CI/workflows are not edited in this lane.

Exact discovery handoff for Codex Agent A:

- Bridge pair: implementation `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py`; test `tests/dmd_ep2_oracle/test_production_bridge.py`; retain `DMD_EP2_REQUIRE_PRODUCTION=1`.
- Independent oracle pair: source and test are both `tests/dmd_ep2_oracle/test_oracle.py` (test-only component; no production implementation is imported). Map this self-pair so it is selected with a nonzero count, and remove or narrow `tests/dmd_ep2_oracle/` from the unmapped candidate roots.
- Both owned test files must execute on the exact candidate head with nonzero reconciled JUnit counts and zero unexplained skips, failures, errors, or timeouts.
