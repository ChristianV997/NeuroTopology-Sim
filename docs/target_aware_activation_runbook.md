# Target-Aware EEG Signal Benchmark Activation Smoke Runbook (P15)

---

## Purpose

P15 proves that the full explicit-label path works end-to-end as a controlled
smoke test:

P14 readiness → P12 active mock alignment → P10 topology →
P13 target injection → P11 target-aware M+T rerun

**This is not empirical validation.** It uses a declared mock binary label
mapping to verify that explicit targets propagate correctly through the pipeline.
No real dataset contracts are activated. No labels are inferred. No targets
are fabricated outside the declared mock mapping.

---

## Stage sequence

| Stage | Pipeline | Purpose |
|---|---|---|
| P14 | `plan_dataset_label_adapters` | Adapter readiness planning |
| P12 | `align_eeg_labels --activate-mock-contract` | Active mock label alignment |
| P10 | `run_eeg_level_t_signal` | Level T topology extraction |
| P13 | `inject_eeg_targets --mock-binary-targets --run-p11-smoke` | Target injection + P11 smoke |
| P11 | (run inside P13 via `--run-p11-smoke`) | Target-aware M+T residual benchmark |

---

## Exact command

```bash
python -m sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke \
  --dataset-id DS005620 \
  --root outputs/btc_icft \
  --out outputs/btc_icft/target_aware_activation/DS005620 \
  --mock-fixture \
  --validate-artifacts
```

---

## Expected fixture-safe result

```
[p14_adapter_readiness] OK (exit=0)
[p12_explicit_label_alignment] OK (exit=0)
[p10_level_t_signal_topology] OK (exit=0)
[p13_target_injection] OK (exit=0)

Activation smoke summary:
  predictive_metrics_available: True
  promoted: False or True (determined by P11 gates)
  activation_smoke_passed: True
```

The key success criterion is `predictive_metrics_available: True` — this
confirms that explicit mock targets propagated from P12 through P13 into P11.

---

## How to inspect metrics

After running, inspect the target-aware metrics snapshot:

```bash
cat outputs/btc_icft/target_aware_activation/DS005620/target_aware_metrics_snapshot.json
```

Key fields:
- `predictive_metrics_available` — must be `true` for activation smoke to pass
- `explicit_targets_available` — must be `true`
- `auc_m`, `auc_mt`, `delta_auc` — Level M vs M+T AUC comparison
- `promoted` — P11 gate decision (not forced by P15)
- `promotion_reason` — P11 gate rationale

---

## Why this is not empirical validation

- Mock binary labels (`condition_a → 1`, `condition_b → 0`) are
  **declared fixtures**, not real clinical or scientific annotations.
- The P11 benchmark is controlled and reproducible but makes no claim
  about real EEG signals or mental states.
- AUC/ECE metrics reflect the mock fixture structure, not real predictive
  performance.
- Promotion (if true) reflects the P11 gate logic on fixture data only.

---

## Requirements for real contract activation

Real dataset contract activation requires a **separate human-reviewed PR** with:

1. `explicit_label_column` declared (e.g., `"trial_type"`)
2. `positive_values` declared (e.g., `["meditation"]`)
3. `negative_values` declared (e.g., `["rest"]`)
4. `label_scope` declared (`"window"`, `"file"`, `"subject"`, or `"session"`)
5. `join_keys` confirmed (8-field composite for window scope)
6. Peer review of the label mapping before activation

Do NOT activate real contracts by passing `--activate-mock-contract` with
real dataset metadata files. Use a dedicated contract PR instead.

---

## Guardrails

The following claims are forbidden in all P15 artifacts:

- proves consciousness
- consciousness proven
- soul proven
- afterlife proven
- liberation detected
- ontology solved
- ultimate reality
- Q equals self / Q equals soul
- Q_abs equals suffering
- f_dress equals karma
- sedated implies no_experience
- unresponsive implies unconscious

P15 scans its own output artifacts for these phrases after writing.
If any are found, `activation_smoke_passed` is set to `false`.

---

## Output artifacts

Written to `--out` directory:

| File | Contents |
|---|---|
| `activation_smoke_summary.json` | Pipeline run summary and pass/fail status |
| `activation_stage_results.json` | Per-stage command, exit code, stdout/stderr tail |
| `target_aware_metrics_snapshot.json` | P11 metrics extracted from metrics_signal_mt.json |
| `activation_guardrail_report.json` | Guardrail compliance assertions |
| `omega_event.json` | Safe claim and event record |
| `report.md` | Human-readable activation report |
