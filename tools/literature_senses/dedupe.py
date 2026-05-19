import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();ps=read_json(a.input)['papers']
 seen={};ret=[];groups=[]
 for r in ps:
  k=(r.get('doi') or r.get('pmid') or r['title'].lower()+str(r.get('year')))
  if k in seen: groups.append([seen[k],r['id']])
  else: seen[k]=r['id'];ret.append(r)
 write_json(a.out,{"duplicates_removed":len(ps)-len(ret),"duplicate_groups":groups,"retained_records":ret})
