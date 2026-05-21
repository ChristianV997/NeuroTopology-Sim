from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
 d={"dataset_id":DATASET_ID,"level_m_features_planned":["spectral_power","complexity_proxy","metadata_covariates_if_reviewed"],"input_artifacts_required":["canonical_signal_blocks"],"output_expected":["level_m_features_candidates.parquet"],"baseline_features":["spectral_power","complexity_proxy","metadata_covariates_if_reviewed"],"claim_scope":"marker_level_candidate",**GUARDRAIL_FLAGS}
 write_json(Path(args.out)/'level_m_adapter_plan.json',d)
if __name__=='__main__': main()
