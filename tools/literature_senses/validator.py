import argparse, os, json, sys
REQ=['source_registry.json','query_pack_registry.json','retrieval_plan.json','fixture_retrieved_papers.json','normalized_papers.json','deduped_papers.json','scored_papers.json','claim_extraction_report.json','evidence_tier_matrix.json','construct_mapping_matrix.json','falsifier_watchlist.json','theory_integration_digest.md','living_review_report.md','generation_manifest.json']
BAD=['proves consciousness','clinical treatment','validated theory of everything','Qabs proves']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--json-out',required=True);a=p.parse_args();v=[]
 for f in REQ:
  if not os.path.exists(os.path.join(a.root,f)): v.append(f'missing:{f}')
 for fn in ['theory_integration_digest.md','living_review_report.md']:
  t=open(os.path.join(a.root,fn),encoding='utf-8').read().lower() if os.path.exists(os.path.join(a.root,fn)) else ''
  for b in BAD:
   if b in t: v.append(f'forbidden:{b}')
 out={'ok':not v,'violations':v}
 os.makedirs(os.path.dirname(a.json_out),exist_ok=True);json.dump(out,open(a.json_out,'w'),indent=2)
 sys.exit(0 if not v else 1)
