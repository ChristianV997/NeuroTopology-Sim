from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json

FLAGS={"ontology_promotion_allowed":False,"real_data_auto_execution_allowed":False,"api_key_exposure_allowed":False,"claim_proof_allowed":False,"publish_clinical_claim_allowed":False}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(a.root); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    rows=read_json(root/'local_source_registry.json'); risks=read_json(root/'claim_risk_matrix.json') if (root/'claim_risk_matrix.json').exists() else []
    write_json(out/'project_corpus_status.json',{'total_sources':len(rows),**FLAGS})
    write_json(out/'project_corpus_claim_risks.json',{'risks':risks,**FLAGS})
    write_json(out/'project_corpus_simulator_assets.json',{'items':[r for r in rows if r['category']=='simulator_assets'],**FLAGS})
    write_json(out/'project_corpus_publication_lanes.json',{'items':read_json(root/'publication_lane_registry.json') if (root/'publication_lane_registry.json').exists() else [],**FLAGS})
    write_json(out/'project_corpus_reusable_assets.json',{'items':read_json(root/'reusable_asset_registry.json') if (root/'reusable_asset_registry.json').exists() else [],**FLAGS})
    write_json(out/'project_corpus_next_actions.json',{'actions':['review quarantined ontology files','review risky phrase rewrites'],**FLAGS})

if __name__=='__main__': main()
