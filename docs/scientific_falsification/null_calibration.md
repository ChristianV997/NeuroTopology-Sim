# Null calibration

This note describes `analysis/null_calibration` and
`scripts/run_null_calibration.py`. It does not compute a Bayes factor
and it does not emit a scientific `PASS`.

Related context: PR #219 / #226 (falsification semantics), PR #229 /
#240 (provenance), PR #245 (claim-language audit). Paired-cohort
statistics live in a separate package and are not modified here.

## Purpose

Quantify how a declared statistic behaves under seeded nulls before any
empirical interpretation. Synthetic nulls remain demonstrations. They
cannot create `PASS`, confirm biology, or rewrite K.

## Supported nulls

1. `flat` — constant zero series. Does not preserve variance or lag-1.
2. `gaussian` — i.i.d. unit Gaussian. Does not preserve variance or lag-1
   unless the observed scale happens to be one.
3. `phase_shuffle` — Fourier phase randomization. Preserves the
   periodogram when numpy is present.
4. `label_permutation` — shuffle condition labels; statistic is a two-group
   mean difference.
5. `circular_shift` — circular roll of the series.
6. `block_shuffle` — shuffle contiguous blocks (`block_size`, default 4).
   Does not preserve lag-1 autocorrelation.
7. `matched_variance` — i.i.d. Gaussian with the observed sample variance.
   Does not preserve lag-1.
8. `matched_autocorrelation` — AR(1) matched to lag-1 and variance when
   that correlation is defined; otherwise falls back to matched-variance
   with a warning.

## Metric families

Calibrations are labeled with exactly one family:

- `graph_beta1`
- `spatial_winding_q`
- `scalar_chirality`
- `other`

The calibrator never converts graph cycle rank into spatial winding or
scalar chirality.

## Report fields

- `n_replicates`, `seed`
- `observed_statistic`
- `null_mean`, `null_variance`
- `empirical_percentile`
- `exceedance_count`
- `permutation_p_value` = (exceedances + 1) / (n + 1)
- `correction_method` (`none`, `bonferroni`, `holm`) and `n_tests`
- `effective_sample_size`
- `finite_value_status`
- `provenance`
- `synthetic_demo`
- `failed_replicates`, `skipped_replicates`, `warnings`, `errors`

Unavailable measurements are JSON `null`. Non-finite inputs are rejected.
`k_value` and `falsification_verdict` are always `null`.
`scientific_pass` is always `false`.

## Status values

- `CALIBRATION_ONLY` — a finite null pool was obtained.
- `INSUFFICIENT` — fewer than two successful replicates.
- `ERROR` — invalid spec or non-finite required input.
- `NOT_SUPPORTED` — reserved; this runner does not promote evidence.

A recommended floor of 100 replicates is warned; it is not a scientific
gate.

## CLI

```text
python scripts/run_null_calibration.py \
  --input spec.json \
  --output calibration.json
```

## Rules

1. Never call the output formal biological evidence.
2. Never modify K or falsification verdicts.
3. Never tune nulls to favor PITNN.
4. Use fixed integer seeds.
5. Preserve null-generation parameters in `parameters`.
6. Record failed or skipped replicates.
7. Reject non-finite outputs.
8. Use JSON null for unavailable measurements.
9. The same spec and seed must rerun identically.
10. Warn when a null does not preserve autocorrelation or variance.
11. Keep metric families separate.
12. Record multiple-comparison metadata. Unknown `n_tests` is not treated
    as one test.
13. Warn when replicate count is below 100.
14. Never emit scientific PASS.

## Limitations

Phase-shuffle and AR(1) matching are engineering surrogates. They do not
establish that a topology metric is identifiable on EEG or fMRI. A
calibrated p-value is not a formal Bayes factor.
