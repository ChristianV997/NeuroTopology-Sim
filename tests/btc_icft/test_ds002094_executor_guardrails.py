from pathlib import Path
import subprocess, json

def run(*args): subprocess.check_call(["python","-m",*args])

def prep(out: Path):
    for m in ['registry','local_data_preflight','contract_requirements','reader_preflight','mne_adapter_plan','level_m_adapter_plan','level_t_adapter_plan','artifact_plan','real_execution_gate','post_execution_controls_interface','readiness_report']:
        run(f'tools.ds002094_executor.{m}','--out',str(out))

def test_validator_passes_and_fails(tmp_path: Path):
    out=tmp_path/'o'; prep(out); run('tools.ds002094_executor.validator','--root',str(out))
    p=out/'level_m_adapter_plan.json'; d=json.loads(p.read_text()); d['empirical_claims_permitted']=True; p.write_text(json.dumps(d))
    rc=subprocess.run(["python","-m","tools.ds002094_executor.validator","--root",str(out)]).returncode
    assert rc==1
