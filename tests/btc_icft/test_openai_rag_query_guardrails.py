from __future__ import annotations
import pytest
from tools.openai_rag.query_client import run_query
from tools.openai_rag.guardrails import apply_guardrails
from tools.openai_rag.sync_plan import build_sync_plan

def test_mock_query_works_without_openai():
    r=run_query('What is ToL?', mode='mock')
    assert 'answer' in r

def test_mock_query_returns_sources_and_fields():
    r=run_query('x', mode='mock')
    assert 'source_artifacts' in r and 'claim_scope' in r and 'limitations' in r

def test_guardrail_blocks_qabs():
    t,h=apply_guardrails('Qabs proves liberation')
    assert h and 'candidate telemetry' in t.lower()

def test_guardrail_blocks_soul_real():
    t,h=apply_guardrails('soul is real')
    assert h

def test_live_query_fails_without_key():
    with pytest.raises(RuntimeError):
        run_query('x', mode='live', vector_store_id='vs_1', live=True)

def test_live_sync_fails_without_confirm_upload():
    r=build_sync_plan('outputs/openai_rag/artifact_manifest.json', mode='live', live=True, confirm_upload=False)
    assert r['upload_enabled'] is False
