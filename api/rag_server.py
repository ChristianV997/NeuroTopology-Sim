from __future__ import annotations
import argparse, json, os
from pathlib import Path

try:
    from fastapi import FastAPI
except Exception:
    FastAPI = None

from tools.openai_rag.query_client import run_query
from tools.openai_rag.sync_plan import build_sync_plan
from tools.openai_rag.status import build_status as build_rag_status
from tools.command_center.status_adapter import build_status as build_command_center_status
from tools.command_center.guardrails_status import build_guardrails_status

ALLOWED_MODES={"mock","dry_run","live"}

def health(): return {"ok": True}
def status(): return build_command_center_status()
def artifact_manifest():
    p=Path('outputs/openai_rag/artifact_manifest.json')
    return json.loads(p.read_text()) if p.exists() else {"artifacts":[],"status":"not_available"}
def rag_status(): return build_rag_status()
def rag_sync_plan(mode='dry_run', live=False, confirm_upload=False):
    return build_sync_plan('outputs/openai_rag/artifact_manifest.json', mode, live, confirm_upload)
def rag_query(query:str, mode='mock', vector_store_id=None, include_sources=True):
    if mode not in ALLOWED_MODES: raise ValueError('invalid mode')
    if mode=='live' and not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY required for live mode')
    r=run_query(query, mode, vector_store_id, live=(mode=='live'))
    if not include_sources:
        r['source_artifacts']=[]; r['citations']=[]
    return r
def local_ops_status():
    p=Path('outputs/local_ops/local_ops_status.json')
    return json.loads(p.read_text()) if p.exists() else {"ok":True,"status":"not_available"}
def tol_status():
    p=Path('outputs/tol_digest/tol_digest_validation.json')
    return json.loads(p.read_text()) if p.exists() else {"ok":True,"status":"not_available"}
def guardrails_status(): return build_guardrails_status()
def action_queue():
    p=Path('outputs/local_ops/action_queue.json')
    return json.loads(p.read_text()) if p.exists() else {"ok":True,"items":[],"status":"not_available"}

# backwards compatibility
manifest=artifact_manifest
query_endpoint=rag_query
sync_plan_endpoint=rag_sync_plan

app = FastAPI(title='ScienceR-Dsim OpenAI RAG API') if FastAPI else None
if app:
    app.get('/health')(health); app.get('/status')(status); app.get('/artifacts/manifest')(artifact_manifest)
    app.get('/rag/status')(rag_status); app.post('/rag/query')(lambda payload: rag_query(payload.get('query',''), payload.get('mode','mock'), payload.get('vector_store_id'), payload.get('include_sources',True)))
    app.post('/rag/sync-plan')(lambda payload: rag_sync_plan(payload.get('mode','dry_run'),payload.get('live',False),payload.get('confirm_upload',False)))
    app.get('/local-ops/status')(local_ops_status); app.get('/tol/status')(tol_status); app.get('/guardrails/status')(guardrails_status); app.get('/actions/queue')(action_queue)

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--smoke-test',action='store_true'); a=p.parse_args(argv)
    if a.smoke_test:
        _=health(); _=status(); _=rag_status(); print('rag_server_smoke_ok'); return 0
    print('FastAPI available' if FastAPI else 'FastAPI unavailable; functional helpers loaded'); return 0
if __name__=='__main__': raise SystemExit(main())
