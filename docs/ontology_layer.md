# Ontology Claim Evaluation Layer (O1-O3)

## Purpose

This layer is a machine-checkable claim-validity firewall sitting on top of
the DS005620 benchmark runtime. It prevents engineering metrics from being
interpreted as empirical, mechanism, theory, or ontology conclusions.

It does **not** add a new scientific result. It adds a structured gate that
keeps benchmark outputs in the right epistemic lane.

## Why an ontology layer matters

The benchmark stack can produce metrics that look conclusive. Without a
formal scope gate, downstream readers may infer more than the evidence
warrants. The ontology layer:

- separates engineering runtime validation from empirical promotion;
- separates empirical association from mechanism candidacy;
- separates mechanism candidacy from theory consistency;
- holds ontology candidates in quarantine by default.

## Layers

| Layer | Symbol | Role |
|---|---|---|
| Phenomenology / behavioral context | `D_PHENOMENOLOGY` | Reviewed labels stand in for behavioral context for benchmark purposes only |
| Marker | `M_MARKER` | Level M features computed from signals |
| Topology telemetry | `T_TOPOLOGY` | Level T features and residual predictive value |
| Substrate mechanism | `C_SUBSTRATE` | Candidate mechanisms requiring independent biophysical evidence |
| Theory construct | `Q_THEORY` | Dynamical organization framework, theory consistency only |
| Ontology candidate | `O_ONTOLOGY_CANDIDATE` | Always quarantined unless multiple independent evidence families converge |
| Governance / evidence | `OMEGA_GOVERNANCE` | Omega invariants and overclaim tripwires |

## Claim scopes

- `engineering_runtime` — pipeline orchestration validated, no empirical claim
- `marker_association` — Level M associates with reviewed labels under controls
- `topology_residual` — Level T shows residual predictive value beyond Level M
- `mechanism_candidate` — substrate mechanism articulated as a candidate
- `theory_consistency` — findings discussed as theoretically consistent
- `ontology_candidate` — articulated and quarantined; never promoted
- `blocked_overreach`, `rejected` — explicit failure scopes

## Bridge claims

A bridge claim formalizes what may be asserted between two layers and what
artifacts/controls/falsifiers are required to promote the bridge.

The bridge registry lives at
`configs/btc_icft/ontology_bridge_registry.json`. Initial bridges:

- `B1_M_MARKERS_TO_REVIEWED_LABELS` (M → D)
- `B2_T_RESIDUAL_OVER_M` (T → M)
- `B3_DYNAMICAL_ORGANIZATION_CANDIDATE` (T → Q)
- `B4_NO_DIRECT_CONSCIOUSNESS_EQUIVALENCE` (T → O, always quarantined)
- `B5_SUBSTRATE_MECHANISM_REQUIRES_INDEPENDENT_EVIDENCE` (C → Q)
- `B6_ONTOLOGY_REMAINS_QUARANTINED` (Q → O, always quarantined)

## Falsifiers

Each bridge enumerates concrete falsifiers (e.g. "T contribution disappears
under label shuffle null"). Until real execution and controls are present
these are reported as `not_evaluated`; with real data they become
`pending_evaluation` and downstream control pipelines should resolve them.

## Alternative explanations

Bridges list alternative explanations (artifact dominance, class imbalance,
metadata leakage, etc.) that must be ruled out before promotion. The
evaluator reports them with the same status semantics as falsifiers.

## Evidence requirement matrix

`contracts/btc_icft/ontology_claims/evidence_requirement_matrix.json`
encodes, per scope, the required artifacts, controls, nulls, ablations,
reviewed-labels gate, controls gate, human review, and independent
dataset/mechanism evidence requirements.

## What mock E2E can say

- `max_claim_scope = engineering_runtime`
- `promotion_state = engineering_validated`
- ontology candidate remains quarantined
- M / T empirical claims are blocked pending real execution
- C / Q / O claims are blocked pending controls and independent evidence

## What real execution can say

Real execution + reviewed labels + complete controls + human review can
promote M and T to `empirical_candidate`. The ontology layer never promotes
beyond that without independent dataset replication and independent
mechanism evidence.

## What controls are required

`nulls.json`, `ablations.json`, `leakage_report.json`, `artifact_report.json`
must all be present in the controls root for `topology_residual` to be
promotable. The bridge registry documents per-bridge requirements.

## What remains quarantined

Ontology candidates and metaphysical claims remain quarantined for every
run mode the evaluator currently understands. No path through the evaluator
produces an ontology proof state.

## Publication package integration

Authors should run `make ds005620-ontology-check` to materialize the
ontology evaluation outputs alongside the evidence packet and paper
skeleton, and cite `ontology_claim_evaluation.json`,
`claim_scope_matrix.json`, and `report.md` in the methods/limitations
sections.

## Commands

```bash
# Run ontology evaluation against the existing mock E2E artifacts.
make ds005620-ontology-eval-mock

# Run the full mock chain: mock E2E -> evidence -> ontology evaluation.
make ds005620-ontology-check

# Run ontology tests only.
make ds005620-test-ontology
```
