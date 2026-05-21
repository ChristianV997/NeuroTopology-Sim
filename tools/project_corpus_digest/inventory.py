from __future__ import annotations
import argparse, hashlib, os
from pathlib import Path
from . import write_json
from .archive_scanner import scan_archive
from .file_classifier import classify
from .ontology_quarantine import apply_quarantine

IGNORE={'.git','__pycache__','node_modules'}
WHITELIST_LARGE={'.pdf','.zip','.tex','.md','.json','.yaml','.yml','.py','.txt'}

def iter_files(roots:list[Path]):
    for root in roots:
        for p in root.rglob('*'):
            if any(part in IGNORE for part in p.parts): continue
            if p.is_file():
                if p.stat().st_size>20_000_000 and p.suffix.lower() not in WHITELIST_LARGE: continue
                yield p

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--roots', nargs='+', required=True); ap.add_argument('--out', required=True)
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    registry=[]; files=[]; archives=[]
    for p in iter_files([Path(r) for r in args.roots]):
        art,cat,scope=classify(p)
        row={"id":hashlib.sha1(str(p).encode()).hexdigest()[:12],"name":p.name,"path":str(p),"artifact_type":art,"category":cat,"claim_scope":scope,
             "evidence_state":"artifact_derived","allowed_use":"internal analysis and safe drafting","prohibited_claims":["no proof language","no clinical claims"],"safety_notes":["local-only"],"publication_lane":None,"reusable_asset_candidates":[]}
        row=apply_quarantine(row)
        registry.append(row); files.append({**row,"size_bytes":p.stat().st_size})
        if art=='zip' or p.suffix.lower()=='.zip': archives.append({**row,**scan_archive(p,extract=False)})
    write_json(out/'local_source_registry.json', registry)
    write_json(out/'local_file_inventory.json', files)
    write_json(out/'archive_inventory.json', archives)
    write_json(out/'generation_manifest.json', {"roots":args.roots,"counts":{"registry":len(registry),"files":len(files),"archives":len(archives)}})

if __name__=='__main__': main()
