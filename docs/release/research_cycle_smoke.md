# Research-Cycle End-to-End Smoke Harness

Deterministic, local-only acceptance harness covering the research-cycle path
from source/manifest through release-evidence decision.

| Artifact | Path |
| --- | --- |
| Package | `tools/release_readiness/research_cycle_smoke/` |
| CLI | `scripts/run_research_cycle_smoke.py` |
| Tests | `tests/release_readiness/research_cycle_smoke/` |

## Integrity rules

- Synthetic fixtures are **engineering acceptance evidence**, not empirical neuroscience.
- Never emits scientific PASS or a Bayes factor.
- Never promotes proxy/synthetic results to causal evidence.
- Missing metrics remain `null`, never fabricated `0`.
- No network / no full-dataset download.
- Does **not** modify production semantics of ledger, claim-gate, solvers, or Awareness Studio.

## Scenarios

1. `complete_valid_engineering`
2. `incomplete_source`
3. `partial_subject_set`
4. `failed_simulation`
5. `timeout`
6. `missing_validation_report`
7. `invalid_provenance`
8. `network_policy_violation`
9. `synthetic_only`
10. `proxy_only`

Each fixture builds the chain
`source → plan → hypothesis → experiment → run → artifact → validation → evidence_graph`
and maps it onto the canonical `research_cycle_release` bundle, then calls
`evaluate_research_cycle_release`.

## CLI

```bash
PYTHONPATH=. python scripts/run_research_cycle_smoke.py \
  --output artifacts/research_cycle_smoke
```

Exit `0` when all decisions match and guards pass; otherwise `1`.
