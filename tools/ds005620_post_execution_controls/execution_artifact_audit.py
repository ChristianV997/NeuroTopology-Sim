from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
EXPECTED=["ds005620_real_benchmark_execution.json","stage_execution_plan.json","stage_results.json","execution_blockers.json","omega_event.json","report.md","stage_outputs/p12_eeg_labels/","stage_outputs/p13_eeg_targets/","stage_outputs/p11_signal_mt/","stage_outputs/p11_signal_mt/metrics_signal_mt.json"]

def exists(root: Path, item: str)->bool:
    p=root/item.rstrip('/')
    return p.is_dir() if item.endswith('/') else p.exists()

def build(execution_root: Path):
    present=[x for x in EXPECTED if exists(execution_root,x)]
    missing=[x for x in EXPECTED if x not in present]
    mock_detected='mock' in execution_root.name.lower() or 'mock' in str(execution_root).lower()
    real_obs=not mock_detected and all(x in present for x in EXPECTED)
    return {"dataset_id":DATASET_ID,"execution_root":str(execution_root),"execution_artifacts_present":present,"missing_artifacts":missing,"real_execution_observed":real_obs,"mock_execution_detected":mock_detected,"benchmark_completed":real_obs,"p12_succeeded":exists(execution_root,'stage_outputs/p12_eeg_labels/'),"p13_succeeded":exists(execution_root,'stage_outputs/p13_eeg_targets/'),"p11_succeeded":exists(execution_root,'stage_outputs/p11_signal_mt/metrics_signal_mt.json'),"omega_invariants_false":exists(execution_root,'omega_event.json') and real_obs,"eligible_for_controls":real_obs,"blocked_by":[] if real_obs else ["real_execution_not_observed"],"next_action":"Run manual DS005620 real execution and place artifacts in execution root."}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execution-root',default='outputs/btc_icft/ds005620_real_benchmark_execution');ap.add_argument('--runbook-root',default='outputs/btc_icft/ds005620_real_runbook');ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args()
    out=Path(a.out);audit=build(Path(a.execution_root));write_json(out/'execution_artifact_audit.json',audit);write_json(out/'missing_execution_artifacts.json',{"dataset_id":DATASET_ID,"missing_artifacts":audit['missing_artifacts']})
if __name__=='__main__': main()
