import argparse,json
from pathlib import Path
from datetime import datetime,timezone
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();o=Path(a.out);o.mkdir(parents=True,exist_ok=True);base={'ok':True,'generated_at':datetime.now(timezone.utc).isoformat(),'active_goal':'P40','preset':'toe_research','contribution_target':'>4,000 useful lines if justified.','required_surfaces':['package'],'guardrails':['no live APIs'],'forbidden_patterns':['final theory'],'next_actions':['run cycle'],'real_data_auto_execution_allowed':False,'live_api_calls_allowed':False,'api_key_exposure_allowed':False,'clinical_claims_allowed':False,'ontology_promotion_allowed':False,'proof_claims_allowed':False,'q_qabs_fdress_proof_claims_allowed':False,'toe_validation_claims_allowed':False}
 for f in ['codex_goal_status.json','codex_goal_scorecard.json','codex_goal_rendered_prompt.json','codex_goal_guardrails.json']:(o/f).write_text(json.dumps(base,indent=2))
if __name__=='__main__':main()