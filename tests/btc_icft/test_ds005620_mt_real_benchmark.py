import csv, json, subprocess, sys
from pathlib import Path
import pytest
from sciencer_d.btc_icft.evaluation import ds005620_residual as mod
from sciencer_d.btc_icft.level_m.ds005620_baseline import build_mock_ds005620_level_m_rows

def _write_csv(path, rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); [w.writerow(r) for r in rows]

def test_loaders_and_missing(tmp_path):
    m=build_mock_ds005620_level_m_rows()[0]
    mfile=tmp_path/'features_m.csv'; tfile=tmp_path/'features_t.csv'
    _write_csv(mfile,[m.__dict__]); t=mod.build_mock_ds005620_level_t_rows()[0]; _write_csv(tfile,[t.__dict__])
    assert mod.load_level_m_real_features(str(mfile))
    assert mod.load_level_t_real_features(str(tfile))
    with pytest.raises(FileNotFoundError): mod.load_level_m_real_features(str(tmp_path/'x.csv'))
    with pytest.raises(FileNotFoundError): mod.load_level_t_real_features(str(tmp_path/'y.csv'))

def test_missing_columns(tmp_path):
    p=tmp_path/'m.csv'; p.write_text('row_id\n1\n')
    with pytest.raises(ValueError): mod.load_level_m_real_features(str(p))
    p2=tmp_path/'t.csv'; p2.write_text('row_id\n1\n')
    with pytest.raises(ValueError): mod.load_level_t_real_features(str(p2))

def test_join_and_failures():
    m=build_mock_ds005620_level_m_rows(); t=mod.build_mock_ds005620_level_t_rows(); j=mod.join_level_m_t_real_rows(m,t); assert len(j)==len(m)
    with pytest.raises(ValueError): mod.join_level_m_t_real_rows(m+[m[0]],t)
    with pytest.raises(ValueError): mod.join_level_m_t_real_rows(m,t+[t[0]])
    with pytest.raises(ValueError): mod.join_level_m_t_real_rows(m,t[:-1])

def test_label_fallback_and_safety():
    rows=mod.join_level_m_t_real_rows(build_mock_ds005620_level_m_rows(),mod.build_mock_ds005620_level_t_rows())
    r=rows[0]
    r2=type(r)(**{**r.__dict__,'y':None,'state_label':'sedated','report_label':'experience','behavior_label':'responsive'})
    assert mod._select([r2],'awake_vs_sedated')[0].y==1
    assert mod._select([r2],'responsive_vs_unresponsive')[0].y==0
    assert mod._select([r2],'experience_vs_no_experience')[0].y==0

def test_reports_and_gate_and_outputs(tmp_path):
    rows=mod.join_level_m_t_real_rows(build_mock_ds005620_level_m_rows(),mod.build_mock_ds005620_level_t_rows())
    res=mod.evaluate_mt_residual(rows,'awake_vs_sedated')
    for k in ['observed_delta_auc','null_delta_auc','margin','nulls_passed','real_nulls_performed','null_methods']: assert k in res.null_report
    for k in ['M_only','M_plus_q_net','M_plus_q_abs','M_plus_f_dress','M_plus_defect_density','M_plus_topology_quality','M_plus_all_T']: assert k in res.ablation_report
    mod.write_mt_real_outputs(res,tmp_path,rows)
    names=['features_joined.csv','metrics_mt_real.json','nulls_real.json','ablations_real.json','leakage_report.json','artifact_report.json','omega_event.json','report.md']
    for n in names: assert (tmp_path/n).exists()
    assert 'residual predictive value' in (tmp_path/'report.md').read_text().lower()

def test_cli():
    cp=subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.run_ds005620_mt_real','--out','/tmp/mt_out','--mock-fixture'],capture_output=True,text=True)
    assert cp.returncode==0
    cp2=subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.run_ds005620_mt_real','--m-features','/nope','--t-features','/nope2','--out','/tmp/mt_out2'],capture_output=True,text=True)
    assert cp2.returncode!=0

def test_config_contract():
    text=Path('configs/btc_icft/ds005620_mt_real.yaml').read_text().lower()
    for term in ['required_outputs','metrics','promotion_gate','guardrails']: assert term in text
