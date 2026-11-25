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


def direct_copy_is_reviewed(license_record):
 """Return false: this offline pipeline has no authenticated review source."""
 return False


def pattern_copy_mode(source_repos, license_records):
 """Keep every caller-supplied source at pattern-only pending authenticated review."""
 return "pattern_only_requires_review"


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--licenses',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 cs=read_json(a.candidates)['candidates'];ls={i['repo']:i for i in read_json(a.licenses)['license_matrix']}
 out=[]
 for i,(pid,desc,subs) in enumerate(PATTERNS,1):
  src=[c['repo'] for c in cs[:5+i]]
  copy_mode=pattern_copy_mode(src,ls)
  out.append({"pattern_id":pid,"source_repos":src,"description":desc,"target_subsystems":subs,"copy_mode":copy_mode,"required_attribution":True,"implementation_notes":["Use stdlib-only implementation.","Preserve offline fixture-first tests."],"compatibility_notes":["Blocked/incompatible licenses remain pattern-only."],"priority":i})
 write_json(a.out,{"reusable_patterns":out})
