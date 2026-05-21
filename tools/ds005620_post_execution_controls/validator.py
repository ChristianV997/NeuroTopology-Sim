from __future__ import annotations
import argparse
from pathlib import Path
from . import FORBIDDEN_PHRASES, read_json, write_json
REQ=['execution_artifact_audit.json','missing_execution_artifacts.json','null_controls_plan.json','nulls_required.json','ablation_plan.json','ablations_required.json','leakage_report_template.json','artifact_report_template.json','statistical_report_template.json','empirical_claim_gate.json','publication_readiness_report.md','post_execution_control_runbook.md']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();root=Path(a.root);errs=[]
 for f in REQ:
  if not (root/f).exists(): errs.append(f'missing:{f}')
 gate=read_json(root/'empirical_claim_gate.json') if (root/'empirical_claim_gate.json').exists() else {}
 audit=read_json(root/'execution_artifact_audit.json') if (root/'execution_artifact_audit.json').exists() else {}
 if gate.get('empirical_claims_permitted'):
  errs.append('empirical_claims_permitted_true_without_prereq')
 if gate.get('publication_ready') and not gate.get('empirical_claims_permitted'): errs.append('publication_ready_without_gate_pass')
 if audit.get('real_execution_observed') and audit.get('mock_execution_detected'): errs.append('mock_root_marked_real')
 txt='\n'.join([p.read_text(encoding='utf-8',errors='ignore').lower() for p in root.rglob('*') if p.is_file()])
 for bad in FORBIDDEN_PHRASES:
  if bad in txt and 'blocked language' not in txt and 'prohibited context' not in txt: errs.append(f'forbidden_phrase:{bad}')
 if 'human_peer_review_confirmed": true' in txt: errs.append('human_peer_review_default_true')
 if '--execute' in txt and 'manual' not in txt: errs.append('unsafe_execute_command_present')
 out={'valid':not errs,'errors':errs};write_json(root/'validation.json',out)
 raise SystemExit(0 if not errs else 1)
if __name__=='__main__': main()
