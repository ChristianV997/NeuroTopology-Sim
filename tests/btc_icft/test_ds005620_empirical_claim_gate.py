from __future__ import annotations
import json, subprocess
from pathlib import Path

def run(cmd): subprocess.run(cmd,check=True)

def test_claim_gate_default_blocked():
    run(['make','ds005620-post-execution-controls'])
    gate=json.loads(Path('outputs/btc_icft/ds005620_post_execution_controls/empirical_claim_gate.json').read_text())
    assert gate['empirical_claims_permitted'] is False

def test_null_and_ablation_requirements_complete():
    root=Path('outputs/btc_icft/ds005620_post_execution_controls')
    nulls=json.loads((root/'nulls_required.json').read_text())['required_control_ids']
    abls=json.loads((root/'ablations_required.json').read_text())['required_ablation_ids']
    assert len(nulls)==10
    assert len(abls)==10
