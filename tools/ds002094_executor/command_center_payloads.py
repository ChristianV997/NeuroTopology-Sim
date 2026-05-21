from __future__ import annotations
import argparse
from pathlib import Path
from . import DEFAULT_OUT, GUARDRAIL_FLAGS, read_json, write_json

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(DEFAULT_OUT)); ap.add_argument('--out',default='outputs/command_center/mock_payloads'); args=ap.parse_args()
 root=Path(args.root); out=Path(args.out)
 common={"real_data_auto_execution_allowed":False,"downloads_data":False,"label_inference_allowed":False,"target_fabrication_allowed":False,"empirical_claims_permitted":False,"ontology_promotion_allowed":False,"human_peer_review_auto_confirmation_allowed":False}
 write_json(out/'ds002094_executor_status.json',{**common,**read_json(root/'dataset_registry.json')})
 write_json(out/'ds002094_local_data_preflight.json',{**common,**read_json(root/'local_data_preflight.json')})
 write_json(out/'ds002094_contract_requirements.json',{**common,**read_json(root/'contract_requirements.json')})
 write_json(out/'ds002094_real_execution_gate.json',{**common,**read_json(root/'real_execution_gate.json')})
 write_json(out/'ds002094_post_execution_controls_interface.json',{**common,**read_json(root/'post_execution_controls_interface.json')})
 write_json(out/'ds002094_next_actions.json',{**common,"next_action":"provide_local_DS002094_root"})
if __name__=='__main__': main()
