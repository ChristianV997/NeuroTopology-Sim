# Surrogate-null contract for synthetic multichannel signals

Status: **HOLD / SYNTHETIC_ONLY**. Synthetic arrays only. No datasets, no participant
data, no subprocess, no network. A null that preserves a chosen statistic is not thereby
biologically valid for any scientific question. Nothing here establishes a result.

Code: `tools/surrogate_nulls/` (stdlib only; no NumPy or SciPy).
Tests: `tests/surrogate_nulls/` (52 tests, `unittest`).

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

## Declared tolerances

| Name | Value | Used for |
|---|---|---|
| `AUTO_SPECTRUM_TOL` | `1e-2` relative power error per channel | IAAFT auto-spectrum status |
| `CROSS_SPECTRUM_STRICT_TOL` | `1e-3` relative Frobenius error | IAAFT strict cross-spectrum status |
| `MARGINAL_EXACT_TOL` | `1e-12` absolute | marginal "exact" status |
| `ENSEMBLE_TOL` (tests) | `0.15` relative Frobenius | Cholesky expectation test (declared before measurement) |
| `EPS` | `1e-12` denominator guard | every relative error |

## Denominators

Every relative error is `||actual - target|| / (||target|| + EPS)`, summed over bins for
CSD comparisons and over bins per channel for power comparisons. The denominator is reported
in each report as `denominator_eps`.

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

## Limitations

- O(n^2) reference transforms. Intended for short synthetic arrays, not production data
  volumes.
- The Cholesky null's expectation is verified by Monte Carlo at one design point (N = 32, two
  channels, halfwidth 1). Other designs need their own ensemble check.
- The winding statistic used in tests is a toy loop statistic for a designed three-channel
  signal. It is not a project metric.
- No claim is made about any biological signal, dataset, or result.
