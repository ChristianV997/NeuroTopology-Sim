from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
IDS=['pre_registered_primary_metric','confidence_intervals','permutation_p_values','effect_sizes','calibration_metrics','cross_validation_split_description','bootstrap_stability','multiple_comparison_correction','baseline_comparison','uncertainty_statement']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();rows=[{'stat_check_id':i,'metric_or_test':i,'required_input':'real_execution_outputs_and_analysis_notes','status':'not_run_real_data_pending','failure_condition':'missing_or_invalid_statistical_evidence','claim_implication':'empirical_claims_blocked'} for i in IDS];write_json(Path(a.out)/'statistical_report_template.json',{'dataset_id':DATASET_ID,'checks':rows})
if __name__=='__main__': main()
