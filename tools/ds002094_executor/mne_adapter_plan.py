from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
 d={"dataset_id":DATASET_ID,"adapter_type":"planned_stub","input_required":["local_DS002094_bids_root","reader_mapping"],"output_expected":["canonical_signal_blocks_plan.json"],"manual_command_template":"python -m sciencer_d.btc_icft.pipelines.run_ds002094_mne_adapter --dataset-root <LOCAL_DS002094_ROOT> --contract <HUMAN_REVIEWED_CONTRACT_PATH> --manual-only", "not_executed_by_tool":True,"requires_human_local_data":True,"requires_human_review":True,"blocked_by":["local_data","human_reviewed_contract","reader_mapping"],"next_action":"human_prepare_manual_adapter_run",**GUARDRAIL_FLAGS}
 write_json(Path(args.out)/'mne_adapter_plan.json',d)
if __name__=='__main__': main()
