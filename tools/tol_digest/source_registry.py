from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
SUPPORTED={'.txt','.md','.tex','.json'}
OPTIONAL={'.pdf'}
KEYWORDS=['dukkha','anatta','qabs','fdress','anesthesia','soul','validated','simulator']

def _sha(p:Path)->str:
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def _role(name:str,text:str)->str:
    s=(name+' '+text).lower()
    if 'book' in s: return 'book_core'
    if any(k in s for k in ['eeg','meg','lfp','anesthesia','pci']): return 'meditation_science'
    if any(k in s for k in ['btc','icft']): return 'btc_icft_methods'
    if 'simulator' in s: return 'simulator_plan'
    if any(k in s for k in ['soul','cosmic','vacuum']): return 'speculative_archive'
    return 'unknown'

def build_registry(input_dir:str):
    root=Path(input_dir); out=[]; warnings=[]
    if not root.exists():
        return {'sources':[], 'warnings':['inputs/tol missing; empty registry']}
    i=0
    for p in sorted(root.rglob('*')):
        if not p.is_file(): continue
        ext=p.suffix.lower()
        if ext not in SUPPORTED|OPTIONAL: continue
        txt=''
        st='parsed'
        if ext=='.pdf': st='unsupported'
        else:
            try: txt=p.read_text(encoding='utf-8',errors='ignore')[:5000]
            except Exception: st='parse_error'
        kws=[k for k in KEYWORDS if k in txt.lower() or k in p.name.lower()]
        out.append({'source_id':f'src_{i:04d}','path':str(p),'title':p.stem,'extension':ext,'parse_status':st if ext!='.pdf' else 'pdf_parse_status=unsupported','size_bytes':p.stat().st_size,'sha256':_sha(p),'detected_keywords':kws,'source_role':_role(p.name,txt)})
        i+=1
    return {'sources':out,'warnings':warnings}

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--out',required=True); a=ap.parse_args(argv)
    reg=build_registry(a.input); op=Path(a.out); op.parent.mkdir(parents=True,exist_ok=True); op.write_text(json.dumps(reg,indent=2),encoding='utf-8'); print(json.dumps(reg,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
