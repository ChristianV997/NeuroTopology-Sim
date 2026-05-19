from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json
from .claim_risk_analyzer import analyze_text
from .publication_lane_mapper import lane_for
from .reusable_asset_extractor import extract_candidates

def _write_md(path:Path, title:str, lines:list[str]):
    path.write_text('# '+title+'\n\n'+'\n'.join(lines), encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',required=True); args=ap.parse_args()
    root=Path(args.root); out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows=read_json(root/'local_source_registry.json')
    for r in rows:
        r['publication_lane']=lane_for(r); r['reusable_asset_candidates']=extract_candidates(r)
    def filt(cat): return [r for r in rows if r['category']==cat]
    write_json(out/'manuscript_digest_matrix.json',filt('manuscripts'))
    write_json(out/'simulator_artifact_matrix.json',filt('simulator_assets'))
    write_json(out/'os_runtime_extraction_matrix.json',filt('os_runtime'))
    write_json(out/'book_system_extraction_matrix.json',filt('book_system'))
    write_json(out/'speculative_quarantine_matrix.json',filt('speculative_ontology'))
    write_json(out/'publication_lane_registry.json',[{'id':r['id'],'path':r['path'],'publication_lane':r['publication_lane']} for r in rows])
    write_json(out/'reusable_asset_registry.json',[{'id':r['id'],'path':r['path'],'reusable_asset_candidates':r['reusable_asset_candidates']} for r in rows if r['reusable_asset_candidates']])
    risks=[]
    for r in rows[:500]:
        p=Path(r['path'])
        if p.suffix.lower() in {'.md','.txt','.py','.tex','.json','.yaml','.yml'} and p.exists():
            for rr in analyze_text(p.read_text(encoding='utf-8',errors='ignore')):
                risks.append({**r,**rr})
    write_json(out/'claim_risk_matrix.json', risks)
    _write_md(out/'claim_risk_report.md','Claim Risk Report',[f"- {x['path']}: unsafe phrase '{x['risky_phrase']}'" for x in risks] or ['- No risky phrases found.'])
    _write_md(out/'system_integration_digest.md','System Integration Digest',[f"- Total local sources: {len(rows)}", '- Ontology defaults to quarantined claim scope.', '- No real-data auto execution performed.'])

if __name__=='__main__': main()
