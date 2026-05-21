from pathlib import Path
import subprocess, json

def run(*args):
    subprocess.check_call(["python","-m",*args])

def test_cycle_writes_required_outputs(tmp_path: Path):
    out=tmp_path/'o'
    cmds=[['tools.ds002094_executor.registry','--out',str(out)],['tools.ds002094_executor.local_data_preflight','--out',str(out)],['tools.ds002094_executor.contract_requirements','--out',str(out)],['tools.ds002094_executor.reader_preflight','--out',str(out)],['tools.ds002094_executor.mne_adapter_plan','--out',str(out)],['tools.ds002094_executor.level_m_adapter_plan','--out',str(out)],['tools.ds002094_executor.level_t_adapter_plan','--out',str(out)],['tools.ds002094_executor.artifact_plan','--out',str(out)],['tools.ds002094_executor.real_execution_gate','--out',str(out)],['tools.ds002094_executor.post_execution_controls_interface','--out',str(out)],['tools.ds002094_executor.readiness_report','--out',str(out)]]
    for c in cmds: run(*c)
    assert (out/'readiness_report.json').exists()
    gate=json.loads((out/'real_execution_gate.json').read_text())
    assert gate['ready_for_real_execution'] is False
