from __future__ import annotations
import argparse, json
from pathlib import Path

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--vault',required=True); ap.add_argument('--out',required=True); ap.add_argument('--strict',action='store_true'); a=ap.parse_args(argv)
    root=Path(a.root); base=Path(a.vault)/'07_ToL'; base.mkdir(parents=True,exist_ok=True)
    files=['ToL_Index.md','Book_Thesis.md','Doctrine_Map.md','Scientific_Observables.md','Quarantined_Claims.md','Research_Roadmap.md','Chapter_Seeds.md']
    missing=[]
    for n in files:
        (base/n).write_text(f'# {n[:-3].replace("_"," ")}\n\nnot available\n',encoding='utf-8')
    if not root.exists(): missing.append('digest root missing')
    out={'ok': not(a.strict and missing), 'missing':missing, 'written':[str(base/n) for n in files]}
    op=Path(a.out); op.parent.mkdir(parents=True,exist_ok=True); op.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2)); return 0 if out['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
