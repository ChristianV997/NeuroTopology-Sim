from __future__ import annotations
import json
from pathlib import Path
from tools.openai_rag.artifact_manifest import build_manifest
from tools.openai_rag.policy import validate_policy

def test_manifest_handles_missing_outputs():
    recs=build_manifest('configs/openai_rag/artifact_sources.json')
    assert isinstance(recs,list)

def test_manifest_includes_tol_and_excludes_patterns():
    recs=build_manifest('configs/openai_rag/artifact_sources.json')
    paths=[r['path'] for r in recs]
    assert 'outputs/tol_digest/book_spine.md' in paths
    assert all('.env' not in p for p in paths)
    assert all(not p.startswith('data/') for p in paths)

def test_quarantine_marked_context():
    rec=next(r for r in build_manifest('configs/openai_rag/artifact_sources.json') if r['path'].endswith('quarantine_report.md'))
    assert rec['claim_scope']=='quarantine_context'

def test_policy_passes_default_config():
    result=validate_policy('configs/openai_rag/rag_policy.json')
    assert result['ok']

def test_policy_fails_invalid_values(tmp_path):
    p=json.loads(Path('configs/openai_rag/rag_policy.json').read_text())
    p['guardrails']['no_client_side_key']=False; p['allow_uploads_by_default']=True
    fp=tmp_path/'p.json'; fp.write_text(json.dumps(p))
    r=validate_policy(str(fp))
    assert not r['ok']

def test_policy_fails_api_key_literal(tmp_path):
    p=json.loads(Path('configs/openai_rag/rag_policy.json').read_text()); p['note']='sk-test-123'
    fp=tmp_path/'p.json'; fp.write_text(json.dumps(p))
    r=validate_policy(str(fp))
    assert not r['ok']
