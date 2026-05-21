from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, read_json, write_json

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();root=Path(a.root)
 audit=read_json(root/'execution_artifact_audit.json');gate=read_json(root/'empirical_claim_gate.json')
 md=f"# DS005620 Post-Execution Controls Report\n\n- dataset_id: {DATASET_ID}\n- real_execution_observed: {audit.get('real_execution_observed')}\n- empirical_claims_permitted: {gate.get('empirical_claims_permitted')}\n- next_action: {gate.get('next_action')}\n"
 (root/'post_execution_controls_report.md').write_text(md,encoding='utf-8')
 write_json(root/'generation_manifest.json',{'package':'tools.ds005620_post_execution_controls','dataset_id':DATASET_ID,'real_data_execution_attempted':False,'labels_inferred':False,'targets_fabricated':False})
if __name__=='__main__': main()
