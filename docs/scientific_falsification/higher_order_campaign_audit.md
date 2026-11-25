# Higher-order campaign audit

This note is the human-readable companion to
`configs/scientific_falsification/higher_order_campaign.yaml`.
It preregisters a comparison ladder. It is not an empirical result.
It does not compute a Bayes factor and it must never emit a scientific
`PASS`.

Owned with the YAML protocol and
`tests/scientific_falsification/test_higher_order_campaign.py` only.
Bayesian falsification, forecasting implementations, signal extraction,
Awareness Studio, and the hypothesis registry are not modified here.

## Campaign ladder

Nested families, scored in order on locked splits:

1. PSD
2. pairwise functional connectivity
3. triadic functional connectivity
4. higher-order spectra
5. directed hypergraph

Physiology and autonomic variables (respiration rate, heart rate,
HRV, electrodermal activity) are explicit candidate predictors or
controls. Respiration is not equanimity. Autonomic amplitude is not
meditation quality.

## Locked design

- Target transition: a declared behavioral state change with verified
  condition labels and a contemporaneous behavioral measurement.
- Prediction horizon: 10 seconds, locked.
- Splits, all required: subject-held-out, session-held-out, forward-time.
- Minimum sample: 20 paired subjects, 8 held-out subjects, 2 sessions
  per split. Below that the only admissible outcome is
  `INSUFFICIENT_POWER`.
- Primary scores: locked-split log loss and Brier score.
- Secondary scores: calibration slope, incremental delta versus the
  previous rung, autonomic-control-adjusted delta.
- Missing data: listwise within a rung or an imputation rule declared
  before lock. Undocumented imputation is rejected.
- Preprocessing lock: before splits. Changes after lock are rejected.

## Nulls and controls

Required nulls: flat, Gaussian, phase shuffle, label permutation,
circular shift, block shuffle, matched variance, matched
autocorrelation. Minimum 100 replicates. Synthetic nulls cannot create
`PASS`.

Common-driver controls: global signal, respiration, heart rate, motion,
condition-label uncertainty. Gain that vanishes after a declared
common driver is `GAIN_CONFUNDED`.

Multiplicity: declare `n_tests` before looking. Unknown test count is
not treated as one test. Bonferroni or Holm required when more than
one comparison is scored. Uncorrected comparisons are rejected.

Stopping rule: fixed sample, then stop. Peeking is rejected.

## Falsification

An incremental gain must be positive on the locked primary scores,
stable across the three splits, survive common-driver controls, and
replicate on an independent cohort or held-out site. Otherwise the
protocol assigns one of:

- `NO_INCREMENTAL_GAIN`
- `GAIN_UNSTABLE`
- `GAIN_CONFUNDED`
- `GAIN_NOT_REPLICATED`
- `INSUFFICIENT_POWER`
- `INCONCLUSIVE`
- `FORMAL_FORECAST_EVIDENCE_PENDING_REVIEW`

`FORMAL_FORECAST_EVIDENCE_PENDING_REVIEW` is not `PASS` and is not a
formal Bayes factor.

## Explicitly rejected

- training-only improvements
- test-set tuning
- post-hoc feature selection
- subject leakage
- uncorrected multiple comparisons
- unverified condition labels
- synthetic data labeled as empirical
- prediction interpreted as causation
- triadic dependence interpreted as a biological mechanism
- respiration interpreted as equanimity
- discernment inferred from EEG without behavioral measurement

## Leakage rules

No subject or session may appear in both train and test. Features may
not use future time. Split identifiers are locked before fitting.
Condition labels that have not been independently verified exclude the
record.

## Scientific limit

A complete protocol is a planning artifact. Completeness is not
evidence that higher-order spectra or directed hypergraphs forecast a
state transition, and it is not evidence of consciousness, quantum
coherence, exceptional points, or biological topological phases.

A preregistered protocol is not empirical evidence.
