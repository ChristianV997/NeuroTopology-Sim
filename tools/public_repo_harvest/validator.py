import argparse, os
from .common import write_json
REQ=["source_repo_registry.json","repo_search_query_pack.json","candidate_repo_matrix.json","license_compatibility_matrix.json","reusable_pattern_registry.json","subsystem_integration_blueprint.json","adapter_gap_analysis.json","copied_artifact_attribution.json","pattern_only_registry.json","compatibility_patch_plan.json","external_systems_scorecard.json","integration_priority_queue.json","public_repo_harvest_report.md","generation_manifest.json"]
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',default='outputs/public_repo_harvest');p.add_argument('--json-out',required=True);a=p.parse_args()
 checks=[];errs=[]
 for f in REQ:
  ok=os.path.exists(os.path.join(a.root,f));checks.append({"file":f,"exists":ok});
  if not ok: errs.append(f"missing:{f}")
 write_json(a.json_out,{"status":"pass" if not errs else "fail","checks":checks,"errors":errs})
