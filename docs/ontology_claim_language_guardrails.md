# Ontology Claim Language Guardrails

## Purpose
Provide a repository-wide claim-language firewall for generated artifacts, docs, and reports.

## Why this exists
This guardrail prevents overclaiming from benchmark/runtime artifacts and keeps claim scope aligned with engineering evidence.

## Safe language
Use constrained wording such as engineering runtime validation, marker association, topology telemetry, bridge hypothesis, mechanism candidate, claim scope, falsifier, and alternative explanation.

## Forbidden phrases / Guardrails
Examples checked by the validator include overclaim patterns and direct metric-to-ontology shortcuts.

## Metric-to-ontology shortcut ban
Do not present metric deltas (AUC, q_net, q_abs, f_dress, topology, EEG) as proving ontology-level conclusions.

## State-label shortcut ban
Do not collapse operational labels into existential conclusions.

## Direct-equivalence ban
Do not assert direct equivalence between benchmark metrics and metaphysical constructs.

## How to run
`make ontology-language-check`

## How this complements the ontology evaluator
This validator blocks language overreach at repo level while ontology evaluation remains a separate evidence and bridge-governed lane.

## What it does not validate
It does not evaluate ontology correctness, scientific truth, real-data causal validity, or contract sufficiency.
