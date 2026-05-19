from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json
from .claim_risk_analyzer import FORBIDDEN
REQ=['local_source_registry.json','local_file_inventory.json','archive_inventory.json','generation_manifest.json','manuscript_digest_matrix.json','simulator_artifact_matrix.json','os_runtime_extraction_matrix.json','book_system_extraction_matrix.json','speculative_quarantine_matrix.json','publication_lane_registry.json','reusable_asset_registry.json','claim_risk_report.md','system_integration_digest.md']

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--json-out',required=True); a=ap.parse_args(); root=Path(a.root)
    errs=[]
    for f in REQ:
        if not (root/f).exists(): errs.append(f'missing {f}')
    for jf in ['local_source_registry.json','local_file_inventory.json','archive_inventory.json']:
        p=root/jf
        if p.exists():
            for row in read_json(p)[:50]:
                for k in ['id','name','path','artifact_type','category','claim_scope','evidence_state','allowed_use','prohibited_claims','safety_notes']:
                    if k not in row: errs.append(f'{jf} missing key {k}')
    for md in ['system_integration_digest.md']:
        p=root/md
        if p.exists():
            t=p.read_text(encoding='utf-8').lower()
            for bad in FORBIDDEN:
                if bad in t: errs.append(f'forbidden phrase in {md}: {bad}')
    cdir=Path('outputs/command_center/mock_payloads')
    for fn in ['project_corpus_status.json','project_corpus_claim_risks.json']:
        p=cdir/fn
        if p.exists():
            d=read_json(p)
            for k in ["ontology_promotion_allowed","real_data_auto_execution_allowed","api_key_exposure_allowed","claim_proof_allowed","publish_clinical_claim_allowed"]:
                if d.get(k) is not False: errs.append(f'{fn} flag {k} must be false')
    write_json(Path(a.json_out),{'valid':not errs,'errors':errs})
    if errs: raise SystemExit(1)
if __name__=='__main__': main()
