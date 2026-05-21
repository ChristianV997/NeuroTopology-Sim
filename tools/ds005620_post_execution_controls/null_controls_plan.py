from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
IDS=['channel_shuffle_null','time_reversal_null','phase_randomization_null','label_permutation_null','subject_blocked_permutation_null','frequency_band_control','random_feature_control','spatial_layout_control','topology_interpolation_control','spectral_power_matched_null']
def build():
    rows=[]
    for cid in IDS: rows.append({'control_id':cid,'name':cid.replace('_',' '),'purpose':'Stress-test non-causal and leakage-sensitive signal paths.','input_artifacts_required':['stage_results.json','stage_outputs/p11_signal_mt/'],'expected_output':f'{cid}_results.json','failure_condition':'control_outperforms_primary_or_unstable','claim_implication':'empirical_claims_blocked_until_resolved','safe_status':'planned_only','manual_or_auto':'manual','can_run_without_real_data':False})
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();out=Path(a.out);rows=build();write_json(out/'null_controls_plan.json',{'dataset_id':DATASET_ID,'controls':rows});write_json(out/'nulls_required.json',{'dataset_id':DATASET_ID,'required_control_ids':IDS})
if __name__=='__main__': main()
