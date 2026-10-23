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

## Current verification and discovery state (refreshed 2026-10-23, Cursor Agent A)

Final PR head for this refresh: `98fdc6eae63154ac21d19b70fb091cad299cfcc3` (docs-only tip atop code/test candidate `eb1b4ae97de16a527b1c20a835045222ec9ecd21`). Live `main` / PR base: `57b7e43d42678822e9eec03679891c1770040327` via normal merge `ba44e21d8cb94fc02cf2e28edf6b7fba519f2ecf` (`main_in_head=yes`). Production leaf unchanged (blob `a1f0d6cc2b30baf2b3c6126da016ca0ebf829bd3`). Cumulative PR paths remain only this document and the two owned tests.

Bounded independent read-only reviews at exact head `98fdc6ea` found **no concrete owned-path defects** (oracle independence/numerical edge cases: CLEAN; bridge path/import/error semantics: CLEAN). Adversarial probes on that head reproduced fail-closed singularity, underflow-vs-singular labeling, large-scale diagonal logs, determinant recovery, non-finite rejection, and forged-stub rejection; no new failing oracle/bridge behavior was observed before or after review.

Local verification at `98fdc6ea` with the existing Python 3.12 environment (**no packages installed this run**):

- `python3 -m unittest tests.dmd_ep2_oracle.test_oracle -v` — **29 passed**, 0 skip/fail/error.
- `DMD_EP2_REQUIRE_PRODUCTION=1 python3 -m unittest tests.dmd_ep2_oracle.test_production_bridge -v` — **9 passed**, 0 skip/fail/error.
- `python3 -m unittest discover -s tests/dmd_ep2_oracle -v` — **38 passed**, 0 skip/fail/error.
- Focused Round-6 selector: `Round6DiscoveryTests.test_dmd_production_bridge_is_paired_but_oracle_only_change_blocks` — **passed**. `compileall` and `git diff --check` on owned paths — passed.
- Neighbor DMD pytest (already present `pytest`/`numpy`; **SciPy absent**; no install): collected 36 tests; **34 passed, 2 failed** in out-of-scope production generator diagnostics (`principal_branch` expectations in `tests/experimental/test_dmd_crouzeix.py` and `tests/dmd_crouzeix_contract/test_production_contract.py`). Those failures are **not** owned by this PR and are not treated as oracle/bridge defects.

Exact-final-head hosted evidence: Required Checks run [40012611544](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/40012611544). Diff base `57b7e43d42678822e9eec03679891c1770040327`, diff head `98fdc6eae63154ac21d19b70fb091cad299cfcc3`, tested merge checkout/workflow SHA `3cda8814e49b91e154716e5a9247e35d2f499e09`. Artifact [required-core-test-report, ID 12526727953](https://api.github.com/repos/ChristianV997/NeuroTopology-Sim/actions/artifacts/12526727953).

- Round-6 selected `dmd_crouzeix` and executed `tests/dmd_ep2_oracle/test_production_bridge.py` with `DMD_EP2_REQUIRE_PRODUCTION=1`: **9 collected, 9 passed, 0 skipped, 0 failures, 0 errors, 0 timeouts**; JUnit reconciliation `matched` (9 testcase records); bridge runner stderr empty.
- Selector status **BLOCKED**, not PASS: `tests/dmd_ep2_oracle/test_oracle.py` in `unmapped_candidate_paths` → oracle had **zero hosted executions**. Core isolated batches: 13/13 passed; that does not clear the selector failure.
- Live `main` still maps the production leaf → bridge only and keeps `tests/dmd_ep2_oracle/` in `UNMAPPED_CANDIDATE_ROOTS`. PR #443 (`c373d202`) proposes `independent_reference_tests` for the oracle and can schedule it when the bridge file co-changes, but **oracle-only** changes remain unmapped and the root stays in `UNMAPPED_CANDIDATE_ROOTS`. Workflow edits stay outside this PR.

Exact discovery handoff for the workflow owner (Codex Agent A):

- Keep bridge pair `neurotopology_sim/experimental/dynamics/dmd_crouzeix.py` → `tests/dmd_ep2_oracle/test_production_bridge.py`, environment `DMD_EP2_REQUIRE_PRODUCTION=1`, command `DMD_EP2_REQUIRE_PRODUCTION=1 python -m unittest tests.dmd_ep2_oracle.test_production_bridge -v`.
- Add a durable test-only self-pair (or equivalent independent execution) for `tests/dmd_ep2_oracle/test_oracle.py` that also clears oracle-only diffs, and remove or narrow `tests/dmd_ep2_oracle/` from `UNMAPPED_CANDIDATE_ROOTS`. Command: `python -m unittest tests.dmd_ep2_oracle.test_oracle -v`.
- Require both suites on the exact final candidate, nonzero counts (currently 9 bridge / 29 oracle expected), zero unexplained skips/failures/errors/timeouts, and matched JUnit. Bridge-only success is not whole-PR success.
