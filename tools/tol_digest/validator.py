from __future__ import annotations
import argparse, json
from pathlib import Path
REQUIRED=['source_registry.json','claim_inventory.json','claim_tier_matrix.json','doctrine_to_construct_map.json','observables_map.json','book_insights.md','research_hypotheses.md','quarantine_report.md','next_actions.json','tol_digest_report.md']


def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--json-out',required=True); a=ap.parse_args(argv)
    r=Path(a.root); errs=[]; warns=[]
    for f in REQUIRED:
        if not (r/f).exists(): errs.append(f'missing:{f}')
    bi=(r/'book_insights.md').read_text(encoding='utf-8') if (r/'book_insights.md').exists() else ''
    rh=(r/'research_hypotheses.md').read_text(encoding='utf-8') if (r/'research_hypotheses.md').exists() else ''
    if 'proves' in bi.lower(): errs.append('proof language in book_insights')
    if 'proves' in rh.lower() and 'candidate telemetry' not in rh.lower(): errs.append('proof framing in research')
    if 'falsifiers' not in rh.lower(): errs.append('missing falsifiers')
    ok=not errs
    out={'ok':ok,'errors':errs,'warnings':warns,'no_network_required':True,'no_real_data_execution':True}
    Path(a.json_out).parent.mkdir(parents=True,exist_ok=True); Path(a.json_out).write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2))
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
