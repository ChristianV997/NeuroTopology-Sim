from __future__ import annotations
import os

def get_api_key_from_env(): return os.getenv('OPENAI_API_KEY')
def mask_secret(value:str)->str: return '' if not value else value[:3]+'***'+value[-3:]
def _live_guard(mode:str, live:bool=False, confirm_upload:bool=False):
    if mode!='live' or not live: raise RuntimeError('Live mode disabled unless --mode live --live used')
    if not get_api_key_from_env(): raise RuntimeError('OPENAI_API_KEY required for live mode')
    if not confirm_upload: raise RuntimeError('Upload requires --confirm-upload')
def create_vector_store(name, metadata=None, mode='mock', live=False):
    if mode!='live': return {'id':'vs_mock','name':name,'metadata':metadata or {}}
    _live_guard(mode, live, False); return {'id':'vs_live_placeholder','name':name}
def upload_file(path,purpose='assistants',mode='mock',live=False,confirm_upload=False):
    if mode!='live': return {'id':'file_mock','path':path}
    _live_guard(mode, live, confirm_upload); return {'id':'file_live_placeholder'}
def attach_file_to_vector_store(vector_store_id,file_id,mode='mock',live=False,confirm_upload=False):
    if mode!='live': return {'ok':True}
    _live_guard(mode, live, confirm_upload); return {'ok':True}
def create_response_with_file_search(model, vector_store_id, instructions, query, include_results=True, mode='mock', live=False):
    if mode!='live': return {'id':'resp_mock','output_text':f'Mock answer for query: {query}','file_search_call':{'results':[] if include_results else None}}
    _live_guard(mode, live, False); raise RuntimeError('Live HTTP call intentionally not executed in this environment')
