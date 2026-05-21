from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, read_json, write_json
REQ=['real_execution_observed','benchmark_completed','omega_invariants_false','null_controls_completed','ablations_completed','leakage_report_passed','artifact_report_passed','statistical_report_passed','human_peer_review_confirmed','ontology_language_clean','publication_readiness_reviewed']
def build(root: Path):
 a=read_json(root/'execution_artifact_audit.json') if (root/'execution_artifact_audit.json').exists() else {}
 status={k:False for k in REQ};status.update({k:a.get(k,False) for k in ['real_execution_observed','benchmark_completed','omega_invariants_false']})
 blocked=[k for k,v in status.items() if not v]
 perm=not blocked
 return {'dataset_id':DATASET_ID,'empirical_claims_permitted':perm,'allowed_claim_level':'publication_ready_limited_empirical' if perm else 'engineering_runtime_only','blocked_by':blocked,'required_before_claims':[k for k in REQ if k in blocked],'human_review_required':True,'claim_language_boundary':'No proof, ontology, or clinical efficacy claims.','publication_ready':perm,'next_action':'Complete real execution, controls, and human review artifacts.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');ap.add_argument('--json-out',default='outputs/btc_icft/ds005620_post_execution_controls/empirical_claim_gate.json');a=ap.parse_args();g=build(Path(a.root));write_json(Path(a.__dict__['json_out']),g)
if __name__=='__main__': main()
