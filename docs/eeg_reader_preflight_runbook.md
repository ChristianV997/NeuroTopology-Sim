# EEG Reader Preflight Runbook

## purpose
P19.0 provides local EEG reader capability preflight.

## what P19.0 does
Scans local files, detects format, checks optional dependencies, and writes manifest/report artifacts.

## what it does not do
No binary parsing, no downloads, no label inference, no target fabrication, no contract activation.

## supported text fixture formats
.csv, .tsv, .txt

## dependency-gated binary formats
mne: .edf/.bdf/.gdf/.set/.fdt/.vhdr/.vmrk/.eeg/.cnt/.fif
wfdb: .hea/.dat
scipy: .mat

## exact mock command
python -m sciencer_d.btc_icft.pipelines.preflight_eeg_readers \
  --dataset-id DS005620 \
  --out outputs/btc_icft/eeg_reader_preflight/DS005620 \
  --mock-fixture

## exact real/local command
python -m sciencer_d.btc_icft.pipelines.preflight_eeg_readers \
  --dataset-id DS005620 \
  --root data/DS005620 \
  --out outputs/btc_icft/eeg_reader_preflight/DS005620

## output artifacts
- eeg_file_manifest.csv
- reader_capability_report.json
- reader_preflight_summary.json
- extraction_blockers.json
- omega_event.json
- report.md

## how to interpret blockers
`optional_dependency_missing:*` means install optional package before future extractor work.

## next adapter actions
Select backend, add local fixture tests, then implement dependency-gated extractor.

## guardrails
No consciousness/ontology/soul/afterlife proof claims.
