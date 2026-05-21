from __future__ import annotations
import argparse, json
from pathlib import Path
from .guardrails import response_envelope
from .openai_client import create_response_with_file_search, get_api_key_from_env

def run_query(query:str, mode:str='mock', vector_store_id:str|None=None, live:bool=False)->dict:
    mf=Path('outputs/openai_rag/artifact_manifest.json')
    data=json.loads(mf.read_text()) if mf.exists() else {'artifacts':[]}
    src=[a['path'] for a in data.get('artifacts',[]) if a.get('allowed_for_rag') and a.get('exists')][:10]
    if mode=='live':
        if not live: raise RuntimeError('Live mode requires --live')
        if not get_api_key_from_env(): raise RuntimeError('OPENAI_API_KEY required for live mode')
        if not vector_store_id: raise RuntimeError('vector_store_id required in live mode')
        resp=create_response_with_file_search('gpt-5.5', vector_store_id, 'guarded', query, mode='live', live=True)
        return response_envelope(resp.get('output_text',''), src, claim_scope='candidate_telemetry', evidence_state='requires_controls')
    ans=f"Mock RAG summary for ScienceR-Dsim. Groups available: {sorted(set(a.get('group') for a in data.get('artifacts',[])))}"
    return response_envelope(ans, src, claim_scope='candidate_telemetry', evidence_state='not_directly_measured')

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--query',required=True); p.add_argument('--mode',default='mock'); p.add_argument('--out',required=True); p.add_argument('--vector-store-id'); p.add_argument('--live',action='store_true'); a=p.parse_args(argv)
    r=run_query(a.query,a.mode,a.vector_store_id,a.live)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(r,indent=2))
    md=out.with_suffix('.md'); md.write_text('# OpenAI RAG Query Response\n\n'+r['answer']+'\n\n## Sources\n'+'\n'.join(f'- `{s}`' for s in r['source_artifacts']))
    return 0
if __name__=='__main__': raise SystemExit(main())
