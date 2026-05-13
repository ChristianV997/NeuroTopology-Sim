# DS005620 Real Benchmark Executor Runbook (P18.1)

---

## Purpose

P18.1 is the guarded executor that actually runs the DS005620 benchmark
chain end-to-end:

P12 (`align_eeg_labels --external-contract`)
→ P13 (`inject_eeg_targets`)
→ P11 (`run_eeg_signal_mt`)

It only runs real CLIs when two flags are both set:
- `--execute`
- `--peer-reviewed-contract-confirmed`

Without both flags, the executor operates in dry-run mode: it writes the
planned commands and stage status, but executes nothing.

P18.1 never infers labels, never fabricates targets, never modifies P12/P13
source code, never modifies legacy `mt_real`, and never claims consciousness,
self, soul, liberation, afterlife, enlightenment, or ontology.

---

## One-command mock E2E

This is the integration smoke test for the whole DS005620 chain:

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \
  --mock-e2e --execute --peer-reviewed-contract-confirmed \
  --out outputs/btc_icft/ds005620_real_benchmark_execution_mock
```

Materializes a coherent in-tree fixture set (reviewed contract, metadata
with `trial_type`, canonical signal blocks, Level M features, Level T
features) and runs the real P12 / P13 / P11 CLIs against it. On success:

- `p12_succeeded: true`
- `p13_succeeded: true`
- `p11_succeeded: true`
- `benchmark_completed: true`

All six P18.1 artifacts are written under `--out`.

Verify with:

```bash
python tools/validate_ds005620_e2e_execution.py \
  --root outputs/btc_icft/ds005620_real_benchmark_execution_mock
```

A clean run prints `[validate-ds005620-e2e] PASS`.

---

## Dry-run mode

Default behavior when `--execute` is omitted:

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \
  --out outputs/btc_icft/ds005620_real_benchmark_execution_dry
```

- writes all six artifacts
- runs no stage
- `would_execute` flags reflect which stages have all prerequisites in place
- `dry_run_only_no_commands_executed` semantics — stages are not invoked

---

## Real/local mode

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --metadata data/DS005620/events.tsv \
  --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \
  --execute --peer-reviewed-contract-confirmed \
  --out outputs/btc_icft/ds005620_real_benchmark_execution
```

All paths default to the official P17.1 / P19.2 / P9 / P10 outputs — only
override when running against a non-default location.

If `--execute` is supplied without `--peer-reviewed-contract-confirmed`, the
run falls back to dry-run and records
`execute_requested_without_peer_reviewed_contract_confirmation` in
`execution_blockers.json`.

---

## Peer-review gate

The executor exists to slow down accidental real runs against unreviewed
contracts. A peer reviewer must:

1. Inspect `p12_external_contract.json` for correctness.
2. Verify the declared `explicit_label_column`, `positive_values`, and
   `negative_values` against the local `events.tsv`.
3. Confirm there are no sedated→no_experience or unresponsive→unconscious
   mappings.
4. Confirm there are no filename-, topology-, or artifact-derived labels.
5. Then, and only then, supply `--peer-reviewed-contract-confirmed`.

The flag is a self-attestation. The omega event records the flag value but
does not validate the human review independently.

---

## Stage sequence

| Stage | Module | Requires | Produces |
|---|---|---|---|
| P12 | `align_eeg_labels` | reviewed contract, metadata, Level M features | `label_alignment.csv` |
| P13 | `inject_eeg_targets` | Level M features, P12 alignment | `features_m_signal_labeled.csv` |
| P11 | `run_eeg_signal_mt` | P13 labeled M features, Level T features | `metrics_signal_mt.json` |

P11 always reads `features_m_signal_labeled.csv` from the P13 output, never
the raw Level M file.

Use `--stop-after p12` (or `p13` / `p11`) to halt after a given stage; later
stages are marked skipped.

Use `--continue-on-stage-failure` to keep running even if an upstream stage
fails; by default a failing stage halts the chain.

---

## Output artifacts

| File | Contents |
|---|---|
| `ds005620_real_benchmark_execution.json` | Mode, dry-run flag, execute flag, peer-review flag, per-stage executed/succeeded flags, `benchmark_completed`, artifact_root, safe_claim |
| `stage_execution_plan.json` | Per-stage command, command_str, ready_to_run, expected_outputs |
| `stage_results.json` | Full per-stage results: ready, executed, skipped, succeeded, exit_code, blockers, expected/actual outputs, stdout/stderr previews, duration |
| `execution_blockers.json` | Executor-level blockers, per-stage blockers, total count |
| `omega_event.json` | Safe-claim record with hardcoded `labels_inferred=False`, `targets_fabricated=False`, `source_contracts_modified=False`, `legacy_mt_real_modified=False`, `contracts_activated_by_executor=False`, `p11_promotion_gate_modified=False`, `consciousness_claims_made=False` |
| `report.md` | Human-readable execution report |

---

## Validation

Run after a mock E2E or real run:

```bash
python tools/validate_ds005620_e2e_execution.py \
  --root outputs/btc_icft/ds005620_real_benchmark_execution_mock
```

Checks:
- all six artifacts exist
- P12 / P13 / P11 expected outputs exist on disk after a successful run
- all seven omega invariants are `false`
- `report.md` contains no banned phrases
- `benchmark_completed: true` only when all three stages succeeded
- P11 command consumes the P13 labeled file, not raw Level M

---

## Blocker interpretation

| Blocker | Cause |
|---|---|
| `execute_requested_without_peer_reviewed_contract_confirmation` | `--execute` was supplied without `--peer-reviewed-contract-confirmed`; falls back to dry-run |
| `P12 prerequisite missing: <path>` | Reviewed contract, metadata, or Level M features file does not exist |
| `P13 prerequisite missing: <path>` | Level M features or P12 `label_alignment.csv` missing |
| `P11 prerequisite missing: <path>` | P13 labeled M features or Level T features missing |
| `skipped_due_to_upstream_failure` | A prior stage failed and `--continue-on-stage-failure` was not supplied |
| `P12 exited with code N` | The P12 CLI returned non-zero; see `stderr_preview` |
| `P13 exited with code N` | The P13 CLI returned non-zero |
| `P11 exited with code N` | The P11 CLI returned non-zero |

---

## Guardrails

- No label inference, no target fabrication
- No sedated→no_experience or unresponsive→unconscious shortcut
- No filename-, topology-, or artifact-derived labels
- No automatic contract activation by the executor — only the human
  peer-review flag unlocks execution
- No P11 promotion-gate modification
- No legacy `mt_real` semantics modification
- No data download (mock-e2e uses in-tree synthetic fixtures only)
- No new required dependencies (stdlib subprocess is the only runner)
- No Level O/C/Q implementation

---

## What counts as success

- **Engineering success:** mock-e2e completes, all six P18.1 artifacts are
  written, the validator passes, P12/P13/P11 all run, P11 produces
  `metrics_signal_mt.json`.

- **Empirical success:** *NOT* a P18.1 deliverable. Empirical claims about
  any DS005620 metric require an independent peer review and a separate
  paper-skeleton PR. P18.1 records `predictive_metrics_available` from the
  underlying P11 module; it does not promote, certify, or interpret them.

---

## What does NOT count as an empirical claim

A successful P18.1 mock-e2e run does **not** demonstrate, prove, or measure:

- consciousness, sentience, self, or soul
- liberation, enlightenment, or awakening
- afterlife or ontology
- topology- or EEG-based proof of any of the above

It demonstrates only that the engineering chain runs end-to-end with
reviewed external labels and explicit P12-derived targets.

---

## Paper handoff

A future paper-skeleton PR should:

1. Describe the controlled empirical protocol (preregistered hypothesis,
   ablation set, null distribution, ROI, statistical thresholds).
2. Cite the reviewed external contract and its provenance.
3. Report `metrics_signal_mt.json` results with full provenance.
4. State explicitly what the result is *not* a claim of.
5. Be independently peer-reviewed before merge.


## CI and automation safety

- The mock E2E path is CI-gated via `.github/workflows/ds005620-e2e.yml`.
- Unsafe execute behavior is enforced: `--execute` without `--peer-reviewed-contract-confirmed` exits nonzero and still writes blocked artifacts.
- Dry-run behavior remains safe-by-default: omitting `--execute` exits 0 and executes no stages.
- Machine-readable validation is available with:

```bash
make validate-ds005620-e2e-json
```

- Real/local execution still requires human data placement and peer-review confirmation before running execute mode.

## Contract validation

Run the contract validator after E2E validation:

```bash
make validate-ds005620-contracts
```

P18.1 artifact shape is now contract-tested in CI.
