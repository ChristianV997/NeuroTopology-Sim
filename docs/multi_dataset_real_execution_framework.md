# Multi-Dataset Real-Execution Framework (P22)

## 1. Purpose

P22 generalizes the DS005620 real-execution planning pattern (P18.3 / P20 / P21) into a registry-driven multi-dataset framework. For each registered dataset, the framework inspects local readiness, plans artifact preparation, computes per-dataset next actions, and preserves all manual real-data and human-review boundaries.

**Safe claim**: P22 generalizes the DS005620 real-execution planning pattern into a registry-driven multi-dataset framework that inspects local readiness, plans artifact preparation, computes next actions, and preserves manual real-data and human-review boundaries.

## 2. Planned datasets

| Dataset ID | Source | Generic supported | Dataset-specific executor |
|---|---|---|---|
| `DS005620` | OpenNeuro | yes | yes (P18.1) |
| `DS002094` | OpenNeuro | yes | no (not yet implemented) |
| `ds001787` | OpenNeuro | yes | no (not yet implemented) |
| `ds003969` | OpenNeuro | yes | no (not yet implemented) |
| `ds003816` | OpenNeuro | yes | no (not yet implemented) |
| `PhysioNet_GABA` | PhysioNet | yes | no (not yet implemented) |

All profiles live in `configs/btc_icft/multi_dataset_real_sources.json`.

## 3. How this copies the DS005620 pattern

The DS005620-specific operator (P20) and gate (P18.3) had three working invariants:

- A stage-by-stage artifact planner that emits manual commands for missing pieces.
- An execution gate that hardcodes `peer_review_confirmed_by_human=false` and `can_use_execute_flag=false`.
- An autonomous iteration loop that runs only safe planning/validation steps.

P22 lifts those three pieces into:

- `sciencer_d/btc_icft/runtime/generic_real_artifact_operator.py` — generic 11-stage operator.
- `sciencer_d/btc_icft/runtime/generic_real_execution_gate.py` — generic gate, same hardcoded invariants.
- `sciencer_d/btc_icft/runtime/multi_dataset_autonomous_iteration.py` — multi-dataset iteration runtime.

The DS005620-specific Makefile targets (`ds005620-real-artifact-plan`, `ds005620-real-execution-gate`, `ds005620-autonomous-iteration`) continue to work unchanged.

## 4. DS005620 fully-supported path

For DS005620, the generic operator and gate emit commands that use the existing DS005620-specific pipelines (`extract_mne_signal_blocks`, `run_eeg_level_m_signal`, `run_eeg_level_t_signal`, the materializer, and `run_ds005620_real_benchmark`). All outputs are routed to the existing legacy paths (`outputs/btc_icft/ds005620_*`) so PR #126 and earlier outputs continue to work.

## 5. Non-DS005620 generic path

For all other datasets:

- Generic per-stage planning is supported.
- Reader preflight, label-contract declaration tracking, metadata inspection, and gate static checks are all supported.
- Real data extraction (MNE, Level M/T) and real benchmark execution are **not** wired. Those stages are marked `blocked_dataset_specific_support_required`.
- The gate reports `dataset_specific_executor_available=false` and `next_action=implement_dataset_specific_executor`.

This is intentional: the framework does not pretend to support what it does not.

## 6. What remains dataset-specific

- Reviewed-contract materializer (only DS005620 has one wired today).
- MNE extraction (only DS005620 has a working pipeline today).
- Signal-block conversion (only DS005620 has a working pipeline today).
- Level M / Level T extractors (only DS005620 has working pipelines today).
- Real benchmark executor `run_ds005620_real_benchmark` (DS005620 only).

P22 does not implement these for other datasets. Each new dataset requires explicit, peer-reviewed pipeline work plus its own activation declaration.

## 7. Local data layout

| Dataset ID | Canonical local root candidates |
|---|---|
| `DS005620` | `data/DS005620`, `data/ds005620`, `inputs/DS005620`, `inputs/ds005620` |
| `DS002094` | `data/DS002094`, `data/ds002094`, `inputs/DS002094`, `inputs/ds002094` |
| `ds001787` | `data/ds001787`, `data/DS001787`, `inputs/ds001787`, `inputs/DS001787` |
| `ds003969` | `data/ds003969`, `data/DS003969`, `inputs/ds003969`, `inputs/DS003969` |
| `ds003816` | `data/ds003816`, `data/DS003816`, `inputs/ds003816`, `inputs/DS003816` |
| `PhysioNet_GABA` | `data/physionet_gaba`, `data/PhysioNet_GABA`, `inputs/physionet_gaba`, `inputs/PhysioNet_GABA` |

The framework resolves the first existing candidate. No automatic download.

## 8. Label contract requirements

Every dataset must have:

- A human-authored activation declaration at `<local_root>/<dataset_id>_activation_declaration.json`.
- A materialized P12 reviewed external contract.
- An explicit binary mapping (`explicit_label_column`, `positive_values`, `negative_values`).

Binary mapping **must be declared by a human**. The framework never infers labels from filenames, event labels, task labels, conditions, subject IDs, or metadata strings.

## 9. Reader requirements

The framework reuses `sciencer_d/btc_icft/io/eeg_reader_preflight.py`. Optional reader dependencies (`mne`, `wfdb`, `scipy`) are detected but never required. Without them, the framework reports `dependency_missing` rather than attempting any download.

## 10. Artifact operator requirements

The generic operator emits 11 stages:

1. `local_root`
2. `metadata`
3. `raw_eeg`
4. `label_contract_declaration`
5. `reviewed_contract` (materialized)
6. `reader_preflight`
7. `mne_extraction`
8. `canonical_signal_blocks`
9. `level_m_features`
10. `level_t_features`
11. `real_execution_gate`

For non-DS005620 datasets, stages 5 and 7–10 are marked `blocked_dataset_specific_support_required` until a dataset-specific executor is wired.

## 11. Real execution gate requirements

The generic gate keeps the same hardcoded invariants as P18.3:

- `peer_review_confirmed_by_human = false`
- `can_use_execute_flag = false`
- `can_use_peer_reviewed_contract_confirmed_flag = false`

It also adds `dataset_specific_executor_available` — `true` only for DS005620.

## 12. Autonomous iteration behavior

The multi-dataset iteration runs **safe per-dataset planning/inspection steps only**:

1. inspect local availability
2. inspect label adapter readiness
3. inspect reader readiness
4. run generic artifact planner
5. run generic real execution gate
6. (matrix is rebuilt after all steps)

Per dataset, one additional step `manual_real_execution` is always present with `status=manual_required` and is **never executed**.

## 13. Empirical readiness rules

Empirical readiness is **always blocked** in the default no-real-data state:

- No real execution completed → `blocked_no_real_execution`.
- Real execution completed but missing controls (`nulls.json`, `ablations.json`, `leakage_report.json`, `artifact_report.json`) → `blocked_missing_controls`.
- All controls + real execution → `ready_with_human_review`.

`empirical_claims_permitted` is hardcoded `false`. The framework never marks a dataset as ready to claim empirical findings.

## 14. Ontology scope rules

Every dataset, regardless of state:

- `claim_scope_cap = "engineering_runtime"`
- `promotion_state = "engineering_validated"`
- `ontology_quarantined = true`

The framework never promotes any dataset's claim scope. Ontology promotion requires real execution + controls + independent mechanism evidence + peer review, none of which the framework performs.

## 15. Commands

```bash
# Build the multi-dataset matrix:
make real-data-source-matrix

# Validate the matrix:
make validate-real-data-source-matrix

# Multi-dataset readiness loop (matrix + DS005620 planner + gate):
make multi-dataset-real-readiness

# Run safe multi-dataset autonomous iteration:
make multi-dataset-autonomous-iteration

# Dry-run only:
make multi-dataset-autonomous-iteration-dry-run
```

CLIs:

```bash
python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution \
    --out outputs/btc_icft/multi_dataset_real_execution

python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration \
    --out outputs/btc_icft/multi_dataset_autonomous_iteration
```

Options:
- `--dataset-id <id>` — limit to specific dataset (repeatable)
- `--sources <path>` — alternate manifest path
- `--dry-run` — plan-only (iteration CLI)
- `--json` — print JSON summary to stdout

## 16. Guardrails

All hardcoded `false`:

- `executes_real_data`
- `downloads_data`
- `auto_confirms_peer_review`
- `auto_runs_mne_extraction`
- `auto_runs_level_m_extraction`
- `auto_runs_level_t_extraction`
- `auto_runs_real_benchmark`
- `auto_declares_label_mapping`
- `infers_labels`
- `fabricates_targets`
- `weakens_p18_3_gate`
- `weakens_p20_operator`
- `weakens_p21_iteration`
- `weakens_ontology_quarantine`
- `weakens_language_firewall`

Forbidden command substrings are rejected at runtime:
`--execute --peer-reviewed-contract-confirmed`, `dandi download`, `openneuro download`, `wget`, `curl`, `aws s3 cp`.

## Outputs

`outputs/btc_icft/multi_dataset_real_execution/`:

- `dataset_source_matrix.json`
- `local_data_availability_matrix.json`
- `label_contract_readiness_matrix.json`
- `eeg_reader_readiness_matrix.json`
- `artifact_operator_matrix.json`
- `real_execution_gate_matrix.json`
- `autonomous_iteration_matrix.json`
- `empirical_readiness_matrix.json`
- `ontology_scope_matrix.json`
- `next_actions.json`
- `operator_report.md`

`outputs/btc_icft/multi_dataset_autonomous_iteration/`:

- `iteration_state.json`
- `iteration_plan.json`
- `iteration_results.json`
- `iteration_decision_log.json`
- `iteration_next_actions.json`
- `iteration_artifact_index.json`
- `iteration_report.md`
- `iteration_events.jsonl`

## What this framework never does

- Never downloads data.
- Never runs real DS005620 or any other dataset benchmark automatically.
- Never runs MNE extraction on real data automatically.
- Never runs Level M / Level T extraction on real data automatically.
- Never confirms peer review on behalf of a human.
- Never declares a binary label mapping.
- Never infers labels.
- Never fabricates targets.
- Never weakens P18.3, P20, or P21 guardrails.
- Never weakens ontology quarantine or language firewall.
- Never emits empirical claims from local data presence or mock E2E.
- Never promotes any dataset's ontology scope.
