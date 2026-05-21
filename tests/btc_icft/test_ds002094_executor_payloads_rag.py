from pathlib import Path
import subprocess

def run(*args): subprocess.check_call(["python","-m",*args])

def test_payload_rag_obsidian(tmp_path: Path):
    out=tmp_path/'o'; vault=tmp_path/'v'; cc=tmp_path/'cc'
    for m in ['registry','local_data_preflight','contract_requirements','reader_preflight','mne_adapter_plan','level_m_adapter_plan','level_t_adapter_plan','artifact_plan','real_execution_gate','post_execution_controls_interface','readiness_report']:
        run(f'tools.ds002094_executor.{m}','--out',str(out))
    run('tools.ds002094_executor.command_center_payloads','--root',str(out),'--out',str(cc))
    run('tools.ds002094_executor.rag_pack','--root',str(out))
    run('tools.ds002094_executor.obsidian_sync','--root',str(out),'--vault',str(vault))
    assert (cc/'ds002094_executor_status.json').exists()
    assert (out/'rag_pack'/'rag_safe_documents.json').exists()
    assert (vault/'16_DS002094_Executor'/'Readiness_Report.md').exists()
