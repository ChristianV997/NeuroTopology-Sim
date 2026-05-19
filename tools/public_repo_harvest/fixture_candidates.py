import argparse
from .common import read_json, write_json

LICENSE_HINT={"graphrag":"MIT","llama_index":"MIT","langchain":"MIT","langgraph":"MIT","haystack":"Apache-2.0","txtai":"MIT","paper-qa":"MIT","airflow":"Apache-2.0","prefect":"Apache-2.0","dagster":"Apache-2.0","celery":"BSD-3-Clause","rq":"BSD-2-Clause","open-webui":"BSD-3-Clause"}

def score(name,domain,queries):
 base=60+len(domain)
 fit=sum(5 for q in queries if any(s in q.get('target_subsystems',[]) for s in ["openai_rag","literature_senses","local_ops","command_center","research_fabric"]))
 maturity=80 if any(k in name for k in ["apache","microsoft","langchain","PrefectHQ"]) else 65
 complexity=30 if "workflow" in domain else 20
 license=10 if "GPL" in name else 2
 sec=8
 total=base+fit+maturity-complexity-license-sec
 return base,maturity,70,fit,complexity,15,license,sec,total

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--registry',required=True);p.add_argument('--query-packs',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 reg=read_json(a.registry)["sources"];qp=read_json(a.query_packs)["query_packs"]
 rows=[]
 for r in reg:
  b,m,maint,fit,ic,dr,lr,sr,total=score(r['repo_full_name'],r['category'],qp)
  key=r['repo_full_name'].split('/')[-1]
  rows.append({"repo":r['repo_full_name'],"domain":r['category'],"likely_license":LICENSE_HINT.get(key,'unknown'),"usefulness_score":b,"maturity_score":m,"maintenance_signal":maint,"subsystem_fit_score":fit,"integration_complexity":ic,"dependency_risk":dr,"license_risk":lr,"security_risk":sr,"total_priority_score":total})
 write_json(a.out,{"candidates":rows})
