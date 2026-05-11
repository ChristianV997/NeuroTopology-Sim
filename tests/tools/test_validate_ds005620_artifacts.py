import csv, json, subprocess, sys
from pathlib import Path
import pytest
import importlib.util
import sys
_spec=importlib.util.spec_from_file_location("validate_ds005620_artifacts","tools/validate_ds005620_artifacts.py")
_mod=importlib.util.module_from_spec(_spec); sys.modules[_spec.name]=_mod; _spec.loader.exec_module(_mod)
validate_all=_mod.validate_all; ValidationError=_mod.ValidationError

def mk(root:Path):
    d=root/'mt_real'; d.mkdir(parents=True)
    with (d/'features_joined.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['row_id','subject_id','session_id','run_id','window_id','task_label','spectral_power_proxy','entropy_proxy','lzc_proxy','artifact_score','q_net','q_abs','f_dress','defect_density','topology_quality']); w.writerow(['r','s','se','ru','w','awake_vs_sedated',1,1,1,0.1,0.1,0.2,0.3,0.01,0.8])
    (d/'metrics_mt_real.json').write_text(json.dumps({'metrics_m':{},'metrics_mt':{},'delta_auc':0.1,'delta_ece':0,'promoted':True,'promotion_reason':'x'}))
    (d/'nulls_real.json').write_text(json.dumps({'nulls_passed':True,'real_nulls_performed':False}))
    (d/'ablations_real.json').write_text(json.dumps({'M_only':{},'M_plus_all_T':{}}))
    (d/'leakage_report.json').write_text(json.dumps({'leakage_detected':False}))
    (d/'artifact_report.json').write_text(json.dumps({'artifact_dominance':False}))
    (d/'omega_event.json').write_text(json.dumps({'safe_claim':'x'}))
    (d/'report.md').write_text('residual predictive value\nlevel t topology telemetry\nspecified controls')

def test_validator_cases(tmp_path):
    root=tmp_path/'ds005620'; mk(root); assert validate_all(root,['mt_real'])==['mt_real']
    (root/'mt_real'/'omega_event.json').unlink()
    with pytest.raises(ValidationError): validate_all(root,['mt_real'])

def test_json_cli_and_banned(tmp_path):
    root=tmp_path/'ds005620'; mk(root)
    cp=subprocess.run([sys.executable,'tools/validate_ds005620_artifacts.py','--root',str(root),'--stage','mt_real','--json'],capture_output=True,text=True)
    assert cp.returncode==0 and json.loads(cp.stdout)['ok'] is True
    (root/'mt_real'/'report.md').write_text('proves consciousness')
    cp2=subprocess.run([sys.executable,'tools/validate_ds005620_artifacts.py','--root',str(root),'--stage','mt_real','--json'],capture_output=True,text=True)
    assert cp2.returncode!=0 and json.loads(cp2.stdout)['ok'] is False

def test_unknown_stage(tmp_path):
    root=tmp_path/'ds005620'; mk(root)
    with pytest.raises(ValidationError): validate_all(root,['bad_stage'])
