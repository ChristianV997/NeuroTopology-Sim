import argparse
from .common import read_json, write_json
PATTERNS=[
("pattern_rag_manifest","artifact manifest aggregation",["openai_rag","research_fabric"]),
("pattern_chunking","rag chunking strategy",["openai_rag"]),
("pattern_citation_adapter","citation adapter contract",["literature_senses","openai_rag"]),
("pattern_agent_roles","agent role registry",["local_agents"]),
("pattern_dashboard_payload","dashboard status payload model",["command_center"]),
("pattern_dag_plan","dag-like run plan/retry/lockfile",["local_ops","research_fabric"]),
("pattern_validation","forbidden phrase + schema contract checks",["project_corpus_digest","openai_rag"])]
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--licenses',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 cs=read_json(a.candidates)['candidates'];ls={i['repo']:i for i in read_json(a.licenses)['license_matrix']}
 out=[]
 for i,(pid,desc,subs) in enumerate(PATTERNS,1):
  src=[c['repo'] for c in cs[:5+i]]
  risky=any(ls[s]['compatibility_status']!='safe_to_adapt' for s in src if s in ls)
  out.append({"pattern_id":pid,"source_repos":src,"description":desc,"target_subsystems":subs,"copy_mode":"adapted_reimplementation" if risky else "direct_copy_allowed","required_attribution":True,"implementation_notes":["Use stdlib-only implementation.","Preserve offline fixture-first tests."],"compatibility_notes":["Blocked/incompatible licenses remain pattern-only."],"priority":i})
 write_json(a.out,{"reusable_patterns":out})
