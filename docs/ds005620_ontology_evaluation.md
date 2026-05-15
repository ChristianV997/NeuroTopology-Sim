# DS005620 Ontology Evaluation

## DS005620-specific ontology bridge

The DS005620 mock-or-real benchmark exercises an explicit chain from Level
D (reviewed labels) through Level M (markers) and Level T (topology) to
proposed substrate / theory / ontology layers. The ontology evaluation
layer pins each artifact set to a claim scope so the benchmark cannot
silently expand its conclusions.

## M marker claims

- **What is allowed:** Level M markers associate with reviewed labels
  under controls, when real execution is present.
- **What is blocked:** any claim that Level M markers reflect internal
  experience, awareness, or ontological state.
- **Required evidence:** `features_m_signal_labeled.csv`,
  `label_alignment.csv`, `metrics_signal_mt.json`, controls
  (`leakage_report.json`, `artifact_report.json`).

## T topology residual claims

- **What is allowed:** Level T may show residual predictive value beyond
  Level M, conditional on nulls, ablations, leakage, and artifact controls.
- **What is blocked:** any claim that topology telemetry equals or implies
  consciousness, awareness, liberation, or other ontological content.
- **Required evidence:** `metrics_signal_mt.json`, `nulls.json`,
  `ablations.json`, `leakage_report.json`, `artifact_report.json`.

## C substrate claims

- **What is allowed:** a substrate mechanism may be articulated as a
  candidate, contingent on independent biophysical evidence.
- **What is blocked:** any substrate claim based on EEG benchmark
  performance alone.
- **Required evidence:** `independent_mechanism_evidence_packet.json`,
  `mechanism_controls.json`.

## Q theory claims

- **What is allowed:** findings may be discussed as theoretically
  consistent with the dynamical organization framework.
- **What is blocked:** theory promotion as empirical confirmation; theory
  promotion from theory alone.
- **Required evidence:** human review completed.

## O ontology candidate quarantine

- **Default state:** `ontology_quarantined` for every run mode.
- **Required for promotion:** independent dataset replication,
  independent mechanism evidence, evaluated alternatives, human review.
  Even then the evaluator does not promote ontology — it requires manual
  out-of-band review.

## Promotion/demotion rules

The evaluator never promotes ontology automatically. Demotion happens
whenever a required artifact or control becomes absent, when run mode
falls back to mock, or when human review is not marked completed.

## Example outputs

Running `make ds005620-ontology-eval-mock` against the existing mock E2E
artifacts produces:

```
outputs/btc_icft/ds005620_ontology_evaluation_mock/
  ontology_claim_evaluation.json     # full evaluation record
  claim_scope_matrix.json            # per-scope allowed/max_state/blockers
  bridge_claim_status.json           # per-bridge status (allowed / blocked)
  falsifier_status.json              # falsifier statuses (not_evaluated under mock)
  alternative_explanations.json      # alternative-explanation statuses
  ontology_promotion_decision.json   # final promotion decision
  omega_event.json                   # overclaim invariants (all false)
  report.md                          # human-readable summary
```

For mock E2E inputs:

- `max_claim_scope = engineering_runtime`
- `promotion_state = engineering_validated`
- `ontology_claim_status = ontology_quarantined`
- M / T empirical claims blocked pending real execution
- C / Q / O claims blocked pending controls and independent evidence

## Review checklist

When reviewing an ontology evaluation output:

1. Confirm `omega_invariants` are all `false`.
2. Confirm `ontology_claim_status` is `ontology_quarantined`.
3. Confirm no banned phrase appears in `report.md`.
4. Confirm `max_claim_scope` matches the evidence presented.
5. Confirm bridge B4 and B6 are reported as `quarantined`.
6. Confirm falsifiers and alternative explanations are explicit, not
   waved away.
