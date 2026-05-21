from __future__ import annotations
import json
from pathlib import Path
from tools.command_center.openapi_builder import main as openapi_main

def test_openapi_builder_writes_openapi_json(tmp_path):
    out = tmp_path / 'openapi.json'
    assert openapi_main(['--out', str(out)]) == 0
    assert out.exists()

def test_openapi_contract_fields(tmp_path):
    out = tmp_path / 'openapi.json'
    openapi_main(['--out', str(out)])
    spec = json.loads(out.read_text())
    required=["/health","/status","/artifacts/manifest","/rag/status","/rag/query","/rag/sync-plan","/local-ops/status","/tol/status","/guardrails/status","/actions/queue"]
    for p in required: assert p in spec['paths']
    q=spec['paths']['/rag/query']['post']['requestBody']['content']['application/json']['schema']
    assert 'query' in q['required'] and 'mode' in q['required']
    schema=spec['paths']['/rag/status']['get']['responses']['200']['content']['application/json']['schema']['properties']
    assert 'claim_scope' in schema and 'evidence_state' in schema and 'source_artifacts' in schema
    assert 'OPENAI_API_KEY' not in json.dumps(spec)
