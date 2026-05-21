import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();rows=[]
 for r in read_json(a.input)['papers']:
  rows.append({"paper_id":r['id'],"main_claim_summary":"Fixture claim extraction only; not a real literature claim.","method":"synthetic","dataset_or_subject":"fixture","metric":"n/a","intervention_or_model":"n/a","limitations":["synthetic fixture"],"contradicted_by":[],"possible_construct_links":["boundary"],"possible_observables":["score"],"claim_scope":"literature_summary","evidence_state":"not_validated_in_repo"})
 write_json(a.out,{"claims":rows})
