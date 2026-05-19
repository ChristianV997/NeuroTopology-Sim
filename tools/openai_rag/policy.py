from __future__ import annotations
import argparse, json
from pathlib import Path

FORBID=(".env","data/","openai_api_key","sk-")

def validate_policy(policy_path:str, sources_path:str='configs/openai_rag/artifact_sources.json')->dict:
    p=json.loads(Path(policy_path).read_text()); s=json.loads(Path(sources_path).read_text())
    issues=[]
    if not p.get('requires_server_side_key',False): issues.append('requires_server_side_key_false')
    if p.get('allow_openai_calls_by_default',True): issues.append('openai_calls_default_enabled')
    if p.get('allow_uploads_by_default',True): issues.append('uploads_default_enabled')
    if any(not v for v in p.get('guardrails',{}).values()): issues.append('guardrail_false_present')
    src_txt=json.dumps({'groups': s.get('groups', [])}).lower(); pol_txt=json.dumps(p).lower()
    for f in FORBID:
        if f=='data/':
            continue
        if f in src_txt or f in pol_txt:
            issues.append(f'forbidden_pattern:{f}')
    return {"ok": not issues, "issues": issues, "policy_version": p.get('version')}

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--policy',required=True); ap.add_argument('--json-out',required=True); a=ap.parse_args(argv)
    r=validate_policy(a.policy)
    out=Path(a.json_out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(r,indent=2))
    print(json.dumps(r,indent=2)); return 0 if r['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
