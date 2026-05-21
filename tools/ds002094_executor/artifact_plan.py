from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json
STAGES=["local_data_root","metadata_discovery","human_reviewed_label_contract","reader_preflight","mne_extraction_plan","canonical_signal_blocks_plan","level_m_adapter_plan","level_t_adapter_plan","real_execution_gate","post_execution_controls_interface"]
def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
 rows=[]
 for s in STAGES:
  manual=s not in {"local_data_root","metadata_discovery","reader_preflight","artifact_plan"}
  rows.append({"stage_id":s,"status":"planned","safe_to_auto_run":not manual,"manual_required":manual,"input_required":["prior_stage"],"output_expected":[f"{s}.json"],"blocked_by":[] if not manual else ["human_review"],"next_action":"execute_manually_with_human_review" if manual else "run_local_inspection"})
 d={"dataset_id":DATASET_ID,"stages":rows,**GUARDRAIL_FLAGS}
 write_json(Path(args.out)/'artifact_plan.json',d)
if __name__=='__main__': main()
