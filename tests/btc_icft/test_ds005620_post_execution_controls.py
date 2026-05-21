from __future__ import annotations
import json, subprocess
from pathlib import Path

ROOT=Path('outputs/btc_icft/ds005620_post_execution_controls')

def run(cmd):
    subprocess.run(cmd,check=True)

def test_cycle_generates_outputs_and_templates():
    run(['make','ds005620-post-execution-controls-cycle'])
    required=['execution_artifact_audit.json','missing_execution_artifacts.json','null_controls_plan.json','nulls_required.json','ablation_plan.json','ablations_required.json','leakage_report_template.json','artifact_report_template.json','statistical_report_template.json','empirical_claim_gate.json','publication_readiness_report.md','post_execution_control_runbook.md','post_execution_controls_report.md','validation.json','generation_manifest.json']
    for f in required: assert (ROOT/f).exists(), f
    audit=json.loads((ROOT/'execution_artifact_audit.json').read_text())
    assert audit['real_execution_observed'] is False

def test_mock_root_not_real_empirical_evidence(tmp_path: Path):
    mock=tmp_path/'ds005620_real_benchmark_execution_mock';mock.mkdir();(mock/'ds005620_real_benchmark_execution.json').write_text('{}')
    out=tmp_path/'out'
    run(['python','-m','tools.ds005620_post_execution_controls.execution_artifact_audit','--execution-root',str(mock),'--out',str(out)])
    audit=json.loads((out/'execution_artifact_audit.json').read_text())
    assert audit['mock_execution_detected'] is True
    assert audit['real_execution_observed'] is False
