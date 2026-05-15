# DS005620 Real Artifact Build Operator (P20)

P20 adds a deterministic real artifact build operator that plans DS005620 local
artifact preparation without executing real data or weakening label, target,
ontology, or language guardrails.

## What this operator does

- Inspects all prerequisite artifact paths for a real DS005620 run.
- Determines which stages are complete, missing, or require manual action.
- Emits exact commands for each missing stage (for operator reference only).
- Writes 6 output files summarizing the plan, stage status, next action, and
  required paths.
- Reports the next priority action for the operator to take.

## What this operator does NOT do

- Does NOT execute real DS005620 data.
- Does NOT download any data.
- Does NOT infer labels or fabricate targets.
- Does NOT confirm peer review on behalf of a human.
- Does NOT weaken the P18.3 execution gate, ontology quarantine, or language
  guardrails.
- Does NOT auto-run any pipeline command.
- Does NOT modify contracts or activation declarations.

## Usage

```bash
# Run with default paths (writes to outputs/btc_icft/ds005620_real_artifact_operator/):
make ds005620-real-artifact-plan

# Run artifact plan + P18.3 execution gate check:
make ds005620-real-readiness-loop

# CLI directly:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts

# With JSON summary:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts --json

# Strict mode (exit nonzero if any stage is incomplete):
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts --strict
```

## Artifact stages (in order)

| Stage ID | Description | Manual? | Executes real data? |
|---|---|---|---|
| `metadata` | DS005620 events.tsv | Yes | No |
| `raw_eeg_root` | Raw EEG files directory | Yes | No |
| `reviewed_contract_source` | Human-authored activation declaration | Yes (+ human review) | No |
| `reviewed_contract_materialized` | P12 reviewed external contract | No (+ human review) | No |
| `eeg_reader_preflight` | EEG reader preflight output | No | Yes |
| `mne_extraction` | MNE signal extraction output | No | Yes |
| `canonical_signal_blocks` | Canonical signal blocks (P19.2) | No | Yes |
| `level_m_features` | Level M signal features CSV | No | Yes |
| `level_t_features` | Level T topology features CSV | No | Yes |
| `real_execution_gate` | P18.3 real/local execution gate output | No (+ human review) | No |

## Output files

All outputs are written to `outputs/btc_icft/ds005620_real_artifact_operator/`:

| File | Contents |
|---|---|
| `real_artifact_build_plan.json` | Full plan with stages, commands, guardrails, next action |
| `real_artifact_stage_status.json` | Compact stage status summary |
| `real_artifact_next_command.json` | The single next action and command |
| `real_artifact_required_paths.json` | All expected paths with status |
| `real_artifact_commands.sh` | Operator command guide (review before running) |
| `real_artifact_operator_report.md` | Human-readable operator report |

## Next-action priority order

1. `provide_metadata` — place events.tsv
2. `provide_raw_eeg` — place raw EEG files
3. `prepare_reviewed_contract_declaration` — author activation declaration
4. `run_reviewed_contract_materializer` — materialize P12 contract
5. `run_eeg_reader_preflight` — run EEG reader preflight
6. `run_mne_extraction` — run MNE extraction
7. `run_signal_block_conversion` — run signal block conversion
8. `run_level_m_signal` — run Level M feature extraction
9. `run_level_t_signal` — run Level T feature extraction
10. `run_real_execution_gate` — run P18.3 gate check
11. `follow_real_execution_gate_next_action` — follow gate instructions
12. `human_peer_review_required` — human peer review before real execution

## Relation to P18.3 execution gate

After all prerequisite artifact stages are complete, the operator must run
the P18.3 gate (`make ds005620-real-execution-gate`). The gate produces a
`human_peer_review_checklist.md` and a manual real execution command.

**Human peer review is always required and is never auto-confirmed.**

The operator must inspect the gate outputs and the peer review checklist
before manually running any real execution command.

## Config reference

See `configs/btc_icft/ds005620_real_artifact_operator.json` for all default
paths, guardrails, and stage IDs.

## Guardrails

All guardrails are hard-coded `false` and are included in every plan output:

```json
{
  "executes_real_benchmark": false,
  "downloads_data": false,
  "executes_real_data_automatically": false,
  "auto_confirms_peer_review": false,
  "infers_labels": false,
  "fabricates_targets": false,
  "modifies_p18_3_gate": false
}
```
