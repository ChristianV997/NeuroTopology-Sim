# DS005620 Artifact Lifecycle

## 1. Purpose

This document traces the complete artifact lifecycle for the DS005620 engineering
runtime: from raw metadata through signal extraction, feature pipelines, benchmark
execution, ontology evaluation, and publication preparation.

Key distinctions are made explicit:
- artifact present ≠ human reviewed
- human reviewed ≠ empirical claim ready
- empirical candidate ≠ ontology promotion
- mock E2E ≠ real empirical evidence

---

## 2. Artifact Lifecycle Overview

```
data/DS005620/events.tsv                        (human-placed metadata)
  │
  ▼
governance/declarations/...                     (P17.0: activation declaration — human-authored)
  │
  ▼
outputs/btc_icft/ds005620_reviewed_contract/    (P17.1: reviewed contract materialization)
  ├── reviewed_contract.json
  ├── p12_external_contract.json                ← P12-compatible active contract
  ├── p18_handoff.json
  ├── reviewed_activation_report.json
  ├── omega_event.json
  └── report.md
  │
  ▼
outputs/btc_icft/eeg_reader_preflight/DS005620/ (P19.0: EEG reader preflight)
  ├── eeg_file_manifest.csv
  ├── reader_capability_report.json
  ├── reader_preflight_summary.json
  ├── extraction_blockers.json
  ├── omega_event.json
  └── report.md
  │
  ▼
outputs/btc_icft/eeg_mne_extract/DS005620/      (P19.1: MNE extraction adapter)
  ├── mne_signal_metadata.json
  ├── mne_signal_windows.csv
  ├── mne_signal_window_values.json
  ├── omega_event.json
  └── report.md
  │
  ▼
outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/  (P19.2: canonical signal blocks)
  ├── signal_block_inventory.json
  ├── window_inventory.csv
  ├── window_signal_values.json
  ├── reader_alignment_report.json
  ├── rejected_windows.json
  ├── omega_event.json
  └── report.md
  │
  ▼
outputs/btc_icft/eeg_level_m/DS005620/          (P9: Level M signal features)
  └── features_m_signal.csv
  │
  ▼
outputs/btc_icft/eeg_level_t/DS005620/          (P10: Level T topology telemetry)
  └── features_t_signal.csv
  │
  ▼
outputs/btc_icft/ds005620_real_benchmark_execution*/   (P11/P12/P13: benchmark)
  ├── stage_execution_plan.json
  ├── stage_results.json
  ├── execution_blockers.json
  ├── omega_event.json
  └── validation_summary.json
  │
  ▼
(controls required for empirical readiness)
  ├── leakage_report.json
  ├── artifact_report.json
  ├── nulls.json
  └── ablations.json
  │
  ▼
outputs/btc_icft/ds005620_ontology_evaluation*/        (ontology evaluation)
  ├── ontology_evaluation.json
  ├── claim_scope_summary.json
  └── report.md
  │
  ▼
evidence_packet.json                                   (evidence packet export)
  │
  ▼
paper_skeleton*.md                                     (paper skeleton generation)
  │
  ▼
[human review gate]
  │
  ▼
publication package
```

---

## 3. Mock E2E Artifacts

Mock E2E artifacts are produced by `make ds005620-e2e-mock` using in-tree fixtures.
They exercise the full pipeline structure without real DS005620 data.

Output root: `outputs/btc_icft/ds005620_real_benchmark_execution_mock/`

| Artifact | Purpose |
|---|---|
| `stage_execution_plan.json` | Ordered stage plan (P12→P13→P11) |
| `stage_results.json` | Mock stage outcomes |
| `execution_blockers.json` | Omega false-invariant enforced blockers |
| `omega_event.json` | Safe claim record with source_contracts_modified=false |
| `validation_summary.json` | E2E validator output |
| `contract_validation_summary.json` | Contract shape validator output |
| `ci_evidence_report.json` | Machine-readable CI evidence |
| `ci_evidence_report.md` | Human-readable CI evidence |
| `artifact_manifest.json` | Artifact inventory |
| `evidence_packet.json` | Structured evidence export |
| `paper_skeleton*.md` | Paper section stubs |

**Mock E2E is not real empirical evidence.** Mock artifacts confirm engineering runtime
correctness only. They do not support empirical claims about DS005620 subjects.

---

## 4. Real/Local Prerequisite Artifacts

These artifacts must be present and human-verified before any real benchmark execution:

| Artifact | Source | Status gate |
|---|---|---|
| `data/DS005620/events.tsv` | Human-placed from official DS005620 dataset | Must exist; provenance must be verified |
| `p12_external_contract.json` | P17.1 materialization of human-authored declaration | `activation_allowed=true` required |
| `eeg_file_manifest.csv` | P19.0 EEG reader preflight | No extraction blockers |
| `mne_signal_windows.csv` | P19.1 MNE extraction | Requires `mne` installed |
| `signal_block_inventory.json` | P19.2 signal-block conversion | `ready_for_level_m_signal=true` required |
| `features_m_signal.csv` | P9 Level M signal features | Join keys match contract |
| `features_t_signal.csv` | P10 Level T topology telemetry | Join keys match contract |

---

## 5. Contract Artifacts

| Artifact | Location | What it governs |
|---|---|---|
| `p12_external_contract.json` | `outputs/btc_icft/ds005620_reviewed_contract/` | Reviewed external label contract; P12-compatible |
| `contracts/btc_icft/ds005620/p18_1/*.contract.json` | Repository | P18.1 artifact shape contracts |
| `contracts/btc_icft/ontology_claims/claim_language_baseline.json` | Repository | Language gate baseline waivers |
| `contracts/btc_icft/ontology_claims/` | Repository | Ontology claim contracts |

---

## 6. Signal Artifacts

| Artifact | Stage | Notes |
|---|---|---|
| `mne_signal_windows.csv` | P19.1 | Raw MNE-extracted windows; not label-aligned |
| `window_inventory.csv` | P19.2 | Canonical window inventory; join key coverage checked |
| `window_signal_values.json` | P19.2 | Signal values aligned to canonical schema |
| `features_m_signal.csv` | P9 | Level M signal features; single-row summary (dataset/task/metrics) |
| `features_t_signal.csv` | P10 | Level T topology telemetry; single-row summary |
| `features_m_signal_labeled.csv` | P11/P12 | Label-aligned feature set (real run only) |
| `label_alignment.csv` | P11/P12 | Alignment between signal windows and reviewed labels |

---

## 7. M/T Benchmark Artifacts

| Artifact | Stage | Notes |
|---|---|---|
| `metrics_signal_mt.json` | P11 | M+T benchmark results; residual predictive value only |
| `leakage_report.json` | P11 | Required control for any empirical claim |
| `artifact_report.json` | P11 | EEG artifact contamination report |
| `nulls.json` | P11 | Null distribution comparisons |
| `ablations.json` | P11 | Ablation study results |

All M/T benchmark artifacts require real data and human-gated execution.
Mock M/T artifacts confirm pipeline structure only.

---

## 8. Ontology Artifacts

| Artifact | Stage | Notes |
|---|---|---|
| `ontology_evaluation.json` | Ontology evaluator | Claim scope, promotion flags, required evidence status |
| `claim_scope_summary.json` | Ontology evaluator | Per-claim-level summary |
| Ontology bridge registry entries | Ontology layer | C/Q/O candidate records; always quarantined unless promoted out-of-band |

**Ontology candidate remains quarantined** by default in every run mode.
Promotion to C/Q/O requires independent dataset replication, independent mechanism
evidence, evaluated alternatives, and manual out-of-band human review.

---

## 9. Evidence / Publication Artifacts

| Artifact | Stage | Notes |
|---|---|---|
| `evidence_packet.json` | Evidence packet export | Structured evidence; claim scope from ontology evaluator |
| `paper_skeleton*.md` | Paper skeleton generator | Section stubs with placeholder content |
| Publication package | Manual assembly | Assembled from evidence packet + reviewed paper skeleton + human review |

---

## 10. Generated-Language Reports

| Artifact | Gate | Notes |
|---|---|---|
| Language scan report (JSON) | `make ds005620-generated-language-check` | Per-file findings; fails on unsafe phrases |
| Language scan report (Markdown) | `make ds005620-generated-language-check` | Human-readable summary |
| Strict outputs report | `make ontology-language-check-strict-outputs` | No baseline waivers |

---

## 11. Artifact Readiness vs. Empirical Readiness

| Condition | Sufficient for... | Not sufficient for... |
|---|---|---|
| Mock E2E artifacts present | Engineering runtime validation | Any empirical claim |
| Real prerequisite artifacts present | Running real benchmark | Empirical claims (controls required) |
| Benchmark artifacts present | Descriptive results | Empirical claims (controls + human review required) |
| All controls present (leakage, nulls, ablations, artifacts) | Reporting empirical benchmark findings | Ontology promotion |
| Human review completed | Reporting empirical benchmark findings | Ontology promotion (independent replication required) |

---

## 12. Artifact Readiness vs. Ontology Promotion

Ontology promotion (C substrate → Q theory → O ontology candidate) follows a separate,
more stringent path:

| Requirement | Status in current system |
|---|---|
| Empirical benchmark with real data + controls | Not yet run |
| Independent dataset replication | Not available |
| Independent biophysical mechanism evidence | Not available |
| Evaluated alternative explanations | Not available |
| Human out-of-band review | Required; not yet done |
| Ontology evaluator promotion | Never automatic; requires all of the above |

Until all conditions are met, all ontology-related artifacts carry:
`claim_scope: engineering_runtime`, `ontology_status: ontology_quarantined`.
