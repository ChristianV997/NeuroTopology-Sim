# EEG External Contract Alignment Runbook

## Purpose
Enable P12 label alignment to consume a reviewed external contract artifact without inferring labels or fabricating targets.

## Relation to P17.1
P17.1 materializes `p12_external_contract.json` from a reviewed declaration. P12.1 consumes that artifact via `--external-contract`.

## What `--external-contract` does
- Loads and validates an external reviewed contract.
- Uses it as the explicit P12 contract source.
- Preserves existing behavior when omitted.

## What it does not do
- Does not infer labels.
- Does not fabricate targets.
- Does not emit targets outside explicit metadata mapping.
- Does not run P11 or P13.

## Required external contract fields
- `dataset_id`
- `contract_status` (`active_reviewed_external_contract`)
- `explicit_label_column`
- `positive_values`
- `negative_values`
- `label_scope`
- `join_keys` (strict P12 keys)
- `metadata_provenance`
- `guardrails` (including `no_label_inference`, `no_target_fabrication`)

## Exact mock external-contract command
```bash
python -m sciencer_d.btc_icft.pipelines.align_eeg_labels \
  --dataset-id DS005620 \
  --external-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --mock-fixture \
  --out outputs/btc_icft/eeg_labels/DS005620_external
```

## Exact real/local command
```bash
python -m sciencer_d.btc_icft.pipelines.align_eeg_labels \
  --dataset-id DS005620 \
  --signal-features outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv \
  --metadata data/DS005620/events.tsv \
  --external-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --out outputs/btc_icft/eeg_labels/DS005620_external
```

## Output artifacts
- `label_contract.json`
- `label_alignment.csv`
- `label_alignment_report.json`
- `rejected_labels.json`
- `omega_event.json`
- `report.md`

## Failure modes
- Missing contract path.
- Malformed JSON.
- Dataset mismatch.
- Inactive/wrong status.
- Missing strict join keys.
- Missing guardrails and provenance.

## P13/P18 handoff
Use P12 outputs for inspection and readiness. Run P13 only after confirming P12 alignment used the reviewed external contract correctly.

## Guardrails
- no_label_inference
- no_target_fabrication
- external_contract_requires_human_review
- no_external_contract_fallback_to_inference
