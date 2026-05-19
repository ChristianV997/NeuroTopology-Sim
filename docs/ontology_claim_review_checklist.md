# Ontology Claim Review Checklist

Use this checklist when reviewing ontology-aware claim proposals. Complete each section before assigning a promotion decision.

## Claim text

- Proposed claim text is included verbatim.
- Claim language matches the submitted evidence state.

## Claimed layer

- Layer is declared as one of D/M/T/C/Q/O/Ω.
- Layer declaration is consistent with claim content.

## Claimed scope

- Scope is declared as one of: engineering_runtime, marker_association, topology_residual, mechanism_candidate, theory_consistency, ontology_candidate, blocked_overreach, rejected.
- Scope declaration is consistent with the layer and requested promotion.

## Evidence root

- Dataset/run ID is declared.
- Execution root is declared.
- Evidence packet path is declared and accessible.

## Required artifacts

- Validation summary is present.
- Contract validation output is present.
- Artifact report is present.
- Leakage report is present when predictive interpretation is requested.

## Required controls

- Null controls are documented.
- Ablations are documented when contribution claims are requested.
- Real execution artifacts are present for empirical candidate promotion.

## Human review status

- Human-reviewed contract status is explicitly documented.
- Any missing human review is linked to a blocking decision.

## Alternative explanations

- At least one plausible alternative explanation is listed.
- Alternatives are specific enough for targeted follow-up testing.

## Falsifiers

- At least one falsifier is listed.
- Falsifiers are concrete and testable.

## Allowed language

- Uses bounded wording (engineering validation, candidate, consistency, quarantine).
- Distinguishes runtime validation from empirical evidence.
- Distinguishes empirical evidence from ontology-level interpretation.

## Blocked language

- No metric-to-ontology shortcut.
- No state-label shortcut.
- No direct equivalence claims linking topology metrics to self/soul/experience/suffering.
- No metaphysical proof wording.
- No empirical support claim from mock E2E.
- No O-layer promotion from EEG/topology metrics alone.

## Reviewer decision

Choose one:

```text
approve_engineering_claim
approve_marker_candidate
approve_topology_candidate
block_pending_real_execution
block_pending_controls
block_pending_human_review
quarantine_C_Q_O_claim
reject_overreach
```

## Required changes

- List mandatory edits required before merge or publication promotion.
- Link each required change to the missing evidence, control, or language guardrail.
