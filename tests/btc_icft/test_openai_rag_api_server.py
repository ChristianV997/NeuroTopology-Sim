from __future__ import annotations
import importlib
import pytest
from api import rag_server

def test_imports_without_fastapi_requirement():
    assert hasattr(rag_server,'health')

def test_smoke_passes():
    assert rag_server.main(['--smoke-test'])==0

def test_health_ok():
    assert rag_server.health()['ok'] is True

def test_no_api_key_exposure():
    assert 'OPENAI_API_KEY' not in str(rag_server.rag_status())

def test_mode_validation():
    with pytest.raises(ValueError):
        rag_server.query_endpoint('x', mode='bad')

def test_query_endpoint_mock_mode():
    r=rag_server.query_endpoint('x', mode='mock')
    assert 'answer' in r
