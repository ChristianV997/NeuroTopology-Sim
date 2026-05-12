# EEG MNE Adapter Runbook

## Purpose
Dependency-gated local EEG extraction prototype.

## Relation to P19.0 preflight
P19.0 checks reader capability; P19.1 adds optional MNE extraction.

## What P19.1 does
Reads local files when MNE exists and exports fixed signal windows.

## What P19.1 does not do
No download, no labels, no targets, no contracts, no P11 automation.

## Supported MNE-gated formats
.edf .bdf .gdf .set .fdt .vhdr .vmrk .eeg .cnt .fif

## Optional dependency behavior
If MNE is missing, blocked outputs are written.

## Commands
```bash
python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks \
  --dataset-id DS005620 \
  --mock-fixture \
  --out outputs/btc_icft/eeg_mne_extract/DS005620
```

```bash
python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks \
  --dataset-id DS005620 \
  --mock-mne-missing \
  --input data/DS005620/example.edf \
  --out outputs/btc_icft/eeg_mne_extract/DS005620_missing
```

```bash
python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks \
  --dataset-id DS005620 \
  --input data/DS005620/sub-001/eeg/sub-001_task-rest_eeg.edf \
  --out outputs/btc_icft/eeg_mne_extract/DS005620 \
  --window-seconds 2.0 \
  --max-windows 10
```

## Output artifacts
mne_signal_metadata.json, mne_signal_windows.csv, mne_signal_window_values.json, mne_extraction_report.json, omega_event.json, report.md

## Readiness
Check `mne_extraction_report.json` field `ready_for_signal_block_conversion`.

## Next step
P19.2 canonical signal-block conversion.

## Guardrails
No ontology or consciousness claims.
