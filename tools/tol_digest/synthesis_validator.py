from __future__ import annotations
import argparse, json
from pathlib import Path

REQ=['book_spine.md','chapter_seed_bank.md','research_roadmap.md','tol_to_ds005620_observable_bridge.md','public_language_rewrite_guide.md']

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--json-out',required=True); a=ap.parse_args(argv)
    r=Path(a.root); errs=[]
    for f in REQ:
        if not (r/f).exists(): errs.append(f'missing:{f}')
    b=(r/'book_spine.md').read_text(encoding='utf-8') if (r/'book_spine.md').exists() else ''
    rr=(r/'research_roadmap.md').read_text(encoding='utf-8') if (r/'research_roadmap.md').exists() else ''
    ob=(r/'tol_to_ds005620_observable_bridge.md').read_text(encoding='utf-8') if (r/'tol_to_ds005620_observable_bridge.md').exists() else ''
    pg=(r/'public_language_rewrite_guide.md').read_text(encoding='utf-8') if (r/'public_language_rewrite_guide.md').exists() else ''
    for t in ['core thesis','stability vs freedom','what the book does not claim']:
        if t not in b.lower(): errs.append(f'book_missing:{t}')
    for bad in ['soul is real','theory validated','qabs proves','trauma deletion','instant arhat']:
        if bad in b.lower(): errs.append(f'book_unsafe:{bad}')
    for t in ['falsifiers','null controls','ablations','leakage/artifact reports','candidate topology telemetry']:
        if t not in rr.lower(): errs.append(f'roadmap_missing:{t}')
    if 'q proves consciousness' in rr.lower() or 'qabs proves consciousness' in rr.lower() or 'fdress proves consciousness' in rr.lower(): errs.append('roadmap_proof_framing')
    if 'not directly measured' not in ob.lower(): errs.append('bridge_missing_not_directly_measured')
    for t in ['high exit cost','recovery latency','dwell time','transition resistance','fragmentation','qabs','fdress']:
        if t not in ob.lower(): errs.append(f'bridge_missing:{t}')
    for t in ['unsafe: “soul is real”','clinical','quarantined']:
        if t.lower() not in pg.lower(): errs.append(f'guide_missing:{t}')
    out={'ok':not errs,'errors':errs}
    p=Path(a.json_out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2))
    return 0 if out['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
