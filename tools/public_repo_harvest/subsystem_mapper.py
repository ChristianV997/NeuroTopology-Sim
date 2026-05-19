import argparse
from .common import read_json, write_json
FILES={"research_fabric":["tools/research_fabric/"],"literature_senses":["tools/literature_senses/"],"project_corpus_digest":["tools/project_corpus_digest/"],"openai_rag":["tools/openai_rag/"],"command_center":["tools/command_center/"],"local_ops":["tools/local_ops/"],"local_agents":["tools/local_agents/"],"toe_research":["tools/toe_research/"]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--patterns',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 pats=read_json(a.patterns)['reusable_patterns'];rows=[]
 for pr in pats:
  for s in pr['target_subsystems']:
   rows.append({"target_subsystem":s,"source_pattern":pr['pattern_id'],"implementation_mode":pr['copy_mode'],"files_to_add_or_update":FILES.get(s,[f"tools/{s}/"]),"expected_outputs":["validation report","payload json","obsidian mirror"],"tests_required":[f"tests/btc_icft/test_{s}_*.py"],"guardrails_required":["license-safe","offline-first","no-live-api-default"],"risk_level":"medium","priority":pr['priority']})
 write_json(a.out,{"integration_blueprints":rows})
