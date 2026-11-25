# Locked transition-forecasting ladder

This benchmark compares prospective prediction of a declared transition at
`t + Δt` using the locked ladder:

`PSD → PSD + pairwise FC → PSD + pairwise FC + triadic FC → PSD + pairwise FC + directed hypergraph`.

The primary outcome is held-out log loss, with Brier score and calibration
error reported alongside AUROC/AUPRC when class support is valid. Incremental
gain is `previous held-out log loss - current held-out log loss`. A model can
report positive predictive improvement without implying biological causation,
consciousness, liberation, mechanism, or ontology.

## Locking and leakage controls

The runner supports subject-held-out, session-held-out, and forward-time
splits. Hyperparameters are selected only on the nested validation partition;
the test partition is read once for final scoring. Scaling statistics are fit
on training rows only. Group overlap and future-window feature timestamps fail
closed. Subject identity is controlled by group-disjoint splitting rather than
test-visible subject indicators. Pairwise feature count and total feature
dimension are included as deterministic nuisance controls; arousal,
respiration, cardiac/autonomic measures, sampling rate, and window length are
used when supplied and reported as missing when unavailable.

## Evidence and nulls

The report includes label permutation, circular-time shift, block shuffle,
matched-variance, and matched-autocorrelation null comparisons. Positive
incremental gain is reported only when the current model beats the previous
model on locked held-out log loss. Otherwise the result is
`NO_INCREMENTAL_GAIN`. Synthetic runs are always `SYNTHETIC_DEMO_ONLY`.

Every report contains `formal_bayes_factor: null`, `scientific_pass: false`,
and `evidence_class: "forecast_benchmark"`. Missing feature blocks or class
support produce `INSUFFICIENT_DATA`; leakage produces `LEAKAGE_DETECTED`;
invalid payloads produce `INVALID_INPUT`; unresolved evidence is
`INCONCLUSIVE`.

The implementation consumes feature matrices supplied by upstream adapters. It
does not implement or relabel PSD, FC, triadic, topology, or hypergraph
semantics, download data, access networks, or make biological claims.
