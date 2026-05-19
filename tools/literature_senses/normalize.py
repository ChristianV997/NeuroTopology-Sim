import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();
 ps=read_json(a.input)['papers']
 for x in ps: x.setdefault('evidence_state','abstract_only');x.setdefault('claim_scope','literature_summary');x['title']=x['title'].strip();
 write_json(a.out,{"papers":ps})
