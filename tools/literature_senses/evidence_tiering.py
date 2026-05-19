import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();rows=[]
 for c in read_json(a.input)['claims']:
  rows.append({"paper_id":c['paper_id'],"evidence_tier":"T0_speculative_conceptual","rationale":"fixture","can_support":["evidence mapping"],"cannot_support":["proof claims","clinical treatment"],"promotion_requirements":["real studies"],"demotion_triggers":["overclaim"]})
 write_json(a.out,{"matrix":rows})
