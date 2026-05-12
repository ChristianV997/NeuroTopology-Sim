# MNE Signal-Block Conversion Runbook

## Purpose
Bridge P19.1 MNE extraction outputs into canonical signal-block artifacts for downstream processing.

## Relation to P19.1
Consumes `mne_signal_metadata.json`, `mne_signal_windows.csv`, and `mne_signal_window_values.json` from P19.1.

## What P19.2 does
Converts extracted windows into canonical signal-block conversion outputs with readiness telemetry.

## What P19.2 does not do
No label inference, no target fabrication, no contract activation, and no automatic P9/P10/P11 runs.

## Commands
Mock:
```bash
python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks \
  --dataset-id DS005620 \
  --mock-fixture \
  --out outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620
```
Blocked:
```bash
python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks \
  --dataset-id DS005620 \
  --mock-blocked-input \
  --out outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620_blocked
```
Real/local:
```bash
python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks \
  --dataset-id DS005620 \
  --mne-extract outputs/btc_icft/eeg_mne_extract/DS005620 \
  --out outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620
```

## Output artifacts
signal_block_inventory.json, window_inventory.csv, window_signal_values.json, reader_alignment_report.json, rejected_windows.json, omega_event.json, report.md.

## Readiness flags
`ready_for_level_m_signal` and `ready_for_level_t_signal` are true only when conversion status is converted and valid windows exist.

## Downstream usage
P9/P10 should consume canonical outputs later; this step only prepares handoff artifacts.

## Why P18 still needs reviewed contract and real labels
P19.2 only converts operational telemetry windows and does not produce reviewed label contracts or benchmark targets.

## Guardrails
No MNE requirement, no data download, no ontology claims, no label or target emission.
