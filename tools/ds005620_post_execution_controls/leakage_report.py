from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
IDS=['subject_leakage_check','session_leakage_check','trial_order_leakage_check','label_source_leakage_check','preprocessing_leakage_check','feature_normalization_leakage_check','train_test_split_leakage_check','hyperparameter_selection_leakage_check','repeated_measure_leakage_check','artifact_path_leakage_check']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();rows=[{'check_id':i,'risk':'Potential leakage bias','required_evidence':'manual_audit_and_logs','failure_condition':'leakage_confirmed_or_unresolved','claim_implication':'empirical_claims_blocked','status':'not_run_real_data_pending'} for i in IDS];write_json(Path(a.out)/'leakage_report_template.json',{'dataset_id':DATASET_ID,'checks':rows})
if __name__=='__main__': main()
