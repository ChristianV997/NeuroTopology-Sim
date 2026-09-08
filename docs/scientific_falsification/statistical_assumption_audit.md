# Statistical assumption audit

This note describes `analysis/statistical_assumptions` and
`scripts/audit_statistical_assumptions.py`. The auditor reviews
declared reports. It does not recompute statistics, does not modify
`sim/pitnn/bayesian_falsification.py`, and does not emit a scientific
`PASS`.

## Inputs

A spec object names explicit sources. Each source is a path or an
inline JSON object:

- `cohort_statistics`
- `null_calibration`
- `preregistration`

Optional `formal_bayes_factor_supply` is recorded only when
`formally_valid` is true. Otherwise `formal_bayes_factor` remains
`null`.

## Outcomes

`AUDIT_CLEAN`, `AUDIT_INCOMPLETE`, `AUDIT_INVALID_INPUT`,
`AUDIT_INSUFFICIENT_POWER`, `AUDIT_MULTIPLICITY_UNRESOLVED`,
`AUDIT_NULL_MODEL_UNRESOLVED`, `AUDIT_SYNTHETIC_ONLY`,
`AUDIT_SCIENTIFIC_REVIEW_REQUIRED`.

`AUDIT_CLEAN` is internal consistency only. It is not evidence of
consciousness, meditation, propofol mechanism, quantum coherence,
exceptional points, or a biological topological phase.

Every report sets `scientific_pass=false` and
`evidence_class="statistical_assumption_audit"`.

## CLI

```text
python scripts/audit_statistical_assumptions.py \
  --input spec.json \
  --output assumption_audit.json
```
