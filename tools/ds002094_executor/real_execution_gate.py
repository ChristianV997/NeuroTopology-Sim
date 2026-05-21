from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args(); out=Path(args.out)
 cmd="python -m sciencer_d.btc_icft.pipelines.run_ds002094_real_benchmark --dataset-root <LOCAL_DS002094_ROOT> --contract <HUMAN_REVIEWED_CONTRACT_PATH> --execute --peer-reviewed-contract-confirmed --manual-only"
 d={"dataset_id":DATASET_ID,"ready_for_real_execution":False,"peer_review_confirmed_by_human":False,"can_use_execute_flag":False,"can_use_peer_reviewed_contract_confirmed_flag":False,"can_auto_execute":False,"dataset_specific_executor_available":"template_only","blocked_by":["local_data","human_peer_review","dataset_specific_reader"],"next_action":"complete_manual_preconditions","manual_command_template":cmd,"not_executed_by_tool":True,"requires_human_peer_review":True,**GUARDRAIL_FLAGS}
 write_json(out/'real_execution_gate.json',d); write_json(out/'manual_real_execution_command_plan.json',{"dataset_id":DATASET_ID,"manual_command_template":cmd,"not_executed_by_tool":True})
if __name__=='__main__': main()
