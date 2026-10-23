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

At verified head `1e14a5e744d55ffee1fd01c4e654d35a68a72194` (PR base `d78f54128b6fd60c30665c9e9cff307056dbdd82`; live main later `2c8a80bf9874b9f14205d4bb4e466754fb4589cb`), Required Checks run `39877399988` used tested checkout/workflow SHA `8edac9a4ca06b5f97b5b0d6361594bb5e8d0a287`. Round-6 selected only `tests/dmd_ep2_oracle/test_production_bridge.py` under `dmd_crouzeix`: 7 collected, 7 passed, 0 skipped/failures/errors/timeouts, JUnit matched. `tests/dmd_ep2_oracle/test_oracle.py` remained in `unmapped_candidate_paths` and the overall selector reported `BLOCKED`; Required Checks is not green. Bridge-only PASS is not whole-PR success. CI/workflows are not edited in this lane.

Exact discovery handoff for Codex Agent A (do not treat this note as a workflow edit):

- Bridge pair: implementation `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py`; test `tests/dmd_ep2_oracle/test_production_bridge.py`; retain `DMD_EP2_REQUIRE_PRODUCTION=1`. Expected hosted count: **7** collected / 7 passed / 0 skipped/failures/errors/timeouts; JUnit matched.
- Independent oracle self-pair: implementation and test are both `tests/dmd_ep2_oracle/test_oracle.py` (test-only component; no production leaf imported). Register a test-only component that selects this self-pair, and remove or narrow `tests/dmd_ep2_oracle/` from `UNMAPPED_CANDIDATE_ROOTS` so the oracle is not left unmapped. Expected local/hosted count: **18** collected / 18 passed / 0 skipped/failures/errors/timeouts (stdlib unittest; import firewall included). Command: `python -m unittest tests.dmd_ep2_oracle.test_oracle -v`.
- Both owned test files must execute on the exact candidate head with nonzero reconciled JUnit counts and zero unexplained skips, failures, errors, or timeouts.
