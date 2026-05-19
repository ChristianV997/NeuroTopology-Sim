import argparse
from .common import read_json,write_json
constructs=['boundary','Q','dukkha','exit cost','diagnosis boundary']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--claims',required=True);p.add_argument('--tiers',required=True);p.add_argument('--out',required=True);a=p.parse_args();rows=[]
 for c in read_json(a.claims)['claims']:
  for con in constructs: rows.append({"paper_id":c['paper_id'],"construct":con,"mapping_strength":0.5,"evidence_tier":"T0_speculative_conceptual","suggested_repo_artifacts_to_update":["outputs/literature_senses/theory_integration_digest.md"],"claim_boundary":"no proof","next_action":"watch"})
 write_json(a.out,{"mappings":rows})
