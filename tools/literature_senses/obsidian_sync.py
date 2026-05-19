import argparse, os, json
from pathlib import Path
M={'Source_Registry.md':'source_registry.json','Query_Pack_Registry.md':'query_pack_registry.json','Retrieval_Plan.md':'retrieval_plan.json','Scored_Papers.md':'scored_papers.json','Evidence_Tier_Matrix.md':'evidence_tier_matrix.json','Construct_Mapping_Matrix.md':'construct_mapping_matrix.json','Falsifier_Watchlist.md':'falsifier_watchlist.json','Theory_Integration_Digest.md':'theory_integration_digest.md','Living_Review_Report.md':'living_review_report.md'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--vault',required=True);p.add_argument('--out',required=True);p.add_argument('--strict',action='store_true');a=p.parse_args();base=Path(a.vault)/'09_Literature_Senses';base.mkdir(parents=True,exist_ok=True)
 for md,src in M.items():
  sp=Path(a.root)/src;txt=sp.read_text(encoding='utf-8') if sp.exists() else 'not available';(base/md).write_text(f'# {md}\n\n'+txt[:4000],encoding='utf-8')
 Path(a.out).parent.mkdir(parents=True,exist_ok=True);json.dump({'ok':True},open(a.out,'w'),indent=2)
