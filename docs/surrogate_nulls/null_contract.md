# Surrogate-null contract for synthetic multichannel signals

Status: **HOLD / SYNTHETIC_ONLY**. Synthetic arrays only. No datasets, no participant
data, no subprocess, no network. A null that preserves a chosen statistic is not thereby
biologically valid for any scientific question. Nothing here establishes a result.

Code: `tools/surrogate_nulls/` (stdlib only; no NumPy or SciPy).
Tests: `tests/surrogate_nulls/` (121 tests in seven modules, `unittest`). See the CI discovery
note below for how they are run.

## Conventions

- Input: a rectangular array of finite real numbers, `x[channel][time]`. Bool, complex,
  ragged, empty, and non-finite values are rejected with `SurrogateInputError`.
- Transform: unnormalised forward DFT, `X[k] = sum_t x[t] exp(-2 pi i k t / n)`, bins
  `k = 0 .. n//2`. Inverse with the Hermitian extension implied by real data. Taking real
  parts enforces Hermitian symmetry. The imaginary parts of the DC bin and, for even `n`,
  the Nyquist bin are discarded and reported (`dc_imag_discarded`, `nyquist_imag_discarded`).
- Periodogram cross-spectrum: `C[k][i][j] = X_i[k] conj(X_j[k]) / n`.
- Randomized bins: positive frequencies excluding DC and Nyquist. Even `n`: `1 .. n/2-1`.
  Odd `n`: `1 .. (n-1)/2`. Fixed bins: DC, and Nyquist for even `n`.
- Seeds: integers only. Each (seed, label) pair seeds an independent stream via
  `random.Random("seed|label")`, which is stable across processes. Labels separate
  channels, bins, and null families, so changing one bin does not shift another.

## Null definitions

### 1. `common_phase_prichard_theiler`

- **Rule.** rFFT each channel. Draw one uniform phase per randomized bin, shared by all
  channels. Multiply that bin of every channel by the same unit phasor. Inverse rFFT.
- **Preserved (exactly, by construction).** Each channel's power spectrum, the complex
  cross-spectrum at every bin, and therefore same-frequency inter-channel phase differences.
- **Randomized.** The absolute phase of each randomized bin, identically across channels.
- **Intended use.** A baseline that keeps all second-order complex structure.
- **Invalid for narrowband spatial winding.** A winding statistic depends on phase
  differences, which this null preserves exactly. A winding statistic therefore cannot
  exceed this null. The tests show a designed winding survives every seed.
- **Marginal.** Not preserved. The report measures it.

### 2. `independent_phase_univariate_ft`

- **Rule.** rFFT each channel. Draw an independent uniform phase per channel and per
  randomized bin. Multiply. Inverse rFFT.
- **Preserved.** Each channel's power spectrum, exactly per bin.
- **Randomized.** All cross-channel phase relations. The cross-spectrum vanishes in
  expectation (tested: ensemble-mean cross-spectrum falls below 0.25 of the original).
- **Intended use.** A different and potentially too-weak null: it destroys coupling that
  a test may need to keep.
- **Invalid for volume-conduction claims.** It destroys zero-lag coupling that a
  volume-conduction-preserving null would keep. Do not present it as one.

### 3. `cholesky_gaussian_cross_spectral`

- **Target.** The CSD is estimated as a frequency-smoothed periodogram. Each output bin
  averages the raw matrices of neighbouring bins within `smoothing_halfwidth` (default 1).
  Edges are truncated, not reflected, and the average is normalised by the count used. The
  result is a convex combination of positive-semidefinite rank-one matrices, so it is
  Hermitian PSD.
- **Rule.** For each randomized bin, draw `X = sqrt(n) L g`, where `L` is the Cholesky factor
  of the smoothed CSD and `g` is complex standard normal with `E[g g^H] = I` (real and
  imaginary parts each have variance 1/2). Inverse rFFT.
- **Preserved, in expectation only.** `E[X X^H]/n` equals the smoothed target. The ensemble
  check (800 seeds, N = 32) gives relative Frobenius error 0.040 against a declared
  tolerance of 0.15. A control identity target gives 0.75 and fails the same criterion.
- **Single realisations are not exact.** One draw has cross-spectral deviation of about 1.4
  from its target. The report labels both auto- and cross-spectrum statuses
  `EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT`.
- **DC and Nyquist.** Real factors and real standard normals. Their coefficients are exactly
  real. A round-trip re-measurement leaves a floating-point residue near 1e-16.
- **Singular or rank-deficient CSD.** A Cholesky failure caused only by rounding is
  regularised by `ridge_rel * trace / d` (default `1e-8`) and reported in
  `rank_deficient_bins` and `ridge_applied_bins`. With `ridge_rel = 0` the failure is
  raised instead. A zero-trace bin gives zeros and is reported in `zero_power_bins`.
- **Failure behaviour (fails closed).** Negative trace, zero trace with nonzero entries,
  and genuinely indefinite matrices raise `NonPositiveDefiniteError`. Non-square, mismatched,
  non-finite, and non-Hermitian matrices raise `SurrogateInputError`.
- **Assumptions.** Stationarity over the record. A linear-Gaussian second-order model. The
  smoothing halfwidth sets the target's spectral resolution. Under these assumptions the
  null is meaningful for the smoothed cross-spectrum. It does not capture non-Gaussian,
  non-stationary, or nonlinear structure, and it is not a universal null.

### 4. `mv_iaaft_rank_adjusted`

- **Rule.** Start from a seeded random permutation of each channel. Iterate: rFFT; set each
  bin's magnitude to that channel's original magnitude and keep the current phase (DC and
  Nyquist real); inverse rFFT; then rank-adjust by assigning the channel's original sorted
  values in the order of the spectrally constrained signal. Stop when the rank order is stable
  or after `max_iter` iterations.
- **Preserved, exactly, after the final rank step.** Each channel's sorted values (the
  marginal). The report measures the marginal error and it is 0 by construction.
- **Approximate.** Auto-spectra. Reported before and after the final rank step.
- **Not targeted.** Cross-spectra. Reported, not guaranteed.
- **Strict gate.** `cross_spectrum_strict` is `MET_POST_RANK_STRICT` only if the measured
  post-rank cross-spectral error is at most `1e-3`. Otherwise it is `UNMET_POST_RANK_STRICT`.
  This algorithm does not meet that tolerance in the tested case, and the report says so. It
  is never claimed.
- **Convergence.** Reported. A run that reaches `max_iter` is labelled `NO_MAX_ITER_REACHED`.

## API-to-null map

Each public surface, the null hypothesis it encodes, what it assumes, what it estimates, what it
returns, and how it fails. The diagnostics are listed last. They are not nulls.

| API | Null hypothesis | Assumptions | Estimand | Outputs | Failure behaviour |
|---|---|---|---|---|---|
| `common_phase_prichard_theiler(x, seed)` | One common phase per randomized bin, identical across channels. A control that keeps all complex cross-spectra. | Stationary record | None (control only) | `(signals, report)`; `status.role = CONTROL_DIAGNOSTIC_ONLY` | `SurrogateInputError` for invalid arrays. Not a winding null. |
| `independent_phase_univariate_ft(x, seed)` | Independent phase per channel and bin. Destroys cross-channel coupling. | Stationary record | Per-channel power spectrum (exact per bin) | `(signals, report)` | `SurrogateInputError` for invalid arrays |
| `draw_from_csd(csd_by_bin, n_time, seed, ...)` | Gaussian draw per bin with covariance equal to the target. | Target is Hermitian PSD; linear-Gaussian model. With `real_coefficients=True` the target must be real. | `E[X X^H]/n` equals the target (in expectation) | `(spectra, info)`, including ridge and rank-deficient bins | `NonPositiveDefiniteError` if materially indefinite. `SurrogateInputError` for shape, Hermitian, or real-only violations. |
| `estimate_csd(data, estimator, ...)` | None (this is the estimator) | Stationarity; the estimator's stated resolution | The named CSD per bin | `(csd, info)`; `info["dof_per_bin"]` | `SurrogateInputError` for invalid inputs |
| `validate_supplied_csd(csd, n_channels, n_time)` | None (validation only) | None | Validated copy | The validated matrices | `SurrogateInputError` for shape, finiteness, or Hermitian violations. The data are not checked. |
| `cholesky_gaussian_csd(x, seed, estimator=..., ...)` | Linear-Gaussian stationary model whose covariance is the chosen estimate | Stationarity; linear-Gaussian; the estimator's resolution | `E[X X^H/n]` equals the estimate (in expectation) | `(signals, report)` with `estimator_validity`, `rank`, and per-bin diagnostics | Materially indefinite: `NonPositiveDefiniteError`. Rounding-level failure: ridge, reported. Supplied estimate: labelled `SUPPLIED_NOT_VALIDATED_AGAINST_DATA`. |
| `cholesky_gaussian_cross_spectral(x, seed, smoothing_halfwidth, ridge_rel)` | As above, with a boxcar-smoothed periodogram target | As above | As above, boxcar only | `(signals, report)` | As above. Halfwidth 0 is labelled as a diagnostic. |
| `zero_lag_real_part_gaussian(x, seed, ...)` (exploratory) | Ensemble zero-lag / real-covariance null: the expected real covariance equals `Re C` | Stationarity; zero-lag (real) structure is the only structure of interest; the imaginary part is discarded | `Re C(f)` in expectation over seeds | `(signals, report)`; listed in `EXPLORATORY_NULL_IDS` | As `draw_from_csd`. It makes no volume-conduction claim. |
| `mv_iaaft_rank_adjusted(x, seed, max_iter)` | Marginal-preserving null with approximately preserved auto-spectra | Stationarity; the iteration may not converge | Exact sorted values; approximate auto-spectra; cross-spectrum not targeted | `(signals, report)` with convergence and strict-gate status | `SurrogateInputError` for `max_iter < 1`. Non-convergence is reported (`NO_MAX_ITER_REACHED`), not raised. |
| `phase_loop_winding`, `winding_variation` | Not a null. A toy statistic and a check of whether a procedure varies it. | Designed signals | None | Winding value; `varies_from_original`, `varies_across_ensemble` | Not specified beyond input validation |
| `matrix_diagnostics`, `diagnose_csd` | Diagnostic | None | Effective rank, minimum eigenvalue, condition, participation | Per-bin values | `NonPositiveDefiniteError` if materially indefinite |
| `relative_phase_spread`, `zero_or_pi_distance` | Diagnostic | None | Circular spread across seeds; distance from {0, pi} | Per-pair statistics; per-realisation distance | `SurrogateInputError` for an empty seed set |

## Declared tolerances

| Name | Value | Used for |
|---|---|---|
| `AUTO_SPECTRUM_TOL` | `1e-2` relative power error per channel | IAAFT auto-spectrum status |
| `CROSS_SPECTRUM_STRICT_TOL` | `1e-3` relative Frobenius error | IAAFT strict cross-spectrum status |
| `MARGINAL_EXACT_TOL` | `1e-12` absolute | marginal "exact" status |
| `ENSEMBLE_TOL` (tests) | `0.15` relative Frobenius | Cholesky expectation test (declared before measurement) |
| `EPS` | `1e-12` denominator guard | spectral relative-error helpers (`complex_relative_error`, `power_relative_error`) |

## Denominators

The spectral relative-error helpers use `||actual - target|| / (||target|| + EPS)`.
CSD comparisons use the scale-invariant Frobenius error `||A - T|| / ||T||`, summed over
bins, with common component scaling and stable norm accumulation; they do not add `EPS` to
the denominator. A zero target returns zero only when the actual CSD is also zero; otherwise
the result is infinity. Any non-finite CSD input also returns infinity.

The report field `denominator_eps` records the `EPS` setting for the spectral helpers; it is
not applied to the CSD relative error.

## What the reports say

Each `SurrogateReport` lists the randomized and fixed bins, a `status` dictionary, the
measured marginal, auto-spectrum, and cross-spectrum errors, and the discarded DC and Nyquist
imaginary parts. A status string is a label, not a guarantee, and it is always derived from a
measured value compared with a declared tolerance, or it names what was preserved by
construction. The tests check the label against the number.

## Relation to other surfaces

- `tools/surrogate_audit/` (PR #398, unmerged) implements MV-FPR and MV-IAAFT on its own
  branch. The paths here are distinct. Its MV-FPR corresponds to the common-phase null, and
  its MV-IAAFT to null 4. Those are two independent implementations of the same two ideas.
  Consolidate only after #398 is reviewed; this branch does not import it.
- `validation/surrogate_testing.py` and `tests/test_surrogate_testing.py` on `main` are a
  separate per-channel FT/IAAFT gate. They are not modified.

## Spectral-matrix estimation (`tools/surrogate_nulls/csd.py`)

The Gaussian nulls take an explicit spectral estimate. The estimator is named in every report.

| `estimator` | What it is | Rank per bin (d channels) |
|---|---|---|
| `multitaper` (default) | sine multitaper: K orthonormal tapers `h_j(t)=sqrt(2/(n+1)) sin(pi (j+1)(t+1)/(n+1))`, average of tapered periodogram matrices | up to K |
| `periodogram_boxcar` | periodogram averaged over neighbouring bins within `smoothing_halfwidth` | up to 2h+1 |
| `single_periodogram` | one unsmoothed periodogram per bin | 1 for d >= 2 |
| `supplied` (via `spectral_estimate=`) | caller-provided Hermitian matrix per bin; validated for shape, finiteness, Hermitian symmetry; **not** checked against the data | as supplied |

- Default multitaper count: `K = min(n, max(4, d + 2))`, so the estimate keeps rank headroom.
- The orthonormality of the sine tapers is tested (Gram error about 1e-16).
- `single_periodogram` is rank one, so the cross-channel structure of a single epoch cannot be
  represented. The null reports rank one at every bin and applies ridge at every bin. Its draws
  then stay close to the periodogram direction, so the relative phases of the periodogram are
  largely kept. It is labelled `DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL` and is not a
  phase-randomising null.

### Estimator validity labels

Every estimated-CSD report carries `estimator_validity`. The label describes what the estimate can
support. It does not change how the draw is made.

| Label | When |
|---|---|
| `MULTIWINDOW_ESTIMATE_WITH_RANK_HEADROOM_REPORTED_PER_BIN` | multitaper with `K >= d + 1` |
| `MULTIWINDOW_ESTIMATE_LOW_RANK_REPORTED_PER_BIN` | multitaper with `K < d + 1` |
| `SMOOTHED_PERIODOGRAM_RANK_UP_TO_2H_PLUS_1_REPORTED_PER_BIN` | boxcar with `smoothing_halfwidth >= 1` |
| `DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL` | `single_periodogram`, or boxcar with halfwidth 0 |
| `SUPPLIED_NOT_VALIDATED_AGAINST_DATA` | caller-supplied estimate |

## Shrinkage, PSD policy, and conditioning

- Shrinkage (explicit, default 0): `C <- (1 - lam) C + lam (tr C / d) I`, `lam` in `[0, 1]`. The
  value is reported. Out-of-range values are rejected. Shrinkage adds an identity term, so a
  shrunk estimate can be full rank and can vary relative phases even when its estimator is a
  rank-one periodogram. The `estimator_validity` label describes the estimator, not the shrunk
  matrix. The reported `shrinkage` and `effective_rank_per_bin` describe the shrunk matrix.
- PSD policy: the smallest eigenvalue of each bin's matrix must be at least `-psd_tol * trace`
  (`psd_tol = 1e-10`). A smaller value is **materially indefinite** and raises
  `NonPositiveDefiniteError` before any regularisation. Negative eigenvalues within the tolerance
  are rounding noise. They are regularised by ridge (`ridge_rel * trace / d`) only when the
  Cholesky factorisation fails, and the bin is reported in `ridge_applied_bins`.
- Eigenvalues are computed by cyclic Jacobi rotations on the real embedding `[[A, -B], [B, A]]`
  of `H = A + iB`. The embedding is tested against a known matrix (eigenvalues `2 +- sqrt 2`) and
  against the trace.
- Per-bin reports: `effective_rank_per_bin` (eigenvalues above `rank_tol * max`, with
  `rank_tol = 1e-10`), `min_eig_rel_per_bin`, `condition_per_bin` (infinite when the smallest
  eigenvalue is below `rank_tol * max`), and `participation_ratio_per_bin`.
- **The participation ratio** `(sum lam)^2 / sum lam^2` is a continuous measure of how many
  directions the covariance actually uses. A value near 1 means one direction dominates, even
  when the numerical rank is higher. Example: the designed three-channel sinusoid gives
  participation 1.003 at its bin, and independent noise gives about 1.9. The test thresholds
  (1.01 and 1.5) are illustrations chosen after observing these values. They are not calibrated
  decision rules.

## The zero-lag real-part null (exploratory)

`zero_lag_real_part_gaussian` is **separately named and exploratory**. It is not in `NULL_IDS`,
and it appears in `EXPLORATORY_NULL_IDS` and `CONTRACTS`.

- Rule: keep `Re C(f)` from the estimate and draw **real** Gaussian Fourier coefficients with
  covariance `Re C(f)` at every bin. `draw_from_csd(..., real_coefficients=True)` enforces the
  real target.
- Preserved, in expectation over seeds: the real part `Re C(f)` of the estimated cross-spectrum.
  This is an **ensemble zero-lag / real-covariance null**. It constrains the ensemble real
  covariance and does not define a per-realisation phase constraint.
- The imaginary part of the estimate is discarded. Each realisation's bin coefficients are real
  by construction, so every imaginary part of the drawn spectra is exactly zero (tested). Across
  seeds, the mean cross-spectral imaginary part is zero, and the mean real part matches `Re C` within
  a 5-standard-error tolerance (tested: 400 seeds, N = 16, two channels, non-zero target imaginary part).
- **Observed generator property, not part of the null.** Because the draws are real, this
  generator's realisations have relative phases of 0 or pi at every bin (largest distance from
  {0, pi} below 1e-12 in the tests). That is an implementation fact about these draws. The report
  records it under `generator_relative_phase_observed`. The null does not impose it on each
  realisation, and it is not evidence about any recording.
- **PSD.** For real vectors `v`, `v^T Re C v = Re(v^H C v) >= 0`, so `Re C` of a Hermitian PSD
  estimate is real symmetric PSD. The tests check this for multitaper, boxcar, and single-periodogram
  estimates on synthetic data, with the same `psd_tol` as the rest of the package. An indefinite real
  matrix is rejected by the same check (negative control).
- Assumption-dependent. It does **not** model volume conduction, source geometry, filtering, or
  lagged coupling. It is **not** a volume-conduction detector, and it must not be used to claim
  that any of these is controlled.

## Does the procedure vary the phase statistic? (`winding_variation`)

`winding_variation(x, generator, seeds, bin_k)` reports whether a surrogate procedure varies the
toy loop-winding statistic across an ensemble. It returns `varies_from_original` and
`varies_across_ensemble`, with the distinct values. Measured results:

- Common phase: never varies the winding (tested on independent channels).
- Cholesky on independent three-channel noise: varies, taking values -1, 0 and 1.
- Cholesky on the designed noiseless sinusoid at its bin: does **not** vary the winding. The
  estimate there is dominated by one direction (participation 1.003), so draws keep the relative
  phases fixed. This is the rank-one failure mode, and it is reported rather than hidden.

A procedure that leaves the statistic unchanged must not be used to test that statistic.

Definition limits of the toy statistic (`phase_loop_winding`):

- A loop with fewer than three channels has winding 0. Its two edges cancel.
- An adjacent relative phase at exactly ±pi makes the minimal-wrap winding ambiguous. The function
  then raises `SurrogateInputError` instead of returning an arbitrary integer, and
  `winding_variation` raises for such a surrogate. The real-coefficient zero-lag null produces
  these steps, so its winding is undefined and the statistic is not applied to it.

## Common phase: a control, not a winding null

`common_phase_prichard_theiler` multiplies every channel at a bin by the same phasor
`exp(i phi_f)`. Its cross-product is then unchanged: `X_i'(f) conj(X_j'(f)) = X_i(f) conj(X_j(f))`
for every bin and every seed. This is an algebraic identity, and it is tested for every randomized
bin, every channel pair, and several seeds. Every same-frequency relative phase is therefore kept
exactly. A statistic built from relative phases cannot be shown to exceed this null. The procedure
is kept only as a labelled control (`role = CONTROL_DIAGNOSTIC_ONLY`): use it to check that a
statistic is blind to a common phase shift.

## Preserved properties: exact, in expectation, or approximate

| Null | Exact per realisation | In expectation over seeds | Approximate, or measured only |
|---|---|---|---|
| `common_phase_prichard_theiler` (control) | auto-spectra; complex cross-spectrum per bin; every same-frequency relative phase; DC/Nyquist real | - | marginal (measured) |
| `independent_phase_univariate_ft` | auto-spectra per channel | cross-spectrum tends to zero | marginal (measured) |
| `cholesky_gaussian_csd` (multitaper default) and `cholesky_gaussian_cross_spectral` | DC/Nyquist real; Hermitian and conjugate symmetry | `E[X X^H / n]` equals the estimate | single-realisation deviation (measured); marginal (measured); relative phases unconstrained |
| `zero_lag_real_part_gaussian` (exploratory) | every drawn imaginary part is zero; DC/Nyquist real | `E` of the real part equals `Re C` of the estimate (ensemble zero-lag / real-covariance null) | real-part deviation (measured); marginal (measured); observed 0-or-pi relative phases are a generator property, not part of the null |
| `mv_iaaft_rank_adjusted` | per-channel sorted values (marginal) after the final rank step | - | auto-spectra and cross-spectra measured before and after the rank step; strict cross gate reported UNMET when missed |

Reproducibility: every random draw comes from `rng_for(seed, label)`. Each (seed, label) pair
is an independent stream. Labels separate channels, bins, and null families, so changing one bin's
matrix leaves every other bin's coefficients bit-identical (tested).

## Degrees of freedom and rank

- Nominal degrees of freedom per bin: multitaper `2K`; boxcar `2 x` the number of averaged bins
  (edge-truncated); single periodogram `2`. These are **approximate**. Sine tapers, and neighbouring
  bins, are not exactly independent for coloured signals.
- Reported per bin: effective rank (eigenvalues above `1e-10 x max`), absolute and relative minimum
  eigenvalue, condition number, and participation ratio.
- No null claims full rank. Every estimated-CSD report carries `rank = EFFECTIVE_RANK_REPORTED_PER_BIN_NOT_ASSUMED_FULL`.
  A factorization returning a factor does not show full numerical rank.

## Relative-phase diagnostics

- `relative_phase_spread(x, generator, seeds, bin)` reports, for each channel pair, the circular
  spread `1 - R` of the surrogate relative phases across seeds, and whether it varies. Measured:
  the common-phase control gives zero spread for every pair. The Cholesky null on independent
  three-channel noise gives a maximum spread of about 0.87 at bin 3.
- `zero_or_pi_distance(signals)` gives, for one realisation, the largest distance of any
  inter-channel relative phase from {0, pi}. Measured: about 2e-15 for the zero-lag generator's
  real-coefficient draws, an observed property and not part of the null definition, and about
  1.55 rad for the Cholesky null on the same data. Use this diagnostic to describe a generator,
  not to define a null.

## Blocked: random dipole-cloud forward null

**Status: BLOCKED, not implemented.** The random dipole-cloud forward null needs an exact lead
field and a validated cross-spectral-density (CSD) model. Both are the subject of the four-shell
forward model in PR #418, which is open and unmerged. Until #418's lead field and CSD are available
and validated, this null is not implemented here. There is no mock lead field, no re-derived
physics, and no copy of #418's model. Its absence from the API map is deliberate.

## CI discovery

- The required check `core-tests` (`.github/workflows/required-checks.yml`) runs an explicit file
  list through `scripts/run_tests_isolated.py`. That list does not include `tests/surrogate_nulls/`.
  The hosted required check therefore does not discover these tests.
- `awareness-tests` runs only in `apps/awareness_studio`. It does not cover this package. Its
  failure on `main` is pre-existing and unrelated to this package.
- A local run is not a hosted check. The local command is to name the seven test modules explicitly
  from the repository root (`python -m unittest tests.surrogate_nulls.<module> ...`). Discovery on
  `tests/surrogate_nulls` is not importable in this layout. Hosted results are reported separately,
  with the commit SHA.

## Limitations

- O(n^2) reference transforms. Intended for short synthetic arrays, not production data
  volumes.
- The Cholesky null's expectation is verified by Monte Carlo at one design point (N = 32, two
  channels, halfwidth 1, and multitaper with K = 4). Other designs need their own ensemble check.
- The winding statistic used in tests is a toy loop statistic for designed signals. It is not a
  project metric.
- The participation thresholds in the tests are illustrations, not calibrated rules.
- The eigenvalue-based diagnostics are numerical, computed with Jacobi rotations on small
  matrices (d up to a few channels). They are not validated for large d.
- No claim is made about any biological signal, dataset, or result.
