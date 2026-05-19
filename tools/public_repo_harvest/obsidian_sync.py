import argparse, os
from .common import read_json, write_json
MAP=[("source_repo_registry.json","Source_Repo_Registry.md","sources"),("candidate_repo_matrix.json","Candidate_Repo_Matrix.md","candidates"),("license_compatibility_matrix.json","License_Compatibility_Matrix.md","license_matrix"),("reusable_pattern_registry.json","Reusable_Pattern_Registry.md","reusable_patterns"),("subsystem_integration_blueprint.json","Subsystem_Integration_Blueprint.md","integration_blueprints"),("adapter_gap_analysis.json","Adapter_Gap_Analysis.md","adapter_gap_analysis"),("compatibility_patch_plan.json","Compatibility_Patch_Plan.md","compatibility_patches"),("external_systems_scorecard.json","External_Systems_Scorecard.md","external_systems_scorecard"),("integration_priority_queue.json","Integration_Priority_Queue.md","integration_priority_queue")]
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--vault',default='obsidian');p.add_argument('--out',required=True);a=p.parse_args();dest=os.path.join(a.vault,'12_Public_Repo_Harvest');os.makedirs(dest,exist_ok=True)
 created=[]
 for js,md,key in MAP:
  data=read_json(os.path.join(a.root,js));lines=[f"# {md[:-3]}",""]
  for row in data.get(key,[]): lines.append(f"- `{row.get('id',row.get('repo',row.get('pattern_id','item')) )}`: {row}")
  with open(os.path.join(dest,md),'w',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n');created.append(md)
 write_json(a.out,{"status":"ok","created":created,"vault_path":dest})
