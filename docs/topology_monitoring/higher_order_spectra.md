# Bounded higher-order spectral features

This module implements descriptive signal-processing summaries for higher-
order interactions. It is not a topology algorithm, does not estimate
consciousness, and does not establish biological causation.

## Schema and provenance

Reports use schema version `NeuroTopologySim.HigherOrderSpectra.v1`. Typed
records cover the frequency axis, segment configuration, provenance/checksum,
bispectrum, selected trispectrum slices, modulogram, and surrogate comparison.
JSON serialization rejects `NaN` and `Infinity`; unavailable estimates are
encoded as `null`.

Every report records:

- frequency units (`Hz`) and sampling-rate provenance;
- source label, synthetic flag, channel/sample counts;
- SHA-256 of canonical float64 input bytes plus shape and sampling rate;
- FFT length, segment length, overlap, taper, detrending, frequency-bin and
  slice limits, channel limit, surrogate limit, and memory budget.

## Estimators

`compute_bispectrum` averages

\[
B(f_1,f_2)=E[X(f_1)X(f_2)X^*(f_1+f_2)]
\]

over RMS-normalized segments and channels. It returns magnitude and a bounded
bicoherence summary. `compute_trispectrum_slices` evaluates only requested
two-dimensional slices of

\[
T(f_1,f_2,f_3)=E[X(f_1)X(f_2)X(f_3)X^*(f_1+f_2+f_3)].
\]

The complete four-dimensional trispectrum is never computed by default.
`compute_modulogram` provides a reduced carrier-by-modulation-frequency map
using bounded analytic-envelope bands. It is a modulogram-style feature, not a
topological charge.

Comparison features include normalized PSD, first-pair cross-spectrum,
phase-amplitude coupling, and a pairwise cross-frequency magnitude matrix.
These are descriptive comparison features, not interchangeable evidence
streams.

## Complexity and memory limits

The default configuration is deliberately small: 256-sample segments, 256
FFT points, 50% overlap, 32 frequency bins, four trispectrum slices, eight
channels, 32 surrogates, and a 64 MiB working-memory budget. Callers must use
explicit positive limits. Input channel counts and an estimated workspace are
checked before computation; a budget violation raises `MemoryError` rather
than silently allocating unbounded arrays.

Taper choices are deterministic built-ins (`boxcar`, `hann`, `hamming`, and
`blackman`). Demeaning/detrending, segment overlap, frequency resolution, and
RMS normalization are recorded in the output.

## Surrogates and diagnostics

The module supports seeded amplitude shuffles, phase-randomized surrogates,
and block shuffles. Each `SurrogateComparison` records method, seed, count,
observed value, surrogate moments, standardized difference, empirical
p-value, and block length when relevant. These are calibration controls, not
formal significance claims.

Diagnostics explicitly flag the expected near-zero higher-order behavior of
independent Gaussian noise, report descriptive amplitude-modulated-carrier
peaks, and warn about filter/taper artifacts, finite-segment edge effects, and
low segment counts. Coupled-oscillator comparisons remain proxies and do not
imply directionality or causation.

## CLI and optional dependencies

The offline CLI accepts local `.npy`, `.npz`, or numeric CSV input:

```text
python scripts/compute_higher_order_spectra.py \
  --input signal.npy --sampling-rate 256 --output report.json --synthetic
```

No network access or repository signal loader is used. The estimator uses
NumPy-only primitives; SciPy is not required. Invalid inputs produce a finite
JSON error envelope with null estimates. Synthetic data is explicitly marked
synthetic and cannot be interpreted as empirical evidence.
