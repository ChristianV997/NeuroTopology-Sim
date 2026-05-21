from __future__ import annotations
import json
from tools.command_center.mock_payloads import main as mock_main

def test_mock_payloads_generate(tmp_path):
    assert mock_main(['--out', str(tmp_path)]) == 0
    for name in ['health.json','status.json','artifact_manifest.json','rag_status.json','rag_query_response.json','local_ops_status.json','tol_status.json','guardrails_status.json','action_queue.json']:
        assert (tmp_path/name).exists()
    rag=json.loads((tmp_path/'rag_query_response.json').read_text())
    assert 'guardrails_applied' in rag and 'limitations' in rag
    g=json.loads((tmp_path/'guardrails_status.json').read_text())
    assert g['ontology_promotion_allowed'] is False
    assert json.loads((tmp_path/'local_ops_status.json').read_text())['status']=='not_available'
    assert json.loads((tmp_path/'tol_status.json').read_text())['status']=='not_available'
    assert json.loads((tmp_path/'action_queue.json').read_text())['status']=='not_available'
