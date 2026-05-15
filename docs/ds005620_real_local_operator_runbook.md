# DS005620 Real/Local Operator Runbook

## Purpose

This runbook guides a human operator through the prerequisites required before running a real/local DS005620 benchmark execution. It describes every required step, what each produces, and what guardrails remain active throughout.

**Critical**: This runbook does not authorize or execute real data automatically. Every step requires human action. The real execution command is generated for manual use only.

---

## Current system state

After PR #119 (O4/P24.1 ontology-aware publication integration), the repository supports:

- Mock E2E benchmark execution (`--mock-e2e`) with full artifact chain
- Ontology claim evaluation (claim scope capped at `engineering_runtime` for mock runs)
- Evidence packet, Notion payload, paper skeleton, CI evidence report
- Real/local preflight check (P18.2)
- **Real/local execution gate (P18.3)** — this runbook

The next bottleneck is controlled real/local execution readiness under human review.

---

## What mock E2E proves

- The P12 → P13 → P11 pipeline stages execute end-to-end using in-tree fixtures.
- Omega invariants are structurally enforced (no label inference, no target fabrication, no contract modification).
- Artifact contracts and evidence packets are valid for engineering runtime scope.
- Ontology claim scope is correctly capped at `engineering_runtime`.

## What mock E2E does not prove

- Any empirical finding about DS005620 subjects.
- Any causal interpretation of EEG features.
- Any Level M or Level T empirical claims — those require real data, null comparisons, ablations, and leakage reports.
- Any substrate/theory/ontology candidate promotion — those remain quarantined.

---

## Required local directory layout

Before real execution, the following must be present on the operator's machine:

```
data/
  DS005620/
    events.tsv                    ← Step 1: metadata placement

outputs/btc_icft/
  ds005620_reviewed_contract/
    p12_external_contract.json    ← Step 2: reviewed contract materialization
  eeg_mne_extract/DS005620/       ← Step 3: MNE extraction
  eeg_signal_blocks_from_mne/DS005620/  ← Step 4: signal-block conversion
  eeg_level_m/DS005620/
    features_m_signal.csv         ← Step 5: Level M features
  eeg_level_t/DS005620/
    features_t_signal.csv         ← Step 6: Level T features
```

---

## Step 1: Metadata placement

Place the DS005620 events/metadata file locally:

```
data/DS005620/events.tsv
```

This file must be obtained from the official DS005620 dataset (not downloaded automatically by any pipeline). Verify provenance before use.

---

## Step 2: Reviewed contract materialization

Generate the reviewed external label contract using P17.1:

```bash
python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract
```

The contract at `outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json` must satisfy all static gate checks:
- `dataset_id == DS005620`
- `contract_status == active_reviewed_external_contract`
- `explicit_label_column` present and non-empty
- `positive_values` and `negative_values` non-overlapping
- All strict join keys present
- No shortcut indicators (`label_inference_enabled`, `targets_fabricated`, `filename_derived_labels`, `topology_derived_labels`, `artifact_derived_labels`, `automatic_activation`)

---

## Step 3: MNE extraction

Extract MNE signal blocks from local EEG files:

```bash
python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks --dataset-id DS005620
```

Output: `outputs/btc_icft/eeg_mne_extract/DS005620/`

---

## Step 4: Canonical signal-block conversion

Convert MNE outputs to canonical signal blocks with strict join keys:

```bash
python -m sciencer_d.btc_icft.pipelines.convert_mne_signal_blocks --dataset-id DS005620
```

Output: `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/`

---

## Step 5: Level M features

Run Level M signal feature extraction:

```bash
python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal --dataset-id DS005620
```

Output: `outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv`

---

## Step 6: Level T topology features

Run Level T topology feature extraction:

```bash
python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal --dataset-id DS005620
```

Output: `outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv`

---

## Step 7: Real execution gate

Run the P18.3 real/local execution gate to inspect artifact readiness:

```bash
make ds005620-real-execution-gate
# or:
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution \
  --out outputs/btc_icft/ds005620_real_execution_gate
```

This writes seven outputs to `outputs/btc_icft/ds005620_real_execution_gate/`:

| File | Purpose |
|---|---|
| `ready_for_real_execution.json` | Gate readiness summary |
| `real_execution_gate.json` | Full detailed gate report |
| `real_execution_command_plan.json` | Manual execution command (not auto-run) |
| `human_peer_review_checklist.json` | Machine-readable checklist |
| `human_peer_review_checklist.md` | Human-readable checklist |
| `missing_artifacts.json` | List of missing prerequisites |
| `report.md` | Human-readable gate report |

The gate always exits 0 (even if prerequisites are missing). `next_action` tells the operator what to do first.

**Important**: `peer_review_confirmed_by_human`, `can_use_execute_flag`, and `can_use_peer_reviewed_contract_confirmed_flag` remain `false` even when all artifacts are present.

---

## Step 8: Human peer review

Open `outputs/btc_icft/ds005620_real_execution_gate/human_peer_review_checklist.md` and complete all 18 checklist items:

- Verify metadata provenance
- Verify `explicit_label_column` in metadata
- Verify positive and negative values
- Confirm both label classes present
- Confirm no shortcut labels (sedation state, responsiveness state, filename, topology, artifact-derived)
- Confirm join keys match P12/P13/P11 expectations
- Review contract JSON
- Confirm pipeline stage expectations
- Acknowledge empirical controls still required
- Acknowledge ontology claim scope limits

This is a human-only step. No pipeline confirms this automatically.

---

## Step 9: Manual guarded real execution

After completing all checklist items, a human operator may manually run:

```bash
# DO NOT RUN AUTOMATICALLY — requires human peer review first
python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark \
  --dataset-id DS005620 \
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --metadata data/DS005620/events.tsv \
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \
  --out outputs/btc_icft/ds005620_real_benchmark_execution \
  --execute \
  --peer-reviewed-contract-confirmed
```

This command is also stored in `real_execution_command_plan.json`.

---

## Step 10: Post-execution validation

After real execution, run:

```bash
make ds005620-e2e-ci
make validate-ds005620-e2e
make validate-ds005620-contracts
```

---

## Step 11: Controls

Real execution does not validate empirical claims without additional controls. Required post-execution controls (not yet automated):

- `nulls.json` — null comparison results
- `ablations.json` — ablation study results
- `leakage_report.json` — feature leakage audit
- `artifact_report.json` — artifact classification report

These are documented in `configs/btc_icft/ds005620_real_local_execution_gate.json` under `post_execution_required_controls`.

---

## Step 12: Ontology evaluation

After real execution, re-run ontology claim evaluation:

```bash
make ds005620-ontology-eval-mock
# (or with real execution root when available)
```

Ontology evaluation scope remains limited by claim-scope rules even after real execution. Substrate/theory/ontology candidates remain quarantined without independent mechanism evidence.

---

## Step 13: Publication package

After real execution and controls:

```bash
make ds005620-autonomy-check
make ds005620-ontology-check
```

This regenerates the full publication artifact chain with real data context.

---

## Makefile targets

| Target | Purpose |
|---|---|
| `make ds005620-real-artifact-plan` | Run P20 artifact build operator, write 6 outputs |
| `make ds005620-real-readiness-loop` | Run artifact plan + P18.3 execution gate |
| `make ds005620-real-execution-gate` | Run P18.3 gate, write 7 outputs |
| `make ds005620-real-operator-check` | Run preflight + real execution gate |
| `make ds005620-preflight` | Run P18.2 preflight |
| `make ds005620-e2e-ci` | Run mock E2E CI pipeline |
| `make ds005620-autonomy-check` | Full mock E2E + artifact chain |

---

## Guardrails

The following guardrails remain active at all times:

- No label inference
- No target fabrication
- No automatic data download
- No automatic peer-review confirmation
- No automatic real contract activation
- No Makefile target executes real data automatically
- No P11/P12/P13/P18 runtime semantic changes
- No weakening of artifact contracts
- No weakening of ontology quarantine
- No empirical claim from artifact readiness alone
- No Level M or Level T empirical claim without real execution, null comparisons, ablations, and controls
- No substrate/theory/ontology candidate promotion
- No metaphysical proof claims

---

## Operator checklist

Before attempting real execution, confirm:

- [ ] Mock E2E completed successfully (`make ds005620-e2e-ci`)
- [ ] Real execution gate reports `next_action = human_peer_review_required`
- [ ] All 18 human peer review checklist items completed
- [ ] Metadata provenance verified independently
- [ ] Reviewed contract reviewed and confirmed by human reviewer
- [ ] Post-execution controls planned (nulls, ablations, leakage, artifacts)
- [ ] Ontology claim scope expectations confirmed with reviewer
