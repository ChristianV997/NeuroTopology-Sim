import argparse
from .common import write_json, now_iso

SEED = [
("microsoft/graphrag","graph_rag"),("run-llama/llama_index","rag"),("langchain-ai/langchain","rag"),("langchain-ai/langgraph","agent_runtime"),("deepset-ai/haystack","rag"),("neuml/txtai","rag"),("Future-House/paper-qa","literature_review"),
("allenai/s2orc-doc2json","scientific_scraper"),("allenai/scholarqa","literature_review"),("lukasschwab/arxiv.py","scientific_scraper"),("metapub/metapub","scientific_scraper"),("titipata/pubmed_parser","scientific_scraper"),
("PrefectHQ/prefect","workflow_orchestration"),("dagster-io/dagster","workflow_orchestration"),("apache/airflow","workflow_orchestration"),("celery/celery","local_ops"),("rq/rq","local_ops"),
("open-webui/open-webui","dashboard_frontend"),("streamlit/streamlit","dashboard_frontend"),("gradio-app/gradio","dashboard_frontend"),("fastapi/full-stack-fastapi-template","command_center"),
("neo4j/neo4j","knowledge_graph"),("networkx/networkx","knowledge_graph"),("great-expectations/great_expectations","data_validation"),
("mlflow/mlflow","scientific_ml"),("kedro-org/kedro","workflow_orchestration"),("dvcorg/dvc","scientific_ml")
]

def build():
    repos=[]
    for idx,(name,domain) in enumerate(SEED,1):
        repos.append({"id":f"repo_{idx:03d}","repo_full_name":name,"repo_url":f"https://github.com/{name}","category":domain,
        "reason_to_inspect":f"Harvest {domain} architecture patterns for offline-first subsystem integration.",
        "likely_subsystems_to_improve":["research_fabric","literature_senses","project_corpus_digest","openai_rag","command_center","local_ops","local_agents"],
        "expected_artifact_types":["interface_contracts","schema_patterns","run_manifests","guardrail_policies"],"license_status":"unknown","action":"inspect_or_pattern_only"})
    return {"generated_at":now_iso(),"sources":repos}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();write_json(a.out,build())
