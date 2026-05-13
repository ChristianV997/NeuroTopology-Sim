# DS005620 Real Benchmark Readiness Gate Runbook (P18.0)

---

## Purpose

P18.0 inspects whether all required real/local DS005620 benchmark inputs
exist and are compatible before allowing a future P18.1 real target-aware
benchmark run.

P18.0 produces a readiness summary and dry-run command plan but does NOT:
- Run P9/P10/P11 automatically
- Infer labels
- Fabricate targets
- Activate contracts
- Mutate P12 source contracts

---

## Relation to P17.1 and P19.2

P17.1 produced:
- `p12_external_contract.json` — reviewed external contract artifact

P19.2 is implemented and produces:
- `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/signal_block_inventory.json`
- `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/window_inventory.csv`
- `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/window_signal_values.json`
- `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/reader_alignment_report.json`

P18.0 cross-checks all of these inputs and plans the P18.1 benchmark run.

---

## What P18.0 Does

- Inspects P17.1 reviewed external contract for active status and strict join keys
- Inspects local metadata file for supported extension and existence
- Inspects P19.2 canonical signal blocks directory for required files and join key coverage
- Inspects Level M features (features_m_signal.csv) for strict join key presence
- Inspects Level T features (features_t_signal.csv) for strict join key presence
- Builds ordered dry-run command plan for P17.1 → P19.1 → P19.2 → P9 → P10 → P12 → P13 → P11
- Writes readiness summary, input statuses, execution blockers, omega event, and report
- Sets `ready_for_p12_alignment` only when contract + metadata + signal blocks are ready
- Sets `ready_for_real_benchmark` only when all benchmark-stage inputs are present

---

## What P18.0 Does NOT Do

- Does **not** run P9/P10/P11 automatically
- Does **not** infer labels from file names, topology, or artifacts
- Does **not** fabricate y targets
- Does **not** activate contracts or mutate P12 source files
- Does **not** implement Level O/C/Q
- Does **not** touch P19.2 files if they exist
- Does **not** modify P11/P12/P13 behavior
- Does **not** modify legacy DS005620 mt_real semantics
- Does **not** download data
- Does **not** add dependencies

---

## Exact Mock-Ready Command

```bash
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \
  --mock-ready \
  --out outputs/btc_icft/ds005620_real_benchmark_readiness
```

Expected result:
```
ready_for_p12_alignment: True
ready_for_p11_target_aware_benchmark: True
execution_blockers: 0
```

---

## Exact Mock-Blocked Command

```bash
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \
  --mock-blocked \
  --out outputs/btc_icft/ds005620_real_benchmark_readiness_blocked
```

Expected result:
```
ready_for_p12_alignment: False
execution_blockers: > 0
```

---

## Exact Real/Local Planning Command

```bash
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark \
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --metadata data/DS005620/events.tsv \
  --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \
  --out outputs/btc_icft/ds005620_real_benchmark_readiness
```

All paths are inspected but no commands are executed.

---

## Output Artifacts

| File | Contents |
|---|---|
| `ds005620_benchmark_readiness.json` | Readiness flags, blockers, required next steps |
| `benchmark_input_statuses.json` | Per-input status (name, path, exists, ready, blockers) |
| `dry_run_command_plan.json` | Ordered commands with ready_to_run flags |
| `execution_blockers.json` | All blockers, blocker count, next unblocked action |
| `omega_event.json` | Safe claim record |
| `report.md` | Human-readable readiness report |

---

## Readiness Flags

| Flag | Requires |
|---|---|
| `ready_for_p12_alignment` | reviewed_contract + metadata + canonical_signal_blocks all ready |
| `ready_for_p13_target_injection` | P12 alignment output (label_alignment.csv) present |
| `ready_for_p11_target_aware_benchmark` | Level M + Level T + all above ready |
| `ready_for_real_benchmark` | All P11 prerequisites ready |

For P18.0 (planning only), `ready_for_p13_target_injection` is typically `false`
unless a P12 alignment output was explicitly provided.

---

## Blocker Interpretation

| Blocker | Cause |
|---|---|
| `reviewed_contract not found: X` | P17.1 not run yet; run materialize_ds005620_reviewed_contract |
| `contract_status is '...' expected 'active_reviewed_external_contract'` | Contract is preview/blocked; rerun P17.1 with valid declaration |
| `metadata_file not found: X` | Provide real/local DS005620 events.tsv or equivalent |
| `canonical_signal_blocks directory not found: X` | Run P19.1 MNE extraction + P19.2 conversion |
| `window_inventory.csv header missing strict join keys: [...]` | P19.2 canonical conversion output is stale or malformed |
| `blocked_missing_p19_2_converter` | Compatibility blocker only when the P19.2 CLI is absent in the local environment |
| `blocked_p12_external_contract_handshake_missing` | P12 CLI does not support --external-contract |

---

## Dry-Run Command Plan

P18.0 generates an ordered command plan but does NOT execute any command:

1. **P17.1** — Materialize reviewed external contract
2. **P19.1** — MNE signal extraction from local EEG files
3. **P19.2** — Canonical signal-block conversion
4. **P9** — Level M signal feature extraction
5. **P10** — Level T signal topology extraction
6. **P12** — Label alignment with reviewed external contract
7. **P13** — Target injection
8. **P11** — Target-aware M+T benchmark (future P18.1 scope)

Each command includes `ready_to_run`, `requires`, `expected_outputs`, and `blockers`.

---

## P18.1 Handoff

P18.1 mock E2E is CI-protected by `.github/workflows/ds005620-e2e.yml`.


P18.0 plans readiness. **P18.1 (`run_ds005620_real_benchmark`)** executes
the guarded P12 → P13 → P11 chain when peer review is confirmed.

After P18.0 reports `ready_for_p12_alignment: True`:

1. Verify `p12_external_contract.json` with an independent peer reviewer.
2. Smoke-test the integration with `make ds005620-e2e-mock` — runs the
   real P12 / P13 / P11 CLIs against in-tree fixtures.
3. Validate with `make validate-ds005620-e2e`.
4. Run real/local: `python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --execute --peer-reviewed-contract-confirmed --out <real_out>`.
5. Open a P18.1 results PR with the produced artifacts.

Do NOT run P18.1 in execute mode without peer review of the reviewed
external contract.
Do NOT open a P18.1 results PR if `ready_for_p12_alignment: False`.

---

## Guardrails

All P18.0 artifacts are scanned for forbidden phrases:

- proves consciousness / consciousness proven
- soul proven / afterlife proven
- liberation detected / ontology solved
- ultimate reality
- Q equals self / Q equals soul
- Q_abs equals suffering / f_dress equals karma
- sedated implies no_experience
- unresponsive implies unconscious
- topology proves liberation / EEG proves consciousness

Additionally:
- `benchmarks_run` is hardcoded `false` in omega_event
- `labels_inferred` is hardcoded `false` in omega_event
- `targets_fabricated` is hardcoded `false` in omega_event
- `contracts_activated` is hardcoded `false` in omega_event
- P11 stage in dry-run plan always has `ready_to_run: false` for P18.0
