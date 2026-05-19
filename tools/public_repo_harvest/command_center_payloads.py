import argparse, os
from .common import read_json, write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();os.makedirs(a.out,exist_ok=True)
 write_json(os.path.join(a.out,'public_repo_harvest_status.json'),{"status":"ready","root":a.root})
 write_json(os.path.join(a.out,'public_repo_candidates.json'),read_json(os.path.join(a.root,'candidate_repo_matrix.json')))
 write_json(os.path.join(a.out,'public_repo_license_matrix.json'),read_json(os.path.join(a.root,'license_compatibility_matrix.json')))
 write_json(os.path.join(a.out,'public_repo_reusable_patterns.json'),read_json(os.path.join(a.root,'reusable_pattern_registry.json')))
 write_json(os.path.join(a.out,'public_repo_integration_blueprint.json'),read_json(os.path.join(a.root,'subsystem_integration_blueprint.json')))
 write_json(os.path.join(a.out,'public_repo_priority_queue.json'),read_json(os.path.join(a.root,'integration_priority_queue.json')))
 write_json(os.path.join(a.out,'public_repo_guardrails.json'),{"guardrails":["no_blind_copy","license_governed","offline_first","claim_safe"]})
