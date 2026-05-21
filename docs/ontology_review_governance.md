# Ontology Review Governance

## 1. Purpose

This document defines review governance for ontology-aware claim handling in ScienceR-Dsim. Its purpose is to ensure claims are scoped to available evidence and that publication language remains defensible, reproducible, and safe.

## 2. Why ontology governance exists

Runtime pipelines can produce valid artifacts even when scientific interpretation is not yet justified. Governance exists to prevent claim overreach, require explicit evidence states, and keep interpretation aligned with documented controls and review decisions.

## 3. Runtime validation vs empirical evidence

Runtime validation confirms that code paths, contracts, and artifact generation execute as expected. Empirical evidence requires real execution outputs, controls, and reviewed interpretation constraints. Passing runtime checks alone is not empirical support.

## 4. Empirical evidence vs ontology claims

Empirical evidence supports bounded statements about observed data and model behavior. Ontology claims introduce broader interpretive commitments and require stronger, independent evidence families. Evidence for a metric pattern is not, by itself, evidence for ontology-level conclusions.

## 5. D/M/T/C/Q/O/Ω layer definitions

- **D (phenomenology/context):** contextual framing, task conditions, and protocol-level descriptions.
- **M (marker):** marker-level associations and measured feature summaries.
- **T (topology telemetry):** topology-derived telemetry and residual measurements.
- **C (substrate/mechanism candidate):** candidate mechanism interpretations requiring independent mechanism evidence.
- **Q (theory construct):** theory-consistency statements; coherence checks, not empirical proof.
- **O (ontology candidate):** ontology-candidate interpretations subject to strict quarantine by default.
- **Ω (governance/evidence state):** claim state, review state, and promotion readiness metadata.

## 6. Claim scope definitions

- **engineering_runtime:** execution and contract behavior only.
- **marker_association:** marker-level candidate association claims.
- **topology_residual:** residual topology candidate claims.
- **mechanism_candidate:** mechanism-level candidate claims.
- **theory_consistency:** consistency with a theoretical frame.
- **ontology_candidate:** ontology-level candidate statements.
- **blocked_overreach:** claim identified as overreach pending rewrite.
- **rejected:** claim not acceptable for current evidence state.

## 7. Promotion states

- `approve_engineering_claim`
- `approve_marker_candidate`
- `approve_topology_candidate`
- `block_pending_real_execution`
- `block_pending_controls`
- `block_pending_human_review`
- `quarantine_C_Q_O_claim`
- `reject_overreach`

Promotion state must be recorded in review artifacts and linked to evidence paths.

## 8. Required evidence by claim type

- **Engineering runtime claims:** contract/validator outputs and reproducible execution logs.
- **M/T empirical candidate claims:** real execution artifacts plus null controls, ablations where relevant, leakage review, artifact report, and human-reviewed label contract.
- **C claims:** all M/T requirements plus independent mechanism evidence.
- **Q claims:** explicit statement that claims are theory-consistency only and not empirical proof.
- **O claims:** remain quarantined unless independent evidence families converge.

Mock E2E supports engineering-runtime claims only.

## 9. Alternative explanations

Every empirical candidate claim must include plausible alternatives. Alternatives must be specific enough for reviewers to evaluate whether controls and analyses materially reduce competing interpretations.

## 10. Falsifiers

Every empirical candidate claim must list concrete falsifiers. Falsifiers should describe observations or test outcomes that would weaken or refute the claim under review.

## 11. Reviewer workflow

1. Confirm claim text, layer, and scope classification.
2. Verify evidence packet paths and execution provenance.
3. Verify controls, ablations, leakage report, and artifact report status.
4. Confirm human-reviewed contract status for target-linked claims.
5. Check alternative explanations and falsifiers.
6. Apply allowed-language guardrails and remove blocked wording.
7. Record a promotion-state decision and required follow-up actions.

## 12. Merge-blocking conditions

- Claim scope/layer is missing or inconsistent.
- Required evidence paths are absent.
- Required controls are missing for the requested promotion.
- Claim language exceeds evidence state.
- C/Q/O claims are presented as promoted empirical findings.
- Mock E2E outputs are used as empirical support.

## 13. Publication-blocking conditions

- Publication package lacks evidence packet, artifact manifest, or claim decision record.
- Null controls, ablations, leakage report, or artifact report are undocumented when required.
- Human-reviewed contract status is missing for target-linked claims.
- Limitations, reproducibility commands, or claim scope matrix are missing.
- Quarantine conditions for C/Q/O are not preserved.

## 14. Safe language

Use bounded wording such as:

- "engineering validation"
- "marker-level candidate association"
- "topology telemetry pattern"
- "mechanism candidate requiring independent evidence"
- "theory-consistency interpretation"
- "ontology candidate remains quarantined"

## 15. Guardrails

- No metric-to-ontology shortcut.
- No state-label shortcut.
- No direct equivalence between topology metrics and self/soul/experience/suffering.
- No metaphysical proof claim.
- No empirical claim from mock E2E.
- No O-layer claim promoted from EEG metrics alone.
