from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',default='outputs/project_corpus_digest'); a=ap.parse_args()
    root=Path(a.root); out=Path(a.out)
    rows=read_json(root/'local_source_registry.json')
    items=[r for r in rows if r.get('claim_scope')!='ontology_quarantined']
    for i in items: i['redaction_rules']=['mask_api_keys','drop_secrets','strip_credentials']
    write_json(out/'rag_pack.json',{'safe_only':True,'items':items})
if __name__=='__main__': main()
