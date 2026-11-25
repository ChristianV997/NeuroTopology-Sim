# Research-Cycle Release Evidence Evaluator

Read-only operational evaluator for research-cycle Batch 1 JSON exports.
It decides whether a cycle is **complete enough for human review**, without
declaring scientific truth.

| Artifact | Path |
| --- | --- |
| Package | `tools/research_cycle_release/` |
| CLI | `scripts/evaluate_research_cycle_release.py` |
| Tests | `tests/research_cycle_release/` |

## Integrity rules

- `EVIDENCE_READY_FOR_REVIEW` is **not** scientific PASS.
- Never emits a Bayes factor.
- Never promotes proxy results to causal evidence.
- Missing values remain unknown (`null`), never fabricated zero.
- Hardware-dependent metrics stay advisory unless comparability is proven.
- Does not modify or replace the scientific claim gate, ledger, artifact
  extractor, simulation runner, evidence graph writer, or performance-policy
  modules. Batch 1 outputs are consumed only through adapters.

## Decision states

- `EVIDENCE_READY_FOR_REVIEW`
- `EVIDENCE_INCOMPLETE`
- `PROVENANCE_FAILURE`
- `ARTIFACT_FAILURE`
- `VALIDATION_FAILURE`
- `RESOURCE_FAILURE`
- `NETWORK_POLICY_FAILURE`
- `SYNTHETIC_ONLY`
- `PROXY_ONLY`
- `SCIENTIFIC_REVIEW_REQUIRED`
- `INFRASTRUCTURE_BLOCKED`
- `NOT_COMPARABLE`

## Required checks

Source manifest, checksums, locked configuration, code commit, seed, input
provenance, finite outputs, terminal work units, explicitly marked partial
runs, artifact lineage, validation report, null/multiplicity metadata when
applicable, forecasting subject/session/time splits when applicable, resource
budgets, no full-dataset download, recorded network policy, consistent
synthetic/proxy/empirical classes, and no unsupported causal language in
report metadata.

## Adapters

- `generic` — canonical `research_cycle_release_bundle.v1`
- `awareness` — Awareness Studio compiler report JSON
- `registry` — research_cycle registry export JSON

## CLI

```bash
PYTHONPATH=. python scripts/evaluate_research_cycle_release.py \
  --input cycle_bundle.json \
  --output artifacts/research_cycle_release
```

Exit codes: `0` ready-for-review · `1` hard failure · `5` incomplete /
class-restricted / scientific-review · `2` bad input.
