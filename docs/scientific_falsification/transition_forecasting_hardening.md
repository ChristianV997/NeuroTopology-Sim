# Transition-forecasting safety boundary

`analysis.transition_forecasting` is a deterministic, local benchmark of the
PSD → pairwise FC → triadic FC → directed-hypergraph feature ladder. It does
not establish causal influence, biological mechanism, consciousness, or a
formal scientific conclusion.

## Required feature-time lineage

Every feature block must provide a finite, row-aligned, monotonic
non-decreasing `feature_times` vector. Its timestamp may equal, but may never
exceed, the corresponding target timestamp. Missing, unknown, mismatched,
non-finite, non-monotonic, or future feature times fail closed before model
fitting. The exact vectors are included in the dataset checksum so the report
identity binds the causal forecasting boundary.

## Evidence status

Synthetic inputs remain `SYNTHETIC_DEMO_ONLY`. A non-synthetic held-out
log-loss improvement is `INCONCLUSIVE`, never `FORMAL_FORECAST_EVIDENCE`.
This package always serializes `formal_bayes_factor: null` and
`scientific_pass: false`.

The report carries an `adjudication` record describing missing null-model,
calibration, split-lock, and multiplicity declarations. Those declarations
are audit inputs, not authority: caller-supplied formal evidence, Bayes-factor,
or PASS metadata is recorded as ignored. An external independently validated
adjudication path is required before any stronger scientific claim can be
considered.

## Limitations

Proper scoring rules and deterministic null summaries are useful engineering
and methodological checks. They do not rule out hidden common drivers,
preprocessing artifacts, temporal smoothing, volume conduction, sampling
bias, or other alternative explanations. Predictive gain must not be read as
causality or a claim about neural, physiological, contemplative, or biological
mechanism.
