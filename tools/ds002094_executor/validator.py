from __future__ import annotations
import argparse
from pathlib import Path
from . import FORBIDDEN_PHRASES, read_json, write_json
REQ=["dataset_registry.json","local_data_preflight.json","contract_requirements.json","reader_preflight.json","mne_adapter_plan.json","level_m_adapter_plan.json","level_t_adapter_plan.json","artifact_plan.json","real_execution_gate.json","manual_real_execution_command_plan.json","post_execution_controls_interface.json","readiness_report.json"]
FLAGS=["executes_real_data","downloads_data","auto_confirms_peer_review","infers_labels","fabricates_targets","auto_runs_mne_extraction","auto_runs_level_m_extraction","auto_runs_level_t_extraction","auto_runs_real_benchmark","empirical_claims_permitted","ontology_promotion_allowed"]

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default='outputs/btc_icft/ds002094_executor'); args=ap.parse_args(); root=Path(args.root)
 errors=[]
 try:
  for f in REQ:
   if not (root/f).exists(): errors.append(f'missing:{f}')
  if errors: write_json(root/'validation.json',{"valid":False,"errors":errors}); raise SystemExit(1)
  docs={f:read_json(root/f) for f in REQ if f.endswith('.json')}
  for n,d in docs.items():
   for fl in FLAGS:
    if d.get(fl) is True: errors.append(f'{n}:{fl}=true')
  gate=docs['real_execution_gate.json']
  if gate.get('ready_for_real_execution') is not False: errors.append('ready_for_real_execution must default false')
  if gate.get('can_use_execute_flag') is not False or gate.get('can_auto_execute') is not False: errors.append('execute flags enabled')
  if 'manual-only' not in str(gate.get('manual_command_template','')): errors.append('manual command lacks manual-only wrapper')
  reg=docs['dataset_registry.json']
  if reg.get('dataset_specific_executor_template') is not True: errors.append('missing dataset_specific_executor_template')
  c=docs['contract_requirements.json']
  if c.get('allowed_label_source')!='human_reviewed_metadata_only': errors.append('human reviewed label constraint missing')
  if not (root/'post_execution_controls_interface.json').exists(): errors.append('post execution controls interface missing')
  text='\n'.join((root/f).read_text(encoding='utf-8').lower() for f in REQ if (root/f).exists())
  for p in FORBIDDEN_PHRASES:
   if p in text and p not in {'ontology promotion'}: errors.append(f'forbidden phrase: {p}')
  out={"valid":not errors,"errors":errors}; write_json(root/'validation.json',out); raise SystemExit(1 if errors else 0)
 except SystemExit: raise
 except Exception as e:
  write_json(root/'validation.json',{"valid":False,"errors":[f'internal/config error: {e}']}); raise SystemExit(2)
if __name__=='__main__': main()
