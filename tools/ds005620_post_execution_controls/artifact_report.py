from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, write_json
N=[('eeg_quality_bad_channel_report','EEG quality / bad channel report'),('missing_sample_report','missing sample report'),('preprocessing_provenance','preprocessing provenance'),('filter_settings_provenance','filter settings provenance'),('epoch_rejection_report','epoch rejection report'),('montage_layout_provenance','montage / layout provenance'),('interpolation_settings','interpolation settings'),('feature_extraction_provenance','feature extraction provenance'),('topology_grid_refinement_provenance','topology grid/refinement provenance'),('version_hash_manifest','version/hash manifest')]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();rows=[{'artifact_check_id':k,'required_artifact':v,'reason':'Required for reproducibility and evidence integrity.','status':'not_run_real_data_pending','claim_implication':'empirical_claims_blocked'} for k,v in N];write_json(Path(a.out)/'artifact_report_template.json',{'dataset_id':DATASET_ID,'checks':rows})
if __name__=='__main__': main()
