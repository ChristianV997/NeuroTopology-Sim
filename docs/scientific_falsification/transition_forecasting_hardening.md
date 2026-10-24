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
fitting. The dataset checksum binds all feature/target arrays, feature-time
lineage, controls, prediction horizon, target definition, provenance, source
mode, and adjudication metadata. The report checksum is the SHA-256 of the
complete serialized report (including that dataset checksum, split, results,
null summaries, and adjudication fields), so resume/cache identity changes
when report-affecting inputs or outputs change.

## Evidence status

Synthetic inputs remain `SYNTHETIC_DEMO_ONLY`. A non-synthetic held-out
log-loss improvement is `INCONCLUSIVE`, never `FORMAL_FORECAST_EVIDENCE`.
This package always serializes `formal_bayes_factor: null` and
`scientific_pass: false`.

The report carries an `adjudication` record describing missing null-model,
calibration, split-lock, and multiplicity declarations. Those declarations
are audit inputs, not authority: caller-supplied formal evidence, Bayes-factor,
or PASS metadata is recorded as ignored. Empty sequences, and mappings whose
leaves are all empty or unknown (for example `{"families": []}`), count as
missing requirements, not as supplied adjudication. An external independently validated
adjudication path is required before any stronger scientific claim can be
considered.

AUROC is computed from average ranks, so tied prediction scores receive equal
rank contribution. AUPRC groups equal prediction scores at one threshold so
row order within a tied group does not change average precision. These are
benchmark metrics only and do not change the evidence-status boundary.

## Limitations

Proper scoring rules and deterministic null summaries are useful engineering
and methodological checks. They do not rule out hidden common drivers,
preprocessing artifacts, temporal smoothing, volume conduction, sampling
bias, or other alternative explanations. Predictive gain must not be read as
causality or a claim about neural, physiological, contemplative, or biological
mechanism.
