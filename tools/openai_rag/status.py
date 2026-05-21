from __future__ import annotations
import datetime, json
from pathlib import Path

def build_status(out_root='outputs/openai_rag'):
    root=Path(out_root)
    return {'ok':True,'generated_at':datetime.datetime.utcnow().isoformat()+'Z','manifest_exists':(root/'artifact_manifest.json').exists(),'policy_check_exists':(root/'rag_policy_check.json').exists(),'sync_plan_exists':(root/'sync_plan.json').exists(),'query_mock_exists':(root/'query_mock_response.json').exists()}
