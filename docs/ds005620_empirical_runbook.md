# DS005620 Empirical Runbook

This runbook defines the staged BTC/ICFT execution path for DS005620. It is a coordination artifact for contributors and agents. It does not make scientific conclusions. It describes operational dataset, Level M, Level T, and residual-benchmark contracts.

## Current stage map

```text
P0  Dataset contract                  completed by PR #43
P1  Deterministic Level M baseline     completed by PR #48
P2  Deterministic M+T residual scaffold completed by PR #50
P3  Local BIDS inspection contract     completed by PR #53
P4  Local Level M window extraction    Issue #51
P5  Local Level T topology extraction  Issue #52
P6  Local M+T residual orchestration   Issue #54
```

## Scientific guardrails

Allowed framing:

```text
operational telemetry
proxy
candidate metric
local file inspection
window-feature candidate
residual predictive value
deterministic scaffold
evidence event
label contract
future residual testing
```

Forbidden shortcuts:

```text
unresponsive -> unconscious
sedated -> no_experience
behavior_label -> report_label
state_label -> experience_label
```

Forbidden claim class:

```text
No consciousness, self, soul, liberation, afterlife, enlightenment, ontology, or final metaphysical proof claims.
No Q=self, Q=soul, Q_abs=suffering, or f_dress=karma claims.
```

## P3: BIDS inspection contract

Status: completed by PR #53.

Purpose:

```text
local BIDS/OpenNeuro-style root
-> file inventory
-> conservative label candidates
-> contract report
-> cautious report.md
```

Expected command:

```bash
python -m sciencer_d.btc_icft.pipelines.inspect_ds005620_bids \
  --bids-root <local_ds005620_or_fixture_root> \
  --out outputs/btc_icft/ds005620/bids_inspection
```

Expected outputs:

```text
outputs/btc_icft/ds005620/bids_inspection/file_inventory.json
outputs/btc_icft/ds005620/bids_inspection/label_candidates.json
outputs/btc_icft/ds005620/bids_inspection/contract_report.json
outputs/btc_icft/ds005620/bids_inspection/report.md
```

Pass criteria:

```text
- local files are inventoried deterministically
- label candidates are conservative
- missing labels produce warnings, not unsafe inference
- no data is downloaded
- no model training occurs
```

## P4: Local Level M window extraction

Status: active in Issue #51.

Purpose:

```text
BIDS inspection outputs
-> window-level metadata
-> Level M feature candidates
-> artifact/leakage reports
-> omega event
```

Expected command:

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_m_real \
  --inspection outputs/btc_icft/ds005620/bids_inspection \
  --out outputs/btc_icft/ds005620/m_real \
  --task awake_vs_sedated \
  --mock-fixture
```

Expected outputs:

```text
outputs/btc_icft/ds005620/m_real/features_m.csv
outputs/btc_icft/ds005620/m_real/metrics_m.json
outputs/btc_icft/ds005620/m_real/artifact_report.json
outputs/btc_icft/ds005620/m_real/leakage_report.json
outputs/btc_icft/ds005620/m_real/omega_event.json
outputs/btc_icft/ds005620/m_real/report.md
```

Required feature columns:

```text
row_id
subject_id
session_id
run_id
window_id
task_label
state_label
behavior_label
report_label
spectral_power_proxy
entropy_proxy
lzc_proxy
artifact_score
source_file
window_start_s
window_end_s
```

Pass criteria:

```text
- consumes P3 outputs when present
- supports deterministic fixture mode
- fails cleanly if inspection outputs are missing
- preserves state/behavior/report separation
- produces artifact and leakage reports
- does not compute Level T telemetry
- does not run residual promotion
```

## P5: Local Level T topology extraction

Status: queued in Issue #52.

Purpose:

```text
P4 Level M window metadata
-> aligned Level T topology rows
-> topology quality report
-> null-placeholder report
-> artifact-alignment report
-> omega event
```

Expected command:

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_t_real \
  --m-windows outputs/btc_icft/ds005620/m_real \
  --out outputs/btc_icft/ds005620/t_real \
  --mock-fixture
```

Expected outputs:

```text
outputs/btc_icft/ds005620/t_real/features_t.csv
outputs/btc_icft/ds005620/t_real/topology_quality_report.json
outputs/btc_icft/ds005620/t_real/null_placeholder_report.json
outputs/btc_icft/ds005620/t_real/artifact_alignment_report.json
outputs/btc_icft/ds005620/t_real/omega_event.json
outputs/btc_icft/ds005620/t_real/report.md
```

Required topology columns:

```text
row_id
subject_id
session_id
run_id
window_id
task_label
q_net
q_abs
f_dress
defect_density
n_triangles
n_valid_triangles
topology_quality
null_method
null_seed
source_file
window_start_s
window_end_s
```

Pass criteria:

```text
- row_id alignment with P4 windows is preserved
- topology rows are quality-gated
- unavailable readers/data fail cleanly or use fixture mode
- no residual benchmark is run in this stage
```

## P6: Local M+T residual orchestration

Status: queued in Issue #54.

Purpose:

```text
P4 Level M features + P5 Level T features
-> strict row join
-> M-only metrics
-> M+T metrics
-> residual deltas
-> nulls/ablations
-> promotion gate
-> omega event
```

Expected command:

```bash
python -m sciencer_d.btc_icft.pipelines.run_ds005620_mt_real \
  --m-features outputs/btc_icft/ds005620/m_real/features_m.csv \
  --t-features outputs/btc_icft/ds005620/t_real/features_t.csv \
  --out outputs/btc_icft/ds005620/mt_real \
  --mock-fixture
```

Expected outputs:

```text
outputs/btc_icft/ds005620/mt_real/features_joined.csv
outputs/btc_icft/ds005620/mt_real/metrics_mt_real.json
outputs/btc_icft/ds005620/mt_real/nulls_real.json
outputs/btc_icft/ds005620/mt_real/ablations_real.json
outputs/btc_icft/ds005620/mt_real/leakage_report.json
outputs/btc_icft/ds005620/mt_real/artifact_report.json
outputs/btc_icft/ds005620/mt_real/omega_event.json
outputs/btc_icft/ds005620/mt_real/report.md
```

Promotion gate:

```text
delta_auc >= 0.03
delta_ece <= 0 if available
nulls_passed == true
ablations_passed == true
leakage_detected == false
artifact_dominance == false
```

Pass criteria:

```text
- joins only exact row/session/run/window/task matches
- refuses invalid label contracts or unsafe splits
- reports M-only and M+T metrics separately
- separates fixture/proxy controls from real-data controls
- emits explicit promotion_reason
```

## Required validation sequence

Run these after each stage PR when feasible:

```bash
python -m governance.validate
python -m pytest tests/btc_icft -q
python -m sciencer_d.btc_icft.pipelines.run_synthetic_validation --out outputs/btc_icft/synthetic_validation
python main.py --mode synthetic
```

For DS005620 path smoke checks:

```bash
python -m sciencer_d.btc_icft.pipelines.inspect_ds005620_bids --mock --out outputs/btc_icft/ds005620/bids_inspection
python -m sciencer_d.btc_icft.pipelines.run_ds005620_m --out outputs/btc_icft/ds005620/m_baseline --mock
python -m sciencer_d.btc_icft.pipelines.run_ds005620_mt --out outputs/btc_icft/ds005620/mt_residual --mock
```

Add the P4/P5/P6 commands as their modules land.

## Review checklist for every DS005620 PR

```text
- output contract is explicit
- CLI has offline fixture mode
- absent data path fails cleanly
- tests are deterministic and offline
- reports contain cautious operational framing
- label shortcuts are blocked
- generated outputs are not committed
- Level O/C/Q work is not mixed into DS005620 empirical PRs
```

## Artifact Contract Validation

Run after DS005620 stage pipelines emit outputs:

```bash
python tools/validate_ds005620_artifacts.py --root outputs/btc_icft/ds005620
python tools/validate_ds005620_artifacts.py --root outputs/btc_icft/ds005620 --stage mt_real
make validate-ds005620-mt-real
```

This validator checks local artifact shape and guardrail language. It does not compute scientific evidence and does not promote claims.
