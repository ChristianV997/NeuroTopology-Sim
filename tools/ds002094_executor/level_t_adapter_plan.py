from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
 d={"dataset_id":DATASET_ID,"level_t_features_planned":["phase_field_proxy","phase_singularity_candidate","Q_candidate","Qabs_candidate","fdress_candidate","topology_null_controls_required"],"input_artifacts_required":["canonical_signal_blocks","null_control_plan"],"output_expected":["level_t_topology_candidates.parquet"],"topology_features":["phase_field_proxy","phase_singularity_candidate","Q_candidate","Qabs_candidate","fdress_candidate","topology_null_controls_required"],"claim_scope":"topology_telemetry_candidate","blocked_claims":["Q/Qabs/fdress proof claims","consciousness proof claims","ontology promotion"],**GUARDRAIL_FLAGS}
 write_json(Path(args.out)/'level_t_adapter_plan.json',d)
if __name__=='__main__': main()
