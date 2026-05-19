import argparse
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sources',required=True);p.add_argument('--query-packs',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 s=read_json(a.sources)['sources'];q=read_json(a.query_packs)['query_packs'];rows=[]
 for qp in q:
  for src in s:
   rows.append({"planned_query":qp['query_id'],"source":src['source_id'],"mode":"fixture","live_command_template":"--live --confirm-network","max_results":src['default_query_limit'],"expected_fields":["id","title","abstract"],"rate_limit_notes":src['rate_limit_notes'],"legal_notes":src['legal_notes'],"blocked_without_confirm_network":True,"requires_api_key":bool(src['requires_key'] not in (False,'optional')),"output_target":"outputs/literature_senses/fixture_retrieved_papers.json"})
 write_json(a.out,{"retrieval_plan":rows})