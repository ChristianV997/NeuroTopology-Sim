import argparse, json
from pathlib import Path
from .common import now_iso
FILES=['literature_senses_status.json','literature_query_packs.json','literature_scored_papers.json','literature_falsifier_watchlist.json','literature_theory_digest.json','literature_evidence_tiers.json','literature_construct_mapping.json']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();Path(a.out).mkdir(parents=True,exist_ok=True)
 base={"ok":True,"generated_at":now_iso(),"source_artifacts":[a.root],"claim_scope":"literature_summary","evidence_state":"not_validated_in_repo","guardrails":["no live api"],"limitations":["fixtures"],"next_actions":["manual review"],"live_api_calls_enabled":False,"network_required":False,"api_keys_required":False,"diagnosis_claims_allowed":False,"treatment_claims_allowed":False,"clinical_efficacy_claims_allowed":False,"ontology_promotion_allowed":False,"proof_claims_allowed":False,"real_data_auto_execution_allowed":False}
 for f in FILES: json.dump(base,open(Path(a.out)/f,'w'),indent=2)
