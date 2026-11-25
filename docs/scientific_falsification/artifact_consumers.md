# Falsification artifact consumer migration

This document defines the adapter boundary for falsification reports emitted
to dashboard/export consumers. It is additive: `RunRecordV1` remains the
canonical run-record contract, and the existing
`PITNN.DSIM.Falsification.v1` artifact schema remains available.

## Evidence semantics

The current PITNN comparison is an exploratory proxy regression. A number
called `bayes_factor` in a legacy report is not formal evidence by itself.
Formal evidence must identify an explicit marginal-likelihood method and a
finite `formal_bayes_factor`.

The adapter emits these semantic fields on every falsification payload:

| Field | Meaning |
| --- | --- |
| `evidence_method` | Declared method, such as `bic_proxy` or `formal_marginal_likelihood`; unknown methods stay unknown. |
| `proxy_bayes_factor` | Numeric information-criterion/regression proxy, when available. It is never formal `K`. |
| `formal_bayes_factor` | Numeric formal `K`, only for a recognized formal method; otherwise `null`. |
| `bayes_factor_legacy_compatibility` | Deprecation metadata and the preserved numeric value for old readers. |
| `verdict` | `PASS`, `NOT_SUPPORTED`, `INCONCLUSIVE`, or `ERROR` after the consumer gate is applied. |
| `scientific_eligibility` | Boolean indicating that all formal PASS gates are satisfied. |
| `synthetic_demo` | Whether the report is synthetic, fixture, null, or surrogate data. |
| `empirical_provenance` | Provenance details plus `status: complete` or `status: incomplete`. |
| `sample_count` / `effective_sample_count` | Declared sample sizes; missing values remain `null`. |
| `null_control_status` | Explicit null/control state; missing controls are `not_provided`. |
| `multiplicity_status` | Multiple-comparison state; unknown is not silently treated as one test. |
| `model_comparison_status` | `formal`, `proxy_regression`, `unsupported`, or `unknown`. |
| `reason_codes` | Deterministic machine-readable explanation of the classification. |

`bayes_factor` remains a numeric compatibility alias when the source supplied
one. Consumers must read `formal_bayes_factor` and `evidence_method` instead.
If the source value is non-finite or unavailable, the compatibility value is
`null`; JSON never contains NaN or Infinity.

## Verdict rules

- `PASS` requires a finite formal `K > 100`, empirical data, complete
  provenance, a declared effective sample count of at least eight, passing
  controls, known multiplicity handling, and a supported/interpretable formal
  model comparison.
- A proxy value, including a proxy value above 100, produces
  `NOT_SUPPORTED` and `formal_bayes_factor: null`.
- Synthetic, fixture, null, and surrogate data cannot produce `PASS`.
- Incomplete empirical provenance, an unknown evidence method, missing gates,
  or unsupported comparison produce `INCONCLUSIVE`.
- Contract/execution failures produce `ERROR`.

The adapter never recalculates, clips, inflates, or rescales a Bayes factor.
The `K > 100` condition is strict: `K == 100` is not a pass.

## Before and after

Legacy input:

```json
{
  "bayes_factor": 250.0,
  "verdict": "PASS",
  "source_kind": "synthetic_demo"
}
```

The migrated artifact preserves the numeric field for compatibility, but
rejects the unsafe verdict and makes the evidence boundary explicit:

```json
{
  "schema": "PITNN.DSIM.Falsification.v1",
  "bayes_factor": 250.0,
  "bayes_factor_legacy_compatibility": {
    "value": 250.0,
    "status": "deprecated_numeric_compatibility_alias",
    "deprecated": true,
    "interpretation": "unknown"
  },
  "evidence_method": "unknown_legacy_numeric",
  "proxy_bayes_factor": null,
  "formal_bayes_factor": null,
  "verdict": "NOT_SUPPORTED",
  "scientific_eligibility": false,
  "synthetic_demo": true,
  "reason_codes": [
    "SYNTHETIC_DATA",
    "SYNTHETIC_PASS_REJECTED",
    "UNKNOWN_EVIDENCE_METHOD"
  ]
}
```

For a known regression proxy, the preserved value is explicitly labelled:

```json
{
  "evidence_method": "bic_proxy",
  "proxy_bayes_factor": 250.0,
  "formal_bayes_factor": null,
  "verdict": "NOT_SUPPORTED",
  "scientific_eligibility": false,
  "reason_codes": ["PROXY_ONLY", "FORMAL_BAYES_FACTOR_UNAVAILABLE"]
}
```

## RunRecordV1 relationship

The falsification payload is a nested artifact/metric payload. It is not a new
run-record schema. Pipelines that record it in `RunRecordV1.metrics` continue
to use `RunRecordV1.to_dict()`/`from_dict()` and the existing artifact paths.
The adapter only adds semantic keys to the existing PITNN falsification
payload.

## Raw data, derived metrics, and topology

Raw arrays remain separate binary artifacts (for example, NPZ files) and JSON
contains scalar metadata and binary references. Derived RSS, AICc, BIC, proxy
ratios, and verdicts are not raw measurements and must retain their provenance.

Topology observables remain separate: graph beta-1 (cycle rank), spatial
winding, spatial topological charge, and scalar chirality are not aliases and
are never converted into one another by this consumer layer.

## Synthetic-data and optional-dependency limits

Synthetic data is useful for deterministic tests and calibration only. It is
not empirical evidence and cannot support a scientific `PASS`. The consumer
layer performs no network access, dataset download, solver execution, or
optional dependency discovery. Missing or incomplete evidence is represented
explicitly in the payload rather than silently upgraded.
