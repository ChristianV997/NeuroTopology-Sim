# Empirical readiness audit

Read-only gate between local files and any later statistical or evidence
review. A readable header or checksum is not independent empirical
validation. Synthetic input cannot PASS.

Owned files:

- `analysis/empirical_readiness/**`
- `scripts/validate_empirical_readiness.py`
- `tests/empirical_readiness/**`
- `docs/scientific_falsification/empirical_readiness.md`

This layer does not modify provenance contracts, adapters, cohort
manifests, or Bayesian falsification.

## States

- `READY_FOR_DESCRIPTIVE_ANALYSIS`
- `READY_FOR_PAIRED_STATISTICS`
- `READY_FOR_FORMAL_EVIDENCE_REVIEW`
- `INSUFFICIENT_PAIRED_SUBJECTS`
- `INCOMPLETE_PROVENANCE`
- `INVALID_INPUT`
- `SYNTHETIC_DEMO_ONLY`
- `MISSING_OPTIONAL_DEPENDENCY`
- `UNSUPPORTED_SAMPLING_RATE`

Descriptive readiness is not formal-evidence eligibility.

## Paired-cohort rules

Default minimum: 8 paired subjects.

A paired subject has one `subject_id` and at least two explicit
`condition_label` values, either in `cohort.pairs[].conditions` or
across recordings. Labels are not inferred.

## Formal-evidence eligibility

Requires all of:

- every recording `origin=empirical_local`
- local non-empty files and declared checksums
- explicit condition labels
- sampling rate with Nyquist above the requested band
- channel count at or above the configured minimum (default 8)
- known montage and units
- recorded preprocessing, TDA configuration, null controls, and
  multiple-comparison policy
- at least 8 paired subjects

This evaluator does not compute K, run TDA, or claim biological support.
