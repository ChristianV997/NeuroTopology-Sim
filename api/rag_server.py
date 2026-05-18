from __future__ import annotations
import argparse, json
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
except Exception:
    FastAPI = None
    HTTPException = Exception

from tools.openai_rag.query_client import run_query
from tools.openai_rag.sync_plan import build_sync_plan
from tools.openai_rag.status import build_status

ALLOWED_MODES={"mock","dry_run","live"}

def health(): return {"ok": True}
def manifest():
    p=Path('outputs/openai_rag/artifact_manifest.json')
    return json.loads(p.read_text()) if p.exists() else {"artifacts":[]}
def rag_status(): return build_status()
def sync_plan_endpoint(mode='dry_run', live=False, confirm_upload=False):
    return build_sync_plan('outputs/openai_rag/artifact_manifest.json', mode, live, confirm_upload)
def query_endpoint(query:str, mode='mock', vector_store_id=None, include_sources=True):
    if mode not in ALLOWED_MODES: raise ValueError('invalid mode')
    r=run_query(query, mode, vector_store_id, live=(mode=='live'))
    if not include_sources: r['source_artifacts']=[]; r['citations']=[]
    return r

app = FastAPI(title='ScienceR-Dsim OpenAI RAG API') if FastAPI else None
if app:
    @app.get('/health')
    def _h(): return health()
    @app.get('/artifacts/manifest')
    def _m(): return manifest()
    @app.get('/rag/status')
    def _s(): return rag_status()
    @app.post('/rag/sync-plan')
    def _sp(payload:dict): return sync_plan_endpoint(payload.get('mode','dry_run'),payload.get('live',False),payload.get('confirm_upload',False))
    @app.post('/chat')
    @app.post('/query')
    def _q(payload:dict): return query_endpoint(payload.get('query',''), payload.get('mode','mock'), payload.get('vector_store_id'), payload.get('include_sources',True))

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--smoke-test',action='store_true'); a=p.parse_args(argv)
    if a.smoke_test:
        _=health(); _=rag_status(); print('rag_server_smoke_ok'); return 0
    print('FastAPI available' if FastAPI else 'FastAPI unavailable; functional helpers loaded'); return 0
if __name__=='__main__': raise SystemExit(main())
