from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest
from sciencer_d.btc_icft.labels.eeg_label_contracts import *


def _signal_row():
    return {"dataset_id":"DS005620","row_id":"r1","source_file":"f.edf","window_id":"w1","window_start_s":"0","window_end_s":"1","sample_start":"0","sample_end":"10"}

def test_seed_contracts_present_and_inactive():
    c=get_seed_label_contracts();
    for d in ["DS005620","DS002094","ds001787","ds003969","ds003816","PhysioNet_GABA"]:
        assert d in c and c[d].status=="inactive_until_metadata_supplied"

def test_inactive_rejects_and_no_targets():
    c=get_label_contract("DS005620")
    r=align_eeg_labels("DS005620",[_signal_row()],[{"row_id":"r1"}],c)
    assert r.explicit_targets_available is False
    assert all(x["alignment_status"]=="rejected_contract_inactive" for x in r.alignment_rows)

def test_load_metadata_variants(tmp_path:Path):
    (tmp_path/"m.csv").write_text("a,b\n1,2\n"); assert len(load_metadata_rows(str(tmp_path/"m.csv")))==1
    (tmp_path/"m.tsv").write_text("a\tb\n1\t2\n"); assert len(load_metadata_rows(str(tmp_path/"m.tsv")))==1
    (tmp_path/"m.json").write_text(json.dumps([{"a":1}])); assert len(load_metadata_rows(str(tmp_path/"m.json")))==1
    (tmp_path/"m2.json").write_text(json.dumps({"rows":[{"a":1}]})); assert len(load_metadata_rows(str(tmp_path/"m2.json")))==1
    (tmp_path/"m.txt").write_text("x\n")
    with pytest.raises(ValueError): load_metadata_rows(str(tmp_path/"m.txt"))
    with pytest.raises(FileNotFoundError): load_metadata_rows(str(tmp_path/"missing.csv"))

def test_signal_loading_and_missing_cols(tmp_path:Path):
    p=tmp_path/"s.csv"; p.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end\nDS005620,r1,f,w,0,1,0,10\n")
    assert len(load_signal_rows(str(p)))==1
    q=tmp_path/"bad.csv"; q.write_text("dataset_id\nDS005620\n")
    with pytest.raises(ValueError): load_signal_rows(str(q))

def test_active_alignment_paths(tmp_path:Path):
    c=get_label_contract("DS005620"); c.status="active"; c.explicit_label_column="lbl"; c.positive_values=["target"]; c.negative_values=["control"]
    s=[_signal_row()]
    assert align_eeg_labels("DS005620",s,[{**_signal_row(),"lbl":"target"}],c).alignment_rows[0]["y"]==1
    assert align_eeg_labels("DS005620",s,[{**_signal_row(),"lbl":"control"}],c).alignment_rows[0]["y"]==0
    assert align_eeg_labels("DS005620",s,[{**_signal_row(),"lbl":"other"}],c).alignment_rows[0]["alignment_status"]=="rejected_unknown_label_value"
    assert align_eeg_labels("DS005620",s,[{**_signal_row()}],c).alignment_rows[0]["alignment_status"]=="rejected_missing_label"
    s_bad=[{"dataset_id":"DS005620"}]
    assert align_eeg_labels("DS005620",s_bad,[{**_signal_row(),"lbl":"target"}],c).alignment_rows[0]["alignment_status"]=="rejected_missing_join_key"
    c.positive_values=["target"]; c.negative_values=["target"]
    assert align_eeg_labels("DS005620",s,[{**_signal_row(),"lbl":"target"}],c).alignment_rows[0]["alignment_status"]=="rejected_ambiguous_mapping"

def test_conflict_and_broad_scope_and_reports(tmp_path:Path):
    c=get_label_contract("DS005620"); c.status="active"; c.explicit_label_column="lbl"; c.positive_values=["target"]; c.negative_values=["control"]
    r=align_eeg_labels("DS005620",[_signal_row()],[{**_signal_row(),"lbl":"target"},{**_signal_row(),"lbl":"control"}],c)
    assert r.alignment_rows[0]["alignment_status"]=="rejected_conflicting_label"
    c.label_scope="file"
    rr=align_eeg_labels("DS005620",[_signal_row()],[{"source_file":"f.edf","lbl":"target"}],c)
    assert "broader than window" in " ".join(rr.alignment_rows[0]["caveats"])
    out=write_label_alignment_outputs(rr,str(tmp_path/"o"))
    for n in ["label_contract.json","label_alignment.csv","label_alignment_report.json","rejected_labels.json","omega_event.json","report.md"]: assert n in out
    json.loads((tmp_path/"o"/"label_alignment_report.json").read_text())
    header=(tmp_path/"o"/"label_alignment.csv").read_text().splitlines()[0]
    for ccol in ["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","label","y","label_scope","alignment_status","provenance","caveats","warnings"]: assert ccol in header
    md=(tmp_path/"o"/"report.md").read_text().lower()
    assert "explicit local eeg metadata labels" in md and "declared label contract" in md and "future controlled predictive testing" in md
    for ban in ["proves consciousness","consciousness proven","soul proven","afterlife proven","liberation detected","ontology solved","ultimate reality"]: assert ban not in md

def test_ready_for_p11_variants():
    c=get_label_contract("DS005620"); c.status="active"; c.explicit_label_column="lbl"; c.positive_values=["target"]; c.negative_values=["control"]
    s1={**_signal_row(),"row_id":"r1","window_id":"w1"}; s2={**_signal_row(),"row_id":"r2","window_id":"w2","sample_start":"10","sample_end":"20","window_start_s":"1","window_end_s":"2"}
    r1=align_eeg_labels("DS005620",[s1],[{**s1,"lbl":"target"}],c)
    assert r1.label_alignment_report["ready_for_p11_with_targets"] is False
    r2=align_eeg_labels("DS005620",[s1,s2],[{**s1,"lbl":"target"},{**s2,"lbl":"control"}],c)
    assert r2.label_alignment_report["ready_for_p11_with_targets"] is True

def test_cli_modes_and_config(tmp_path:Path):
    out=tmp_path/"inactive"
    r=subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--out",str(out),"--mock-fixture"],capture_output=True,text=True)
    assert r.returncode==0
    rep=json.loads((out/"label_alignment_report.json").read_text()); assert rep["explicit_targets_available"] is False
    out2=tmp_path/"active"
    r2=subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--out",str(out2),"--mock-fixture","--activate-mock-contract"],capture_output=True,text=True)
    assert r2.returncode==0
    rep2=json.loads((out2/"label_alignment_report.json").read_text()); assert rep2["explicit_targets_available"] is True
    r3=subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--out",str(tmp_path/"no_meta")],capture_output=True,text=True)
    assert r3.returncode!=0 and "Explicit local metadata is required" in r3.stdout
    cfg=Path("configs/btc_icft/eeg_label_contracts.yaml").read_text()
    assert "required_outputs" in cfg and "required_statuses" in cfg and "guardrails" in cfg
