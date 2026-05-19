import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--query-packs',required=True);p.add_argument('--out',required=True);a=p.parse_args();
 rec=read_json(a.input)['retained_records']
 for r in rec:
  r.update({k:0.6 for k in ['relevance_score','novelty_score','evidence_strength_score','citation_influence_score','recency_score','method_quality_score','replication_value_score','falsifier_value_score','integration_value_score','safety_value_score']});r['total_priority_score']=6.0
 write_json(a.out,{"papers":rec})
