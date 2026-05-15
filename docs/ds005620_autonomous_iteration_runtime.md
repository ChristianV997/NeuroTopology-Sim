# DS005620 Autonomous Iteration Runtime (P21)

## Purpose

P21 adds a safe autonomous iteration runtime that executes mock/planning/validation steps, records decisions, and stops at manual real-data or human-review boundaries.

It is a single controller that coordinates all existing safe DS005620 pipeline steps in the correct order, logs every decision, and emits the next required action to a human operator.

## Why this exists

After P18.1 (mock E2E), P18.3 (real execution gate), and P20 (real artifact build operator), the system had all the components to run end-to-end mock validation and plan real artifact preparation. But running those steps required the operator to manually invoke many Makefile targets in the correct order.

P21 replaces that manual coordination with a single safe loop:

```bash
make ds005620-autonomous-iteration
```

Or for planning only (no command execution):

```bash
make ds005620-autonomous-iteration-dry-run
```

## Safe autonomous steps

The loop executes these steps automatically (all have `safe_to_auto_run=true`):

| Step ID | Command | Executes real data? |
|---|---|---|
| `ds005620_e2e_mock` | `make ds005620-e2e-mock` | No |
| `validate_e2e` | `make validate-ds005620-e2e` | No |
| `validate_e2e_json` | `make validate-ds005620-e2e-json` | No |
| `validate_contracts` | `make validate-ds005620-contracts` | No |
| `ci_evidence_report` | `make ds005620-ci-evidence-report` | No |
| `artifact_manifest` | `make ds005620-build-manifest` | No |
| `ontology_eval` | `make ds005620-ontology-eval-mock` | No |
| `evidence_export` | `make ds005620-export-evidence` | No |
| `paper_skeleton` | `make ds005620-paper-skeleton` | No |
| `runtime_inspection` | `make ds005620-inspect-runtime` | No |
| `generated_language_check` | `make ds005620-generated-language-check` | No |
| `real_local_preflight` | `make ds005620-preflight` | No |
| `real_artifact_plan` | `make ds005620-real-artifact-plan` | No |
| `real_execution_gate` | `make ds005620-real-execution-gate` | No |

## Manual blocked steps

The following step is always blocked from automatic execution:

| Step ID | Reason |
|---|---|
| `manual_real_execution` | Requires real DS005620 data, human peer review, and P18.3 gate confirmation |

The loop always sets `manual_real_execution` to status `manual_required`. It never executes it.

## Real-data guardrails

All of these are hardcoded `false` and included in every iteration output:

- `executes_real_data`: false
- `downloads_data`: false
- `auto_confirms_peer_review`: false
- `executes_real_benchmark`: false
- `auto_runs_mne_extraction`: false
- `auto_runs_level_m_extraction`: false
- `auto_runs_level_t_extraction`: false
- `infers_labels`: false
- `fabricates_targets`: false
- `weakens_p18_3_gate`: false
- `weakens_p20_operator`: false
- `weakens_ontology_quarantine`: false
- `weakens_language_firewall`: false

Additionally, the loop checks every command against a list of forbidden substrings before executing. Any command containing `--execute --peer-reviewed-contract-confirmed`, `dandi download`, `openneuro download`, `wget`, `curl`, or `aws s3 cp` is blocked and never run.

## Iteration outputs

All outputs are written to `outputs/btc_icft/ds005620_autonomous_iteration/`:

| File | Contents |
|---|---|
| `iteration_state.json` | Overall iteration state: counts, status, next action |
| `iteration_plan.json` | Full plan with all steps and guardrails |
| `iteration_results.json` | Per-step results: status, exit_code, stdout/stderr tails |
| `iteration_decision_log.json` | Decision: next_action, reasons, blocked_by, inputs |
| `iteration_next_action.json` | Compact: next_action, next_command, blocked_by, warnings |
| `iteration_artifact_index.json` | All artifact roots: exists or missing |
| `iteration_report.md` | Human-readable report |
| `iteration_events.jsonl` | Append-only event log |

## Decision logic

After all safe steps run, the loop computes a `final_next_action` by reading these output files:

1. `outputs/btc_icft/ds005620_real_benchmark_execution_mock/validation_summary.json`
2. `outputs/btc_icft/ds005620_real_benchmark_execution_mock/contract_validation_summary.json`
3. `outputs/btc_icft/ds005620_generated_language_validation.json`
4. `outputs/btc_icft/ds005620_real_artifact_operator/real_artifact_next_command.json`
5. `outputs/btc_icft/ds005620_real_execution_gate/ready_for_real_execution.json`

Priority order:
1. `fix_failed_safe_step` — if any required step failed
2. `blocked_language_violation` — if generated-language scan detected violations
3. `blocked_contract_violation` — if contract validation failed
4. Next action from P20 real artifact operator (e.g. `provide_metadata`)
5. Next action from P18.3 real execution gate
6. `human_peer_review_required` — if gate is ready but human review still needed
7. `manual_real_execution_ready_but_not_auto_run` — gate passed, human confirmed
8. `complete_mock_runtime_ready_for_real_artifact_work` — default safe state

## How to run dry-run

```bash
make ds005620-autonomous-iteration-dry-run
# or:
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --dry-run
```

In dry-run mode:
- All safe auto-run steps are marked `pending` (not executed)
- The manual step is `manual_required`
- Decision is still computed from existing artifact files
- All 8 output files are still written
- CLI exits 0

## How to run safe iteration

```bash
make ds005620-autonomous-iteration
# or:
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration
```

Options:
- `--continue-on-error` — record failed steps but continue to remaining steps
- `--skip-mock` — skip all mock E2E steps (run planning/gate steps only)
- `--skip-real-planning` — skip real/local preflight, artifact plan, and execution gate steps
- `--timeout-s N` — per-step timeout in seconds (default 300)
- `--max-steps N` — stop after N steps
- `--json` — print JSON summary to stdout
- `--strict` — explicit: exit nonzero on failure (default behavior)

## How to interpret next_action

See `outputs/btc_icft/ds005620_autonomous_iteration/iteration_next_action.json` after running.

In the default no-real-data state, the expected output is:
```json
{
  "next_action": "provide_metadata",
  "next_command": "Place DS005620 events.tsv at data/DS005620/events.tsv"
}
```

This means all safe mock/runtime steps completed, and the next required action is to provide local DS005620 metadata before real artifact preparation can proceed.

## How this relates to P18.3 and P20

P21 is a coordinator, not a replacement:

- **P18.3** (real/local execution gate) is still the authoritative gate for real execution readiness. P21 runs P18.3 as one of its safe steps.
- **P20** (real artifact build operator) is still the authoritative planner for real artifact preparation. P21 runs P20 as one of its safe steps.
- P21 reads the outputs of both P18.3 and P20 to compute its final decision.

## What this loop never does

- Never executes real DS005620 EEG data
- Never downloads any data (no dandi, no openneuro, no wget, no curl)
- Never runs MNE extraction automatically
- Never runs real Level M or Level T feature extraction automatically
- Never runs the real P18.1 benchmark execution automatically
- Never confirms peer review on behalf of a human operator
- Never activates a reviewed contract
- Never infers labels
- Never fabricates targets
- Never weakens the P18.3 execution gate
- Never weakens the P20 build operator
- Never weakens the ontology quarantine
- Never weakens the generated-output language firewall
- Never emits empirical claims from mock E2E results
- Never promotes ontology candidates from runtime artifacts
- Never makes metaphysical proof claims

## Recommended operator workflow

1. Run dry-run to see the plan: `make ds005620-autonomous-iteration-dry-run`
2. Run safe iteration: `make ds005620-autonomous-iteration`
3. Check `iteration_next_action.json` for the next required action
4. If next_action is `provide_metadata`, place DS005620 events.tsv locally
5. If next_action is `provide_raw_eeg`, place raw EEG files locally
6. If next_action is `prepare_reviewed_contract_declaration`, author the activation declaration
7. Continue following next_action instructions from the P20 operator report
8. After all prerequisites are ready, re-run: `make ds005620-autonomous-iteration`
9. When gate is ready, complete human peer review checklist in `outputs/btc_icft/ds005620_real_execution_gate/human_peer_review_checklist.md`
10. After human review, manually run the real execution command from the gate output

Human peer review and real execution are never automated.
