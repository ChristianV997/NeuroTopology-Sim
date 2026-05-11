# EEG Signal Pipeline Runbook (P8.1–P11)

Operational runbook for the BTC/ICFT EEG signal pipeline.

---

## Purpose

This pipeline produces signal-level EEG artifact tables for controlled residual
benchmarking. It does not download data, train models, infer labels, fabricate
targets, or make consciousness/soul/liberation/afterlife/ontology proof claims.

---

## Stage Order

| Stage | Pipeline | Output directory |
|---|---|---|
| P8.1 | `feed_eeg_study_dataset` | `outputs/btc_icft/eeg_studies/<dataset_id>/` |
| P8.2 | `probe_eeg_signal_blocks` | `outputs/btc_icft/ds005620/signal_blocks/` |
| P9   | `run_eeg_level_m_signal`  | `outputs/btc_icft/eeg_level_m/<dataset_id>/` |
| P10  | `run_eeg_level_t_signal`  | `outputs/btc_icft/eeg_level_t/<dataset_id>/` |
| P11  | `run_eeg_signal_mt`       | `outputs/btc_icft/eeg_signal_mt/<dataset_id>/` |

---

## Smoke Command (fixture-safe)

```bash
python tools/run_eeg_signal_pipeline_smoke.py \
    --dataset-id DS005620 \
    --root outputs/btc_icft \
    --validate
```

Or via Make:

```bash
make smoke-eeg-signal-pipeline
```

---

## Validation Command

```bash
python tools/validate_eeg_signal_artifacts.py \
    --root outputs/btc_icft \
    --dataset-id DS005620
```

Or via Make:

```bash
make validate-eeg-signal-artifacts
```

Flags:

- `--stage <name>` — validate only a specific stage
- `--allow-missing` — skip stages whose output directories are absent
- `--json` — print machine-readable result JSON

---

## Expected Fixture-Safe Outcome

After running all stages with `--mock-fixture`:

```
P11 promotion status:
  promoted: false
  promotion_reason: blocked: no explicit targets available
```

This is the correct default. Promotion to `true` requires explicit validated
binary targets (y) to be present in the Level M feature input — not inferred
from label text.

---

## P12 Note

Label contracts (`eeg_label_contracts.py`, `align_eeg_labels.py`) are a
separate P12 concern. They must not be inferred or fabricated by this pipeline.
P12 is only run after explicit label alignment is confirmed by the label
contract system. The smoke runner does NOT invoke P12.

---

## Guardrails

The following claims are forbidden in all pipeline artifacts:

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

The validator (`validate_eeg_signal_artifacts.py`) checks all JSON, CSV, and
Markdown artifacts for these phrases and returns exit code 1 if any are found.

---

## Individual Stage Commands

**P8.1 — Feed EEG study dataset:**

```bash
python -m sciencer_d.btc_icft.pipelines.feed_eeg_study_dataset \
    --dataset-id DS005620 \
    --out outputs/btc_icft/eeg_studies/DS005620 \
    --mock-fixture
```

**P8.2 — Probe EEG signal blocks:**

```bash
python -m sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks \
    --out outputs/btc_icft/ds005620/signal_blocks \
    --mock-fixture
```

**P9 — Level M signal feature extraction:**

```bash
python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal \
    --dataset-id DS005620 \
    --out outputs/btc_icft/eeg_level_m/DS005620 \
    --mock-fixture
```

**P10 — Level T signal topology extraction:**

```bash
python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal \
    --dataset-id DS005620 \
    --out outputs/btc_icft/eeg_level_t/DS005620 \
    --mock-fixture
```

**P11 — Signal-level M+T residual benchmark:**

```bash
python -m sciencer_d.btc_icft.pipelines.run_eeg_signal_mt \
    --dataset-id DS005620 \
    --out outputs/btc_icft/eeg_signal_mt/DS005620 \
    --mock-fixture
```
