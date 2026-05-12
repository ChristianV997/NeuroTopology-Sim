# DS005620 Human-Reviewed Contract Activation Packet Runbook (P16)

---

## Purpose

P16 produces a read-only audit of local DS005620 metadata files to determine
whether enough explicit metadata exists to activate a P12 label contract.
It generates a human-review packet listing required decisions and activation
blockers, so a human reviewer can prepare a separate contract-activation PR.

---

## What P16 Does

- Loads local DS005620 metadata (.csv, .tsv, or .json)
- Audits each column for binary label candidacy
- Uses P14.1 contract drafts as inactive hints (if supplied)
- Writes activation_proposal.json with candidate columns and unresolved values
- Writes human_review_packet.json with required decisions checklist
- Writes metadata_value_audit.csv with per-column audit details
- Writes activation_blockers.json
- Writes omega_event.json with safe claim
- Writes report.md

---

## What P16 Does NOT Do

- Does **not** infer labels from file names, topology, or artifacts
- Does **not** fabricate y targets
- Does **not** activate any real contract (`contract_activation_allowed` is always `false`)
- Does **not** run P11
- Does **not** modify P11/P12/P13 behavior
- Does **not** modify legacy DS005620 mt_real semantics
- Does **not** download data
- Does **not** use P14.1 contract drafts to activate anything

---

## Exact Mock Command

```bash
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \
  --mock-fixture \
  --out outputs/btc_icft/ds005620_contract_activation
```

Expected result:

```
[p16] DS005620 contract activation packet complete.
  n_metadata_rows: 6
  metadata_file_exists: True
  candidate_label_columns: ['trial_type', 'condition']
  positive_values: [] (not declared)
  negative_values: [] (not declared)
  contract_activation_allowed: False (always)
  activation_blockers: 9
```

---

## Exact Real/Local Metadata Command

```bash
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \
  --metadata data/DS005620/events.tsv \
  --contract-drafts outputs/btc_icft/label_contract_drafts/contract_drafts.json \
  --out outputs/btc_icft/ds005620_contract_activation
```

---

## How to Use Contract Drafts as Hints Only

The `--contract-drafts` flag accepts the P14.1 `contract_drafts.json` output.
P16 reads the DS005620 draft and extracts `candidate_label_columns` and
`unresolved_values` **as hints only**. It never:

- Copies `positive_values` or `negative_values` into the active proposal
- Activates any contract based on the draft status
- Downgrades blockers based on draft content

If a draft has a status suggesting activation (e.g., `ready_to_activate`),
P16 logs a warning and ignores the active-looking status.

---

## Required Human Decisions

Before a real contract-activation PR can be opened, a human reviewer must
explicitly declare all of the following:

| Decision | Description |
|---|---|
| `explicit_label_column` | Which column in the metadata contains the label |
| `positive_values` | Which values map to the positive class |
| `negative_values` | Which values map to the negative class |
| `label_scope` | `window`, `file`, `subject`, or `session` |
| `join_keys` | Composite key fields for aligning metadata to P9 features |
| `metadata_provenance` | Source and path of the metadata file |
| `semantic_justification` | Why the mapping is semantically valid |
| `no_shortcut_confirmation` | Explicit statement that no shortcut inference is used |

---

## Activation Blockers

The following blockers will always appear in P16 output:

- `explicit_label_column_required` — must be declared by a human
- `positive_values_required` — must be declared by a human
- `negative_values_required` — must be declared by a human
- `both_classes_required` — both classes must appear in local metadata
- `human_review_required` — human review is always required
- `semantic_justification_required` — semantic mapping must be justified
- `no_shortcut_inference_confirmation_required` — must confirm no shortcut
- `separate_contract_activation_pr_required` — requires a separate PR

If no local metadata is found:

- `metadata_required` — supply local metadata file first

---

## Next Step: P17 Contract Activation PR

After P16 is reviewed and all required human decisions are made, open a
**separate contract-activation PR** that explicitly declares:

1. `explicit_label_column` (e.g., `"trial_type"`)
2. `positive_values` (e.g., `["focus"]`)
3. `negative_values` (e.g., `["mind_wandering"]`)
4. `label_scope` (e.g., `"window"`)
5. `join_keys` (the 8-field composite from P11)
6. Metadata provenance (file path and source)
7. Semantic justification (why the mapping is valid)
8. Confirmation that no shortcut inference was used

That PR runs P12 → P13 → P11 target-aware benchmark. This PR (P16)
only prepares the review packet.

---

## Guardrails

All P16 artifacts are scanned for forbidden phrases. If any are found,
the pipeline fails before writing outputs.

Forbidden in all P16 outputs:

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

Additionally:
- `contract_activation_allowed` is hardcoded `false` everywhere
- No label inference from file names, topology, or artifacts
- No target fabrication
- No data download

---

## Running Tests

```bash
python -m pytest tests/btc_icft/test_ds005620_contract_activation.py -q
```

---

## Output Artifacts

Written to `--out` directory:

| File | Contents |
|---|---|
| `activation_proposal.json` | Gates, candidate columns, unresolved values, blockers |
| `human_review_packet.json` | Reviewer checklist, required decisions, reviewer questions |
| `metadata_value_audit.csv` | Per-column audit: count, unique values, binary_candidate flag |
| `activation_blockers.json` | Blockers list; `contract_activation_allowed: false` |
| `omega_event.json` | Safe claim and event record |
| `report.md` | Human-readable activation audit report |
