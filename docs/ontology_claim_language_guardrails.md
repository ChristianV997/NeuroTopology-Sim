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

## Baseline-aware validation
Run `make ontology-language-check` for stable repo-gate behavior. This mode loads `contracts/btc_icft/ontology_claims/claim_language_baseline.json` and allows only explicitly listed legacy findings.

## Strict generated-output validation
Run `make ontology-language-check-strict-outputs` to scan outputs with no baseline waivers. Any unsafe language in generated artifacts fails this check.

## How to add a temporary waiver
1. Run `make ontology-language-baseline-candidate`.
2. Copy only justified legacy entries into the canonical baseline contract.
3. Set a concrete reason and owner for each entry.

## How to remove a waiver
1. Fix the source text.
2. Remove the corresponding baseline entry.
3. Re-run baseline-aware and strict checks.

## Why generated artifacts should not be baselined
Generated evidence/report/paper artifacts must reflect current safe claim-language behavior. Fix generators/templates instead of waiving unsafe output.

## CI behavior
The workflow uses baseline-aware repo scan so existing known legacy findings do not destabilize CI, while new unwaived findings still fail.

## Cleanup policy
Baseline entries are temporary governance debt. Every entry must include reason, owner, and planned cleanup tracking.

## How this complements the ontology evaluator
This validator blocks language overreach at repo level while ontology evaluation remains a separate evidence and bridge-governed lane.

## What it does not validate
It does not evaluate ontology correctness, scientific truth, real-data causal validity, or contract sufficiency.

## DS005620 generated-output profile
Use `make ds005620-generated-language-check` to enforce strict generated-output language validation for DS005620 artifacts only. This runs `scan-mode generated` with `--generated-output-profile ds005620`, scans only DS005620 generated output roots, skips missing roots, and writes JSON/Markdown reports.

## Publication package readiness
This gate protects generated evidence packets, CI evidence reports, and paper skeleton outputs by failing unsafe claim language before publication-facing artifacts are consumed downstream.

## Fixing generated template failures
If this gate fails, edit the generator/template text that emitted unsafe language and regenerate artifacts. Do not add baseline waivers for generated artifacts.
