# DS005620 Real EEG Integration Plan

This document defines the next execution layer after the DS005620 local artifact pipeline is hardened. It is intentionally downstream of the current P7 validation-hardening work.

It does not make scientific conclusions. It defines contracts for replacing fixture-derived Level M and Level T features with validated local EEG signal extraction while preserving label safety, subject-split discipline, artifact reporting, and evidence guardrails.

## Current completed empirical chain

```text
P0  Dataset contract
P1  Deterministic Level M baseline
P2  Deterministic M+T residual scaffold
P3  Local BIDS inspection contract
P4  Local Level M window extraction scaffold
P5  Local Level T topology extraction scaffold
P6  Local M+T residual orchestration scaffold
P7  Validation hardening and artifact-contract checks
```

## Next target

```text
P8  Real EEG reader adapter contracts
P9  Real Level M feature extraction from local EEG windows
P10 Real Level T topology extraction from analytic phase / montage topology
P11 Real null controls and ablation rerun
P12 Evidence event export and report ingestion
```

## Guardrails

Allowed language:

```text
local signal extraction
EEG reader adapter
operational telemetry
feature candidate
artifact-aware window
residual predictive value
controlled benchmark
metadata contract
```

Forbidden language:

```text
consciousness proof
self proof
soul proof
afterlife proof
liberation detection
enlightenment proof
ultimate reality
ontology proof
Q=self
Q=soul
Q_abs=suffering
f_dress=karma
```

Forbidden label shortcuts:

```text
unresponsive -> unconscious
sedated -> no_experience
behavior_label -> report_label
state_label -> experience_label
```

## P8: Real EEG reader adapter contracts

Purpose:

```text
local EEG files
-> reader capability report
-> channel/sample metadata
-> window-readable signal blocks
-> artifact-aware reader status
```

Expected new module:

```text
sciencer_d/btc_icft/io/eeg_readers.py
sciencer_d/btc_icft/pipelines/inspect_eeg_readers.py
configs/btc_icft/eeg_readers.yaml
tests/btc_icft/test_eeg_reader_contracts.py
```

Supported adapter strategy:

```text
1. stdlib fixture/text adapter for tests
2. optional MNE adapter if mne is installed
3. optional EDF/BDF adapter only if dependency is already available
4. clear unsupported-file status otherwise
```

No required new dependency should be introduced in P8. Optional readers must degrade cleanly.

Required outputs:

```text
outputs/btc_icft/ds005620/eeg_readers/reader_capability_report.json
outputs/btc_icft/ds005620/eeg_readers/file_readability_report.json
outputs/btc_icft/ds005620/eeg_readers/channel_inventory.json
outputs/btc_icft/ds005620/eeg_readers/report.md
```

P8 pass criteria:

```text
- local files are classified by readability
- missing optional dependencies are reported, not fatal
- tests use tiny fixture files only
- no data download
- no model training
- no Level O/C/Q
- no proof/ontology claims
```

## P9: Real Level M feature extraction

Purpose:

```text
P8 readable signal blocks
+ P4 window metadata
-> real Level M spectral/entropy/LZC/artifact features
```

Expected behavior:

```text
- consume P4 m_real windows
- consume P8 readability reports
- read only supported local fixture or local EEG files
- compute feature rows only for readable windows
- emit skipped-window report for unsupported files
- preserve subject/session/run/window/task alignment
```

Required outputs:

```text
outputs/btc_icft/ds005620/m_signal/features_m_signal.csv
outputs/btc_icft/ds005620/m_signal/skipped_windows.json
outputs/btc_icft/ds005620/m_signal/artifact_report.json
outputs/btc_icft/ds005620/m_signal/leakage_report.json
outputs/btc_icft/ds005620/m_signal/omega_event.json
outputs/btc_icft/ds005620/m_signal/report.md
```

## P10: Real Level T topology extraction

Purpose:

```text
P8 readable signal blocks
+ P4 window metadata
+ montage-aware phase-grid topology
-> real Level T topology features
```

Expected behavior:

```text
- compute analytic phase only when signal data and channel metadata are sufficient
- otherwise skip with explicit reason
- run montage topology only on valid channel geometry
- emit quality gates and skipped-window reasons
- do not run residual promotion here
```

Required outputs:

```text
outputs/btc_icft/ds005620/t_signal/features_t_signal.csv
outputs/btc_icft/ds005620/t_signal/topology_quality_report.json
outputs/btc_icft/ds005620/t_signal/skipped_windows.json
outputs/btc_icft/ds005620/t_signal/null_placeholder_report.json
outputs/btc_icft/ds005620/t_signal/omega_event.json
outputs/btc_icft/ds005620/t_signal/report.md
```

## P11: Real null controls and residual rerun

Purpose:

```text
P9 real M features
+ P10 real T features
-> M vs M+T residual benchmark with real null controls
```

Required controls:

```text
channel_shuffle
time_reverse
phase_randomization
subject-safe split check
artifact dominance check
ablation suite
calibration check
```

Required decision rule remains:

```text
delta_auc >= 0.03
delta_ece <= 0 if available
nulls_passed == true
ablations_passed == true
leakage_detected == false
artifact_dominance == false
```

## Evidence-event export

Every stage after P8 should emit an evidence event with:

```text
stage_id
dataset_id
input_artifacts
output_artifacts
claim_scope
allowed_claim
forbidden_claims
guardrail_status
artifact_status
leakage_status
promotion_status
```

Allowed claim template:

```text
This local DS005620-style run produced operational telemetry suitable for controlled residual testing under the specified artifact, leakage, and label-contract guardrails.
```

## Stop conditions

Stop and repair before moving forward if any of the following occur:

```text
- unsafe label inference appears
- subject split is invalid
- row/window alignment is broken
- outputs silently omit required reports
- optional reader failure crashes the pipeline
- generated reports contain banned proof/ontology language
- topology or EEG features are interpreted as ontology proof
```
