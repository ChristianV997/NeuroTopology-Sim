import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--claims',required=True);p.add_argument('--mapping',required=True);p.add_argument('--out',required=True);a=p.parse_args();rows=[]
 for i,c in enumerate(read_json(a.claims)['claims'],1): rows.append({"falsifier_id":f"f{i}","paper_id":c['paper_id'],"affected_claim":c['main_claim_summary'],"affected_constructs":["boundary"],"falsifier_type":"ontology quarantine reinforcement","severity":"medium","action":"add_to_falsifier_watchlist","required_followup":"manual review","claim_demotion_suggestion":"watch"})
 write_json(a.out,{"watchlist":rows})
