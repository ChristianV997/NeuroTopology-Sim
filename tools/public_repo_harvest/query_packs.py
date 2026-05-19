import argparse
from .common import write_json
PACKS=[
("rag_graph_orchestration",["rag manifest adapter","graphrag node schema"],["openai_rag","research_fabric"]),
("scientific_literature_scrapers",["doi normalization","pubmed adapter contracts"],["literature_senses"]),
("citation_graph_and_paper_qa",["citation graph schema","paper qa evidence routing"],["literature_senses","openai_rag"]),
("local_agent_runtime",["agent role registry","safe command policy"],["local_agents"]),
("dashboard_command_center",["status payload schema","guardrail badges"],["command_center"]),
("workflow_scheduler",["dag retries","run lockfiles"],["local_ops","research_fabric"]),
("validation_and_data_contracts",["schema validator","forbidden phrase scan"],["project_corpus_digest","openai_rag"]),
("knowledge_graph_artifacts",["node edge contracts","graph export payload"],["research_fabric"]),
("publication_pipeline",["artifact publication flow","scorecards"],["project_corpus_digest"]),
("scientific_ml_reproducibility",["experiment registry","repro lock"],["research_fabric","local_ops"]) ]

def build():
 q=[]
 for i,(qid,patterns,targets) in enumerate(PACKS,1):
  q.append({"query_id":qid,"search_terms":patterns,"target_subsystems":targets,"desired_patterns":patterns,
  "blocked_license_types":["GPL","AGPL","proprietary","unknown"],"minimum_license_requirements":["SPDX present","OSI-approved for copy"],
  "security_risks":["unbounded-exec","credential-leak"],"expected_outputs":["candidate_repo_matrix","pattern_registry"],"priority":i})
 return {"query_packs":q}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();write_json(a.out,build())
