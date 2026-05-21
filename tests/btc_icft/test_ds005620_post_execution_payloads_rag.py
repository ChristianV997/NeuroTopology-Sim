from __future__ import annotations
import json, subprocess
from pathlib import Path

def run(cmd): subprocess.run(cmd,check=True)

def test_payloads_rag_obsidian_and_make_targets():
    run(['make','ds005620-post-execution-controls-cycle'])
    payload=Path('outputs/command_center/mock_payloads/ds005620_empirical_claim_gate.json')
    data=json.loads(payload.read_text())
    assert data['empirical_claims_permitted'] is False
    assert Path('outputs/btc_icft/ds005620_post_execution_controls/rag_pack/rag_pack_report.md').exists()
    assert Path('obsidian/15_DS005620_Post_Execution_Controls/Empirical_Claim_Gate.md').exists()
    mk=Path('Makefile').read_text()
    assert 'ds005620-post-execution-controls-cycle' in mk
