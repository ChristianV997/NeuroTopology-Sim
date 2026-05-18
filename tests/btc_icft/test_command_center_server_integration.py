from __future__ import annotations
import os
from api import rag_server
from tools.command_center.frontend_pack import main as front_main

def test_import_and_smoke_without_fastapi():
    assert hasattr(rag_server, 'health')
    assert rag_server.main(['--smoke-test']) == 0

def test_handlers_and_key_safety(monkeypatch):
    assert rag_server.health()['ok'] is True
    assert 'status' in str(rag_server.status()).lower()
    assert 'answer' in rag_server.rag_query('x', mode='mock')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    try:
        rag_server.rag_query('x', mode='live', vector_store_id='vs_1')
        assert False
    except RuntimeError:
        assert True
    all_text=str(rag_server.status())+str(rag_server.rag_status())
    assert 'OPENAI_API_KEY' not in all_text

def test_frontend_pack_and_makefile_docs(tmp_path):
    assert front_main(['--out', str(tmp_path)])==0
    assert (tmp_path/'frontend_api_contract.md').exists()
    assert 'Do not put OPENAI_API_KEY in frontend' in (tmp_path/'frontend_env_example.md').read_text()
    assert (tmp_path/'replit_integration_guide.md').exists()
    assert os.path.exists('docs/replit_command_center_integration.md')
    mk=open('Makefile').read()
    for s in ['command-center-api-smoke','command-center-openapi','command-center-mock-payloads','command-center-frontend-pack']:
        assert s in mk
