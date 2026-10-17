# Round 6 DMD / EP2 / matrix-log audit (oracle, synthetic only)

**State: HOLD / SYNTHETIC_ONLY.** Base is verified live `origin/main` at `3f3fe8593303184cb88eef056c1322f3d4e57a16`. Branch: `batch1/hermes-bots-dmd-ep2-oracle`. Round 6 candidate code was not found in this base; repository search only located DMD/Koopman mentions in docs and package descriptions. Consequently no claim is made that candidate code was run or reviewed. Primary checkout had pre-existing modifications; this work used a separate worktree and did not touch them.

## Reproducible checks

Run: `python -m unittest discover -s tests/dmd_ep2_oracle -v` — **7 tests passed** after extending the standard-library oracle. A second run with NumPy available through an isolated, non-checkout cache was used only to confirm environment availability: `uv run --offline --with numpy python -c "import numpy; print(numpy.__version__)"` reported NumPy 2.5.4; the verifier itself remains dependency-free. `git diff --check` passed. The tests use synthetic values; no network, datasets, installs into the repository, or third-party code were used.

The matrix-level oracle now covers diagonalizable, defective repeated-eigenvalue, strongly nonnormal, singular, and near-cut synthetic 2x2 matrices. It uses the closed-form 2x2 primary matrix-function identity (with the repeated-root derivative limit), not the candidate Denman–Beavers/Gregory implementation. For supported matrices, it checks `exp(log(A))` reconstruction and separately checks branch proximity. This is an independent mathematical oracle, not evidence that the candidate engine is correct.

## Analytic EP2 result

For the supplied matrix, eigenvalues are `ω0 − iγ ± sqrt(δ² − g²)`, so the theoretical eigenvalue split is `2 sqrt(δ²−g²)` on the real-split side. With δ=1.2: g=.4 gives 2.2627416997969525; g=1.0 gives 1.32664991614216; g=1.2 gives exactly zero analytically. At g=δ, after subtracting `(ω0−iγ)I`, the matrix is nonzero and squares to zero: algebraic multiplicity two and geometric multiplicity one (rank one). This avoids unstable eigenvector-condition-number expectations. A numerical implementation should use a scaled singular-value/rank tolerance tied to matrix norm and machine precision, and report sensitivity across tolerances; a raw floating determinant alone is cancellation-prone.

## Pairing and logs

The pairing test builds adjacent snapshots separately inside each trajectory. It demonstrates the false `(last(A), first(B))` transition introduced by concatenation with no boundary metadata. Preserve trajectory IDs/boundaries in any DMD regression test.

The executable checks cover scalar principal logarithms, singular scalar rejection, and a near-negative-real-axis phase warning. They **do not** implement or verify a general 2×2 Denman–Beavers/Gregory matrix logarithm, nor test its behavior on diagonalizable/defective/nonnormal matrices. NumPy is absent in the available interpreter, and installs were prohibited; with no Round 6 candidate available, this requested matrix-level verification remains a blocker. A small scalar `exp(log(z))` round trip is not evidence of correct matrix branch selection or recovery of a continuous-time generator.

A near-π principal phase is only a branch-sensitivity diagnostic. It does not establish an unobserved physical frequency, resolve aliasing, or prove the sampling rate adequate. Round-trip residual measures reconstruction consistency only; branch diagnostic measures proximity to the principal cut only. Neither proves generator recovery; compare against known synthetic generator, sampling interval, within-trajectory transitions, and an independently chosen branch.

Crouzeix `C=2` remains **PREPRINT_UNREFEREED**, not used as a validated bound or scientific evidence.

## Ownership and next step

Only `tests/dmd_ep2_oracle/test_oracle.py` is added. No subagents were used. No PR was created: the requested matrix-level suite and candidate comparison cannot be honestly completed in this environment, so the draft-PR gate is not met. No scientific `VALIDATED` or `PASS` claim is made.
