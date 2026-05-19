import argparse, os
from .common import read_json, write_json, now_iso
GAPS=["OpenAlex live adapter","Semantic Scholar live adapter","PubMed live adapter","arXiv live adapter","local project archive adapter","GitHub public repo metadata adapter","RAG manifest aggregator","dashboard payload indexer","workflow DAG planner","GraphRAG schema adapter","citation graph builder","license scanner","source attribution generator"]
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args();os.makedirs(a.root,exist_ok=True)
 gap=[{"gap_id":f"gap_{i:03d}","current_state":"partial_or_missing","desired_state":g,"source_repo_pattern":"public pattern registry","implementation_priority":"P1" if i<6 else "P2","blocked_by":[],"safe_fixture_first":True,"expected_tests":["fixture generation","validator contract"]} for i,g in enumerate(GAPS,1)]
 write_json(os.path.join(a.root,'adapter_gap_analysis.json'),{"adapter_gap_analysis":gap})
 write_json(os.path.join(a.root,'copied_artifact_attribution.json'),{"direct_code_copies":[],"status":"no_direct_code_copied","policy":"all external repositories used as pattern sources unless license-compatible snippets are explicitly attributed"})
 write_json(os.path.join(a.root,'pattern_only_registry.json'),{"pattern_only_registry":[{"id":"pattern_only_default","reason":"license unclear or incompatible","action":"reimplement_from_scratch"}]})
 with open(os.path.join(a.root,'public_repo_harvest_report.md'),'w',encoding='utf-8') as f:f.write('# Public Repo Harvest Report\nThis run generated a license-governed, offline-first integration blueprint and artifact pack.\n')
 write_json(os.path.join(a.root,'generation_manifest.json'),{"generated_at":now_iso(),"module":"tools.public_repo_harvest","artifacts_root":a.root})
