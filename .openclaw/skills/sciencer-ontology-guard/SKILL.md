# OpenClaw Skill: sciencer-ontology-guard

## Purpose

Monitors ontology claim scope and generated-language guardrails for all
ScienceR-Dsim dataset artifacts.

## What this skill inspects

- `claim_scope_cap` — always `"engineering_runtime"` for all datasets.
- `promotion_state` — always `"engineering_validated"` (never promoted).
- `ontology_quarantined` — always `true`.
- Generated-language scan output at `outputs/btc_icft/ds005620_generated_language_validation.json`.
- Ontology claim language validation at `outputs/btc_icft/ontology_claim_language_validation.json`.

## Safe commands

- `make ds005620-generated-language-check`
- `make ontology-language-check`
- `make validate-real-data-source-matrix`
- `python tools/validate_ontology_claim_language.py`

## What this skill never does

- Never promotes any dataset's ontology scope.
- Never weakens the language firewall.
- Never makes empirical claims from mock or planning outputs.
- Never marks any dataset as ready for empirical findings.

## Escalation

If a language violation or scope escalation is detected, the skill reports
`blocked_language_violation` and requires human review before any further
pipeline steps.
