import argparse,json
from pathlib import Path
from datetime import datetime,timezone
FILES=['toe_literature_bridge_status.json','toe_priority_matrix.json','toe_topology_telemetry_upgrade.json','toe_cosmology_constraints.json','toe_gravitational_wave_constraints.json','toe_consciousness_adversarial_matrix.json','toe_equation_registry.json','toe_falsifier_watchlist.json']
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();o=Path(a.out);o.mkdir(parents=True,exist_ok=True);base={'ok':True,'generated_at':datetime.now(timezone.utc).isoformat(),'toe_validation_claims_allowed':False,'final_theory_claims_allowed':False,'consciousness_proof_claims_allowed':False,'clinical_claims_allowed':False,'ontology_promotion_allowed':False,'q_qabs_fdress_proof_claims_allowed':False,'real_data_auto_execution_allowed':False,'live_api_calls_allowed':False,'api_key_exposure_allowed':False,'active_goal':'P40','preset':'toe_research','contribution_target':'>4,000 useful lines if justified.','required_surfaces':['package'],'guardrails':['no proof'], 'forbidden_patterns':['final theory'], 'next_actions':['validate']}
 for f in FILES:(o/f).write_text(json.dumps(base,indent=2))
if __name__=='__main__':main()