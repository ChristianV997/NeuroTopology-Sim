# Round 6 DMD / EP2 / matrix-log audit (oracle, synthetic only)

**State: HOLD / SYNTHETIC_ONLY.** Independent oracle at `tests/dmd_ep2_oracle/`. Numerical diagnostics and matrix bounds do **not** establish a biological exceptional point, neural generator branch, or empirical effect.

## Run modes (keep distinct)

| Mode | Command | Production leaf |
|------|---------|-----------------|
| **oracle-only** | `python -m unittest tests.dmd_ep2_oracle.test_oracle -v` | not imported |
| **production-import** | `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v` | **required** (fail closed if absent) |
| discover (mixed) | `python -m unittest discover -s tests/dmd_ep2_oracle -v` | bridge skips with `ORACLE_ONLY:` only when the source file is absent and production is not required; when the file is present, bridge **must run** |

Owned paths only: `tests/dmd_ep2_oracle/`, `docs/dmd_ep2_oracle_audit.md`. Production DMD is **not** edited here.

Bridge helper imports load sibling `test_oracle.py` by file path so a missing production leaf is reported as `ORACLE_ONLY` / fail-closed `AssertionError`, never as `ModuleNotFoundError: test_oracle`. Production identity checks compare the resolved source path and module spec, then compare the bridge-exercised function code objects with definitions compiled directly from that exact leaf. These are test-time identity checks, not a cryptographic integrity guarantee against a process that deliberately forges or replaces Python code at runtime.

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

Pure-Python 2×2: EP2 splitting / full `N²=0`, within-trajectory pairing, signed Nyquist 240↔−10 @ 250 Hz (exact float identity), principal matrix log, branch proximity, similarity covariance `f(PBP⁻¹)=P f(B) P⁻¹`, ill-conditioned nonnormal residual budgets (`κ_proxy`-scaled, not ad hoc loosening), exact-zero/empty spectrum fail-closed branch diagnostics, shape/finite validation before matrix-function evaluation, and Nyquist fail-closed on non-finite frequency or non-positive `Fs`. It rejects non-finite scalar logs and nilpotency residuals (including overflow-generated NaN), invalid thresholds, and the principal-log negative-real cut; it preserves representable small positive eigenvalues and finite large-scale diagonal inputs using a scaled discriminant/determinant calculation, with exact rational determinant fallback near floating-point cancellation. Roots below the representable range are rejected explicitly as unsupported rather than mislabeled singular. Generic matrix exponentiation remains defined at zero eigenvalues. The repeated-root matrix-function branch calls `assert_full_nilpotency` (full `||N²||`, not a single-entry proxy). Regression: single-entry `n00²+n01·n10` proxy is insufficient.

## Current verification and discovery state (refreshed 2026-10-23)

- Live `main`: `57b7e43d42678822e9eec03679891c1770040327`. PR #400 was at head `ea64a9307c78696e9432915af9e7e7b900ec975e`, with recorded base `b51bb9b4bdf63c19894bb407eadcd70f528f7dda`. The branch was synchronized by normal merge commit `ba44e21d8cb94fc02cf2e28edf6b7fba519f2ecf`; the cumulative PR diff remains only this document and the two owned tests. The production leaf is unchanged (blob `a1f0d6cc2b30baf2b3c6126da016ca0ebf829bd3`).
- On the main-synchronized code/test tree, local `unittest` results were: oracle **29 passed**, required production bridge with `DMD_EP2_REQUIRE_PRODUCTION=1` **9 passed**, and combined discovery **38 passed**, all with zero skips/errors. No dependencies were installed. `compileall` for `tests/dmd_ep2_oracle` and `git diff --check` passed.
- Neighboring pytest-style DMD suites could not be executed in the available runtime because pytest is absent; the fast exceptional-point neighbor also requires unavailable SciPy. The attempted unittest load produced three dependency import errors and no actual tests from those suites. This is unavailable coverage, not a pass.
- Current `main`'s Round-6 selector maps `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` to `tests/dmd_ep2_oracle/test_production_bridge.py`, but retains `tests/dmd_ep2_oracle/` in `UNMAPPED_CANDIDATE_ROOTS`. Therefore the changed oracle test remains unmapped on current `main`. Workflow PR #443 remains open at head `9c6f53d640594653bf37cfde698fbca94cfb1d15` (based on `eee3fffe0f78ee29e13a7f087a20f783dafb745c`) and proposes a test-only oracle mapping; it is not merged and is not current-main hosted evidence. The old Required Checks run `39905598062` is pre-sync and bridge-only, so it does not establish current-head path coverage.

Exact discovery handoff for the workflow owner (no workflow edits in this lane):

- Bridge pair: implementation `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py`; test `tests/dmd_ep2_oracle/test_production_bridge.py`; set `DMD_EP2_REQUIRE_PRODUCTION=1`. Expected hosted result: 9 collected / 9 passed / 0 skipped, failures, errors, or timeouts; matched JUnit.
- Independent oracle test-only self-pair: implementation and test are both `tests/dmd_ep2_oracle/test_oracle.py`. Register a test-only component selecting this self-pair and remove or narrow `tests/dmd_ep2_oracle/` from `UNMAPPED_CANDIDATE_ROOTS`. Command: `python -m unittest tests.dmd_ep2_oracle.test_oracle -v`. Expected hosted result: 29 collected / 29 passed / 0 skipped, failures, errors, or timeouts; matched JUnit.
- Both paths must run on the exact candidate head with nonzero reconciled JUnit counts. Bridge-only success is not whole-PR success. No CI/workflow files are edited in this lane.
