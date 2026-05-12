# DS005620 Contract Activation Runbook (P16)

## Purpose

Prepare a conservative, human-reviewed DS005620 label-contract activation packet from local metadata audit results.

## What P16 does

- Audits local metadata values and candidate columns.
- Produces an activation proposal with `contract_activation_allowed: false` by default.
- Produces a human review packet, activation blockers, omega event, and report.
- Captures unresolved candidate values for human review only.

## What P16 does not do

- Does not activate a real contract.
- Does not infer labels or fabricate targets.
- Does not infer `no_experience` from `sedated`.
- Does not infer `unconscious` from `unresponsive`.
- Does not use filename/topology/artifact-derived labels.
- Does not modify P11/P12/P13 behavior.
- Does not modify legacy `mt_real` semantics.
- Does not download data.

## Exact mock command

```bash
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \
  --mock-fixture \
  --out outputs/btc_icft/ds005620_contract_activation
```

## Exact real/local metadata command

```bash
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \
  --metadata local_ds005620_metadata.csv \
  --contract-drafts outputs/btc_icft/label_contract_drafts/contract_drafts.json \
  --out outputs/btc_icft/ds005620_contract_activation
```

## Required human decisions

- choose `explicit_label_column`
- declare `positive_values`
- declare `negative_values`
- declare `label_scope`
- verify `join_keys`
- verify metadata provenance
- justify semantic mapping
- confirm no shortcut inference
- approve contract activation in a separate PR

## Activation blockers

Applicable blockers can include:

- `metadata_required`
- `explicit_label_column_required`
- `positive_values_required`
- `negative_values_required`
- `both_classes_required`
- `human_review_required`
- `semantic_justification_required`
- `no_shortcut_inference_confirmation_required`
- `separate_contract_activation_pr_required`

## Next P17 contract activation PR

Open a separate contract-activation PR only after a human reviewer explicitly declares `explicit_label_column`, `positive_values`, `negative_values`, `label_scope`, `join_keys`, metadata provenance, semantic justification, and no-shortcut justification.

## Guardrails

- no_data_download
- no_label_inference
- no_target_fabrication
- no_sedated_to_no_experience
- no_unresponsive_to_unconscious
- no_filename_derived_labels
- no_topology_derived_labels
- no_artifact_derived_labels
- no_automatic_real_contract_activation
- no_p11_gate_modification
- no_legacy_mt_real_change
- no_level_o
- no_ontology_claims
- no_soul_afterlife_claims
- no_liberation_claims
