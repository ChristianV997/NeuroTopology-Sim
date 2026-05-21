from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
IDS=['level_m_only','level_t_only','m_plus_t','no_topology_features','no_spectral_features','no_complexity_features','no_subject_covariates','no_session_covariates','topology_only_after_power_control','reduced_feature_set']
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();out=Path(a.out)
    rows=[{'ablation_id':x,'name':x.replace('_',' '),'purpose':'Test robustness and claim sensitivity.','input_artifacts_required':['stage_results.json'],'expected_output':f'{x}_ablation.json','tests_claim':'feature_component_necessity','failure_condition':'ablation_not_explainable_or_inversion','claim_implication':'empirical_claims_blocked_until_resolved','safe_status':'planned_only'} for x in IDS]
    write_json(out/'ablation_plan.json',{'dataset_id':DATASET_ID,'ablations':rows});write_json(out/'ablations_required.json',{'dataset_id':DATASET_ID,'required_ablation_ids':IDS})
if __name__=='__main__': main()
