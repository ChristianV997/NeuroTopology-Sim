import argparse
from .common import read_json, write_json
from .license_scanner import ALLOWED
PATTERNS=[
("pattern_rag_manifest","artifact manifest aggregation",["openai_rag","research_fabric"]),
("pattern_chunking","rag chunking strategy",["openai_rag"]),
("pattern_citation_adapter","citation adapter contract",["literature_senses","openai_rag"]),
("pattern_agent_roles","agent role registry",["local_agents"]),
("pattern_dashboard_payload","dashboard status payload model",["command_center"]),
("pattern_dag_plan","dag-like run plan/retry/lockfile",["local_ops","research_fabric"]),
("pattern_validation","forbidden phrase + schema contract checks",["project_corpus_digest","openai_rag"])]


def direct_copy_is_reviewed(license_record):
 detected = license_record.get("detected_license") if isinstance(license_record,dict) else None
 return (
  isinstance(license_record,dict)
  and detected in ALLOWED
  and license_record.get("license_spdx")==detected
  and license_record.get("detected_licenses")==[detected]
  and license_record.get("license_status")=="compatible"
  and license_record.get("compatibility_status")=="safe_to_adapt"
  and license_record.get("review_status")=="human_reviewed_compatible"
  and license_record.get("can_copy_code") is True
  and license_record.get("manual_review_required") is False
  and license_record.get("conflicting") is False
 )


def pattern_copy_mode(source_repos, license_records):
 """Require a reviewed license record for every repo before direct-copy mode."""
 if any(not direct_copy_is_reviewed(license_records.get(repo)) for repo in source_repos):
  return "adapted_reimplementation"
 return "direct_copy_allowed"


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--licenses',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 cs=read_json(a.candidates)['candidates'];ls={i['repo']:i for i in read_json(a.licenses)['license_matrix']}
 out=[]
 for i,(pid,desc,subs) in enumerate(PATTERNS,1):
  src=[c['repo'] for c in cs[:5+i]]
  copy_mode=pattern_copy_mode(src,ls)
  out.append({"pattern_id":pid,"source_repos":src,"description":desc,"target_subsystems":subs,"copy_mode":copy_mode,"required_attribution":True,"implementation_notes":["Use stdlib-only implementation.","Preserve offline fixture-first tests."],"compatibility_notes":["Blocked/incompatible licenses remain pattern-only."],"priority":i})
 write_json(a.out,{"reusable_patterns":out})
