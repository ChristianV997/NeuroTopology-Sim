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

## Current verification and discovery state (refreshed 2026-10-23, Antigravity Agent D)

Branch tip atop code/test candidate with hardened edge cases. Live `main` / PR base synced to `6136cb3fe3bc97e811f494a853f471988ce976bb` via normal merge `1ea03b25`. Production leaf unchanged. Cumulative PR paths remain only this document and the two owned test files (`tests/dmd_ep2_oracle/test_oracle.py`, `tests/dmd_ep2_oracle/test_production_bridge.py`).

Bounded independent verification and edge case reproduction found zero regressions in owned paths. Hardened test cases reproduce and verify:
- Fail-closed singularity classification for all-zero matrices (`((0j, 0j), (0j, 0j))`).
- Large-scale overflow handling when off-diagonal elements drive eigenvalue radius past floating-point range.
- Large-scale overflow handling when center and radius are finite individually but their sum/difference overflows float range.
- Catastrophic cancellation preservation: exact rational determinant recovery preserves small eigenvalues despite floating-point cancellation.
- Root recovery fail-closed rejection when the dominant root is zero.
- Bridge policy stub validation: rejection of stubs missing required symbols (`alias_ambiguity_report`), loader mismatches, missing `__file__`, and spec origin mismatches.

Local verification with Python 3.12 (**no packages installed this run**):

- `python -m unittest tests.dmd_ep2_oracle.test_oracle -v` — **35 passed**, 0 skip/fail/error (expanded from 29).
- `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v` — **13 passed**, 0 skip/fail/error (expanded from 9).
- Total focused tests across oracle and bridge: **48 passed**, 0 skip/fail/error.
- Neighbor DMD test suites: `tests/experimental/test_dmd_crouzeix.py` (**12 passed**), `tests/dmd_crouzeix_contract/test_production_contract.py` (**12 passed**).
- `py_compile` and `git diff --check origin/main..HEAD` — passed with zero warnings/errors.

Hosted evidence and discovery gap:
- Required Checks run [40024818885](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/40024818885).
- Round-6 selected `dmd_crouzeix` and executed `tests/dmd_ep2_oracle/test_production_bridge.py` with `DMD_EP2_REQUIRE_PRODUCTION=1`: **9 collected, 9 passed, 0 skipped, 0 failures, 0 errors, 0 timeouts**; JUnit reconciliation `matched` (9 testcase records).
- Selector status: **BLOCKED**, exit code 1: `"status": "BLOCKED", "unmapped_candidate_paths": ["tests/dmd_ep2_oracle/test_oracle.py"]`.
- The oracle suite had **zero hosted executions** because `tests/dmd_ep2_oracle/test_oracle.py` is not yet registered in `round6_experimental_tests.py` on `main`.
- PR #443 (`CI: map verified Batch 3 artifact and OSS candidate suites`, head `42de153b0cf93e732e83121bb8253d2ddd5fa2db`) is OPEN and maps `test_oracle.py` under `dmd_crouzeix`, but has not yet landed on `main`.
- Workflow files remain out of scope for PR #400. Bridge-only success cannot be treated as whole-PR success. PR #400 remains on **HOLD** pending workflow mapping landing on `main`.

Exact discovery handoff for the workflow owner (Codex Agent A):

- Keep bridge pair `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` → `tests/dmd_ep2_oracle/test_production_bridge.py`, environment `DMD_EP2_REQUIRE_PRODUCTION=1`, command `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v`.
- Register durable test execution for `tests/dmd_ep2_oracle/test_oracle.py` (command `python -m unittest tests.dmd_ep2_oracle.test_oracle -v`), clearing oracle-only diffs and removing `tests/dmd_ep2_oracle/` from `UNMAPPED_CANDIDATE_ROOTS`.
- Require both suites on the exact final candidate, nonzero counts (currently 13 bridge / 35 oracle expected), zero unexplained skips/failures/errors/timeouts, and matched JUnit.

