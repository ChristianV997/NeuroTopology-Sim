# DS005620 System Index

## 1. Purpose

This document is a durable navigation index for the DS005620 engineering runtime.
It describes the pipeline stages, runtime gates, ontology gates, language gates,
publication gates, and real/local execution status so that any operator or agent
can orient themselves quickly without reading every runbook.

This document does not change runtime behavior. It is a read-only index.

---

## 2. Current System State

After PR #121 (P18.3 real/local execution gate):

- Mock E2E benchmark execution (`--mock-e2e`) is complete and CI-validated.
- Ontology claim evaluation is integrated; claim scope is capped at `engineering_runtime` for all mock runs.
- Evidence packet, Notion payload, paper skeleton, CI evidence report are all produced by mock pipeline.
- Real/local preflight (P18.2) and real/local execution gate (P18.3) are implemented.
- Language/generated-output gate is active.
- P19.0/P19.1/P19.2 EEG reader preflight and MNE extraction are implemented.
- P9/P10 Level M and Level T signal feature pipelines are implemented.
- Ontology evaluator is integrated with claim-scope quarantine.

**Current bottleneck:** Controlled real/local execution with real DS005620 data under human review. All P11/P12/P13 execution with `--execute --peer-reviewed-contract-confirmed` is manual-only.

---

## 3. Layer Map

```
governance/         — hypothesis specs, activation declarations
contracts/          — reviewed label contracts, ontology claim contracts, language baselines
configs/btc_icft/   — dataset configs
sciencer_d/btc_icft/
  pipelines/        — all runnable pipeline modules
  p18/              — P18.0–P18.3 readiness planner, execution gate
  runtime/          — P18.2 science runtime autonomy kernel
  ontology/         — ontology evaluator
  level_m/          — Level M signal features (P9)
  level_t/          — Level T topology telemetry (P10)
tools/              — validators (ontology language, generated output, contracts, artifacts)
outputs/btc_icft/   — all pipeline outputs (never committed)
docs/               — runbooks and navigation indices
tests/btc_icft/     — all btc_icft test suite
```

---

## 4. Pipeline Stage Map

| Stage | Purpose | Main command | Output root | Auto-runs real data? | Claim scope |
|---|---|---|---|---|---|
| P17.0 | Activation declaration validator | `python -m sciencer_d.btc_icft.pipelines.validate_activation_declaration` | `outputs/btc_icft/ds005620_activation_declaration` | No | engineering runtime |
| P17.1 | Reviewed contract materializer | `python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract` | `outputs/btc_icft/ds005620_reviewed_contract` | No | engineering runtime |
| P18.0 | Real benchmark readiness planner | `python -m sciencer_d.btc_icft.pipelines.check_ds005620_real_benchmark_readiness` | `outputs/btc_icft/ds005620_real_benchmark_readiness` | No | engineering runtime |
| P18.1 | Guarded mock/local executor | `python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --mock-e2e --execute --peer-reviewed-contract-confirmed` | `outputs/btc_icft/ds005620_real_benchmark_execution_mock` | No (mock only without human flags) | engineering runtime |
| P18.2 | Science runtime autonomy kernel | `python -m sciencer_d.btc_icft.pipelines.inspect_science_runtime` | `outputs/btc_icft/science_runtime_inspection` | No | engineering runtime |
| P18.3 | Real/local execution gate | `python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution` | `outputs/btc_icft/ds005620_real_execution_gate` | No | engineering runtime |
| P19.0 | EEG reader preflight | `python -m sciencer_d.btc_icft.pipelines.preflight_eeg_readers --mock-fixture` | `outputs/btc_icft/eeg_reader_preflight/DS005620` | No | engineering runtime |
| P19.1 | MNE extraction adapter | `python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks --mock-fixture` | `outputs/btc_icft/eeg_mne_extract/DS005620` | No | engineering runtime |
| P19.2 | MNE to canonical signal blocks | `python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks --mock-fixture` | `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620` | No | engineering runtime |
| P9 | Level M signal features | `python -m sciencer_d.btc_icft.pipelines.run_ds005620_level_m_signal_features` | `outputs/btc_icft/eeg_level_m/DS005620` | No (with mock fixture) | reviewed-label benchmark |
| P10 | Level T topology telemetry | `python -m sciencer_d.btc_icft.pipelines.run_ds005620_level_t_signal_topology` | `outputs/btc_icft/eeg_level_t/DS005620` | No (with mock fixture) | topology telemetry |
| P11 | M+T residual predictive value benchmark | `python -m sciencer_d.btc_icft.pipelines.run_ds005620_mt_residual_benchmark` (mock) | `outputs/btc_icft/ds005620_real_benchmark_execution_mock` | No (mock only in CI) | residual predictive value |
| Ontology evaluator | Evaluate claim scope and promotion readiness | `make ds005620-ontology-check` | `outputs/btc_icft/ds005620_ontology_evaluation_mock` | No | ontology candidate remains quarantined |
| Evidence packet export | Export structured evidence packet | `make ds005620-export-evidence` | `outputs/btc_icft/ds005620_real_benchmark_execution_mock/evidence_packet.json` | No | engineering runtime |
| Paper skeleton generation | Generate paper skeleton from evidence | `make ds005620-paper-skeleton` | `outputs/btc_icft/ds005620_real_benchmark_execution_mock/paper_skeleton*.md` | No | engineering runtime |
| CI evidence report | Machine-readable CI evidence | `make ds005620-ci-evidence-report` | `outputs/btc_icft/ds005620_real_benchmark_execution_mock/ci_evidence_report.*` | No | engineering runtime |
| Generated-output language gate | Scan generated artifacts for unsafe language | `make ds005620-generated-artifact-check` | (report files in outputs) | No | language governance |

---

## 5. Runtime Gates

| Gate | What it blocks | Command | Notes |
|---|---|---|---|
| Mock E2E gate | Runs P12→P13→P11 with in-tree fixtures only | `make ds005620-e2e-ci` | CI-safe; no real data |
| Real/local preflight | Checks all real-data prerequisites | `make ds005620-preflight` | Planning only; no execution |
| Real/local execution gate | Full gate plan before any real execute | `make ds005620-real-execution-gate` | Planning only; no execution |
| Operator check | Combines preflight + execution gate | `make ds005620-real-operator-check` | Human review required before proceeding |
| Autonomy check | Full mock E2E + artifact + ontology checks | `make ds005620-autonomy-check` | CI-safe |

---

## 6. Ontology Gates

The ontology evaluator applies claim-scope quarantine at every run. No automatic promotion occurs.

| Gate | What it enforces | Promotion path |
|---|---|---|
| C (substrate) | Substrate claim requires independent biophysical mechanism evidence | Manual out-of-band human review only |
| Q (theory) | Theory claim requires human review and consistent empirical record | Manual out-of-band human review only |
| O (ontology candidate) | Ontology candidate remains quarantined by default | Independent dataset replication + independent mechanism evidence + evaluated alternatives + human review |

`make ds005620-ontology-check` — evaluates claim scope for mock artifacts.

---

## 7. Language Gates

| Gate | Command | Scope |
|---|---|---|
| Repo-wide baseline-aware scan | `make ontology-language-check` | All repo docs and configs (baseline waivers active) |
| Strict generated-output scan | `make ontology-language-check-strict-outputs` | Generated outputs; no baseline waivers |
| DS005620 generated-output profile | `make ds005620-generated-language-check` | DS005620 output roots only |
| DS005620 generated artifact check | `make ds005620-generated-artifact-check` | Full generated artifact chain including language gate |
| GitHub governance check | `make github-governance-check` | GitHub workflow governance policies |

---

## 8. Publication Gates

The publication path requires all of the following before a paper can claim empirical results:

1. Real DS005620 data placed and verified locally.
2. P17.1 reviewed contract materialized with peer-reviewed labels.
3. P19.0/P19.1/P19.2 EEG extraction completed under MNE.
4. P9 Level M features_m_signal.csv present.
5. P10 Level T features_t_signal.csv present.
6. P11/P12/P13 executed with `--execute --peer-reviewed-contract-confirmed` by a human operator.
7. Null comparisons, ablations, leakage report, and artifact report present.
8. Ontology evaluation completed; claim scope confirmed by human review.
9. Language gate passes on all generated outputs.
10. Evidence packet and paper skeleton reviewed by a human.

**Mock E2E artifacts do not constitute real empirical evidence and must not be cited as such.**

---

## 9. Real/Local Execution Status

- P18.3 gate: **Implemented**. Produces execution gate plan; does not auto-execute.
- Real execution command is generated for manual use only.
- No CI target auto-runs `--execute --peer-reviewed-contract-confirmed` on real data.
- Human operator must run the generated command after verifying all prerequisites.

---

## 10. Remaining Real-Data Blockers

| Blocker | Required step |
|---|---|
| `data/DS005620/events.tsv` not present | Human must place DS005620 metadata locally |
| `outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json` | Run P17.1 after placing metadata |
| `outputs/btc_icft/eeg_mne_extract/DS005620/` | Run P19.1 MNE extraction with MNE installed |
| `outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620/` | Run P19.2 signal-block conversion |
| `features_m_signal.csv`, `features_t_signal.csv` | Run P9/P10 on real signal blocks |
| Peer-reviewed label contract confirmation | Human must confirm labels match reviewed contract |

---

## 11. Safe Next Milestones

| Milestone | Owner lane | Status |
|---|---|---|
| P20: DS005620 real artifact build operator | Claude | Assigned |
| PR #114 ontology review governance merge | Codex | Assigned |
| PR #122 obsolete conflict branch cleanup | Codex | Assigned |
| Navigation and operator-index layer (this doc) | Copilot | In progress |
| Real/local operator execution (human-gated) | Human operator | Blocked on real data |

---

## 12. Files and Docs to Read First

For any new operator or agent working on DS005620:

| Priority | File | What it covers |
|---|---|---|
| 1 | `docs/ds005620_system_index.md` (this file) | Navigation overview |
| 2 | `docs/ds005620_real_local_operator_runbook.md` | Real/local execution steps |
| 3 | `docs/ds005620_artifact_contracts.md` | Artifact contract definitions |
| 4 | `docs/ds005620_ontology_evaluation.md` | Ontology claim-scope rules |
| 5 | `docs/ontology_claim_language_guardrails.md` | Language gate rules |
| 6 | `docs/science_runtime_autonomy_kernel.md` | P18.2 runtime kernel |
| 7 | `docs/ds005620_real_benchmark_readiness_runbook.md` | P18.0 readiness planning |
| 8 | `docs/eeg_reader_preflight_runbook.md` | P19.0 EEG preflight |
| 9 | `docs/eeg_mne_adapter_runbook.md` | P19.1 MNE extraction |
| 10 | `docs/mne_signal_block_conversion_runbook.md` | P19.2 signal-block conversion |
| 11 | `docs/ds005620_reviewed_contract_activation_runbook.md` | P17.1 contract materialization |
| 12 | `docs/ds005620_agent_coordination_map.md` | Agent lane coordination |
| 13 | `docs/ds005620_command_surface.md` | Full command reference |
| 14 | `docs/ds005620_artifact_lifecycle.md` | Artifact flow overview |
