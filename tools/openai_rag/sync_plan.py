from __future__ import annotations
import argparse, datetime, json
from pathlib import Path
from .openai_client import get_api_key_from_env

def build_sync_plan(manifest_path:str, mode:str='dry_run', live:bool=False, confirm_upload:bool=False)->dict:
    mp=Path(manifest_path)
    m=json.loads(mp.read_text()) if mp.exists() else {'artifacts': []}
    arts=m.get('artifacts',[])
    up=[a['path'] for a in arts if a.get('allowed_for_rag') and a.get('exists')]
    sk=[a['path'] for a in arts if not (a.get('allowed_for_rag') and a.get('exists'))]
    warns=[]
    enabled=(mode=='live' and live and confirm_upload and bool(get_api_key_from_env()))
    if mode=='live':
      if not get_api_key_from_env(): warns.append('OPENAI_API_KEY missing')
      if not live: warns.append('Missing --live flag')
      if not confirm_upload: warns.append('Missing --confirm-upload flag')
    return {'generated_at':datetime.datetime.utcnow().isoformat()+'Z','files_to_upload':up if enabled else [],'files_to_skip':sk,'existing_vector_store_id':None,'target_vector_store_name':'ScienceR-Dsim-P29','mode':mode,'openai_calls_enabled':enabled,'upload_enabled':enabled,'warnings':warns}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--out',required=True); p.add_argument('--mode',default='dry_run'); p.add_argument('--live',action='store_true'); p.add_argument('--confirm-upload',action='store_true'); a=p.parse_args(argv)
    plan=build_sync_plan(a.manifest,a.mode,a.live,a.confirm_upload)
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    (out/'sync_plan.json').write_text(json.dumps(plan,indent=2))
    (out/'sync_report.md').write_text('# OpenAI RAG Sync Report\n\n' + '\n'.join([f"- mode: {plan['mode']}", f"- openai_calls_enabled: {plan['openai_calls_enabled']}", f"- upload_enabled: {plan['upload_enabled']}", f"- files_to_upload: {len(plan['files_to_upload'])}"]))
    return 0
if __name__=='__main__': raise SystemExit(main())
