from __future__ import annotations
import csv, json, subprocess, sys
from pathlib import Path
import pytest
from sciencer_d.btc_icft.labels.eeg_target_injection import *

MREQ=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","n_channels","n_samples","sample_rate_hz","spectral_power_proxy","entropy_proxy","lzc_proxy","artifact_score","feature_status"]
LREQ=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","label","y","label_scope","alignment_status","provenance"]

def _write_csv(p, cols, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

def mrow(i=0):
    return {c:'' for c in MREQ}|{"dataset_id":"DS005620","row_id":f"r{i}","source_file":"f.edf","window_id":f"w{i}","window_start_s":str(i),"window_end_s":str(i+1),"sample_start":str(i*10),"sample_end":str(i*10+10),"n_channels":"4","n_samples":"10","sample_rate_hz":"100","spectral_power_proxy":"0.1","entropy_proxy":"0.2","lzc_proxy":"0.3","artifact_score":"0.0","feature_status":"ok"}
def lrow(i=0,y='1',status='aligned',label='x'): return {"dataset_id":"DS005620","row_id":f"r{i}","source_file":"f.edf","window_id":f"w{i}","window_start_s":str(i),"window_end_s":str(i+1),"sample_start":str(i*10),"sample_end":str(i*10+10),"label":label,"y":y,"label_scope":"window","alignment_status":status,"provenance":"p12"}

def test_all(tmp_path):
    mp=tmp_path/'m.csv'; lp=tmp_path/'l.csv'; _write_csv(mp,MREQ,[mrow(0),mrow(1)]); _write_csv(lp,LREQ,[lrow(0,'1'),lrow(1,'0')])
    assert len(load_level_m_features(str(mp)))==2; assert len(load_label_alignment(str(lp)))==2
    with pytest.raises(FileNotFoundError): load_level_m_features(str(tmp_path/'x.csv'))
    with pytest.raises(FileNotFoundError): load_label_alignment(str(tmp_path/'y.csv'))
    bad=tmp_path/'bad.csv'; _write_csv(bad,[c for c in MREQ if c!='feature_status'],[{k:v for k,v in mrow().items() if k!='feature_status'}]);
    with pytest.raises(ValueError): load_level_m_features(str(bad))
    badl=tmp_path/'badl.csv'; _write_csv(badl,[c for c in LREQ if c!='provenance'],[{k:v for k,v in lrow().items() if k!='provenance'}]);
    with pytest.raises(ValueError): load_label_alignment(str(badl))
    r=inject_explicit_targets(load_level_m_features(str(mp)),load_label_alignment(str(lp)),"DS005620")
    assert r.binary_targets_available and r.explicit_targets_available and r.class_counts['1']==1 and r.class_counts['0']==1
    # coverage scenarios
    r2=inject_explicit_targets([mrow(0)],[lrow(0,'', 'aligned','onlytext')],"DS005620"); assert r2.n_labeled_rows==0
    r3=inject_explicit_targets([mrow(0)],[lrow(0,'2')],"DS005620"); assert any(x['target_status']=='rejected_invalid_y' for x in r3.rejected_rows)
    r4=inject_explicit_targets([mrow(0)],[lrow(0,'','aligned')],"DS005620"); assert any(x['target_status']=='rejected_missing_y' for x in r4.rejected_rows)
    r5=inject_explicit_targets([mrow(0)],[lrow(1,'1')],"DS005620"); assert any(x['target_status']=='rejected_no_matching_m_row' for x in r5.rejected_rows)
    r6=inject_explicit_targets([mrow(0)],[lrow(0,'1'),lrow(0,'0')],"DS005620"); assert any(x['target_status']=='rejected_conflicting_target' for x in r6.rejected_rows)
    r7=inject_explicit_targets([mrow(0)],[lrow(0,'1','aligned','a'),lrow(0,'1','aligned','a')],"DS005620"); assert r7.n_labeled_rows==1 and r7.warnings
    out=write_target_injection_outputs(r,tmp_path/'out')
    assert set(out.keys())=={"features_m_signal_labeled.csv","target_injection_rows.csv","target_injection_report.json","rejected_targets.json","omega_event.json","report.md"}
    json.loads(Path(out['target_injection_report.json']).read_text()); json.loads(Path(out['rejected_targets.json']).read_text());
    head=next(csv.DictReader(open(out['features_m_signal_labeled.csv']))); assert 'target_provenance' in head and 'feature_status' in head
    head2=next(csv.DictReader(open(out['target_injection_rows.csv']))); assert 'target_status' in head2 and 'provenance' in head2
    md=Path(out['report.md']).read_text().lower(); assert 'explicit p12 label targets' in md and 'level m signal features' in md and 'future target-aware signal-level residual testing' in md
    for b in ['proves consciousness','soul proven','sedated implies no_experience','unresponsive implies unconscious']: assert b not in md

def test_cli(tmp_path):
    c=[sys.executable,'-m','sciencer_d.btc_icft.pipelines.inject_eeg_targets','--dataset-id','DS005620','--out',str(tmp_path/'a'),'--mock-fixture']
    p=subprocess.run(c,capture_output=True,text=True); assert p.returncode==0 and '"ready_for_target_aware_p11": false' in p.stdout.lower()
    p=subprocess.run(c+['--mock-binary-targets','--out',str(tmp_path/'b')],capture_output=True,text=True); assert p.returncode==0 and '"ready_for_target_aware_p11": true' in p.stdout.lower()
    p=subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.inject_eeg_targets'],capture_output=True,text=True); assert p.returncode!=0
    p=subprocess.run(c+['--run-p11-smoke'],capture_output=True,text=True); assert p.returncode!=0 and 'requires explicit binary targets' in p.stdout.lower()
    cfg=Path('configs/btc_icft/eeg_target_injection.yaml').read_text(); assert 'required_outputs' in cfg and 'target_statuses' in cfg and 'guardrails' in cfg

def test_mock_fixture_aligns_with_t_features(tmp_path):
    tdir=tmp_path/'t'
    subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal','--dataset-id','DS005620','--out',str(tdir),'--mock-fixture'],check=True,capture_output=True,text=True)
    tf=str(tdir/'features_t_signal.csv')
    out=tmp_path/'inj'
    p=subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.inject_eeg_targets','--dataset-id','DS005620','--out',str(out),'--mock-fixture','--mock-binary-targets','--t-features',tf],capture_output=True,text=True)
    assert p.returncode==0
    mrows=list(csv.DictReader(open(out/'features_m_signal_labeled.csv',encoding='utf-8')))
    trows=list(csv.DictReader(open(tf,encoding='utf-8')))
    key=lambda r: tuple(r[k] for k in ['dataset_id','row_id','source_file','window_id','window_start_s','window_end_s','sample_start','sample_end'])
    tkeys={key(r) for r in trows}
    assert all(key(r) in tkeys for r in mrows)
    assert any(r['target_status']=='labeled_explicit_target' and r['y']=='1' for r in mrows)
    assert any(r['target_status']=='labeled_explicit_target' and r['y']=='0' for r in mrows)

def test_mock_non_binary_still_blocks_p11_smoke(tmp_path):
    tdir=tmp_path/'t'
    subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal','--dataset-id','DS005620','--out',str(tdir),'--mock-fixture'],check=True,capture_output=True,text=True)
    tf=str(tdir/'features_t_signal.csv')
    p=subprocess.run([sys.executable,'-m','sciencer_d.btc_icft.pipelines.inject_eeg_targets','--dataset-id','DS005620','--out',str(tmp_path/'inj'),'--mock-fixture','--run-p11-smoke','--t-features',tf,'--p11-out',str(tmp_path/'p11')],capture_output=True,text=True)
    assert p.returncode!=0 and 'requires explicit binary targets' in p.stdout.lower()

def test_non_aligned_label_not_injected():
    m=[mrow(0)]
    l=[lrow(0,'1','unaligned','ignored')]
    r=inject_explicit_targets(m,l,'DS005620')
    assert r.n_labeled_rows==0
    assert r.labeled_m_rows[0]['target_status']=='unlabeled_no_explicit_target'
    assert any(x['target_status']=='rejected_non_aligned_label' for x in r.rejected_rows)
