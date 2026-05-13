# DS005620 Review Governance

## Claim firewall

- Keep claims constrained to tooling/governance/runtime status unless required controls exist.
- Reject any wording that overstates scientific meaning from mock or incomplete artifacts.
- Require explicit evidence-state labeling (exploratory, blocked, benchmark-gated).

## Label/target firewall

- No label inference, filename-derived labels, topology-derived labels, or artifact-derived labels.
- No target fabrication or implicit promotion from partial outputs.
- Any P12/P13 touching PR must state exact source columns and mapping limits.

## Runtime execution firewall

- PRs touching execution paths must state whether impact is mock-only, real/local, or CI-only.
- No automatic real-contract activation.
- No edits that bypass required benchmark or declaration gates.

## Mock E2E vs real/local distinction

- Mock E2E validates pipeline wiring and artifact flow only.
- Real/local execution requires explicit local prerequisites and reviewed contract gates.
- Mock success is never sufficient for empirical promotion.

## When benchmark artifacts can be promoted

- Promotion requires complete benchmark gate success plus declared controls.
- Promotion requires clear provenance for generated artifacts and validation outputs.
- Promotion is blocked when guardrails or contract checks are incomplete.

## Required control artifacts before empirical claims

- Null/control comparison outputs.
- Ablation outputs where applicable.
- Leakage review status and artifact references.
- Validator summaries for execution and contract compliance.

## Reviewer checklist

- Confirm phase and scope declarations are complete.
- Confirm execution-path impact disclosure is complete.
- Confirm guardrail checklist has no unchecked critical items.
- Confirm tests-run section includes governance + btc_icft commands.
- Confirm claims stay within reviewed evidence state.
