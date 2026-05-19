import argparse
from .common import read_json, write_json

def gen(query_packs):
 out=[];i=1
 for qp in query_packs:
  for _ in range(2):
   out.append({"id":f"fx-{i}","source":"local_fixture","title":f"Synthetic {qp['query_id']} study {i}","authors":["Fixture A"],"year":2024,"venue":"FixtureConf","url":f"https://fixture.local/{i}","abstract":"Fixture claim extraction only; not a real literature claim.","query_pack":qp['query_id'],"retrieval_mode":"fixture","fixture_generated":True,"not_real_paper":True,"do_not_cite_as_literature":True});i+=1
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mode',default='fixture');p.add_argument('--query-packs',required=True);p.add_argument('--out',required=True);a=p.parse_args();
 q=read_json(a.query_packs)['query_packs'];write_json(a.out,{"papers":gen(q)})
