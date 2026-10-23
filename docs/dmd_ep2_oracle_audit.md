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

The code/test candidate reviewed for this evidence refresh was `eb1b4ae97de16a527b1c20a835045222ec9ecd21`, based on live `main` `57b7e43d42678822e9eec03679891c1770040327` via normal merge commit `ba44e21d8cb94fc02cf2e28edf6b7fba519f2ecf`. The production leaf was unchanged (blob `a1f0d6cc2b30baf2b3c6126da016ca0ebf829bd3`). The cumulative PR remains confined to this document and the two owned tests.

Local verification on that code/test tree, using the existing Python 3.12.14 environment and without installing dependencies:

- `python -m unittest tests.dmd_ep2_oracle.test_oracle -v` — **29 passed**.
- `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v` — **9 passed**.
- `python -m unittest discover -s tests/dmd_ep2_oracle -v` — **38 passed**.
- All three suites had zero skips, failures, or errors. Focused Round-6 discovery selector tests: **3 passed**. `compileall` and `git diff --check` passed.
- Neighboring pytest-style DMD suites could not be run locally: pytest is absent; the fast exceptional-point neighbor also requires unavailable SciPy. The attempted unittest import yielded three dependency import errors and no actual neighboring tests. This is unavailable coverage, not a pass.

Exact-head hosted evidence for code/test candidate `eb1b4ae97de16a527b1c20a835045222ec9ecd21` is Required Checks run [40012237449](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/40012237449). The workflow tested synthetic merge checkout/workflow SHA `2ac22ea65c7ed969336d18b19e8b9e29cf87034b`, with diff base `57b7e43d42678822e9eec03679891c1770040327` and diff head equal to the candidate SHA.

- Round-6 selected `dmd_crouzeix` and executed `tests/dmd_ep2_oracle/test_production_bridge.py` with `DMD_EP2_REQUIRE_PRODUCTION=1`: **9 collected, 9 passed, 0 skipped, 0 failures, 0 errors, 0 timeouts**; JUnit reconciliation was `matched` with 9 testcase records.
- The selector result was **BLOCKED**, not PASS: `tests/dmd_ep2_oracle/test_oracle.py` was listed in `unmapped_candidate_paths`. Thus the oracle had **zero hosted executions** and no hosted JUnit evidence. The core isolated batch step separately reported **13 batches passed, 0 skipped, 0 failed, 0 timeouts**; that does not clear the later selector failure.
- Current `main` maps `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` to the production bridge test, but retains `tests/dmd_ep2_oracle/` as an unmapped candidate root. The mapping gap is owned by the workflow/discovery lane, not this PR. No workflow files are changed here.

Exact discovery handoff for the workflow owner:

- Keep bridge pair `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` → `tests/dmd_ep2_oracle/test_production_bridge.py`, environment `DMD_EP2_REQUIRE_PRODUCTION=1`, command `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v`.
- Add a test-only self-pair for `tests/dmd_ep2_oracle/test_oracle.py` and remove or narrow `tests/dmd_ep2_oracle/` from `UNMAPPED_CANDIDATE_ROOTS`. Command: `python -m unittest tests.dmd_ep2_oracle.test_oracle -v`.
- Require both suites on the exact final candidate, nonzero counts (currently 9 bridge / 29 oracle expected), zero unexplained skips/failures/errors/timeouts, and matched JUnit. Bridge-only success is not whole-PR success.
