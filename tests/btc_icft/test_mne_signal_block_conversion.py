from __future__ import annotations
import csv, json, math, subprocess, sys
from pathlib import Path
from sciencer_d.btc_icft.io.mne_signal_block_conversion import *


def _fixture(tmp_path: Path, extraction_status="extracted", bad=None):
    d=tmp_path/"in"; d.mkdir(exist_ok=True)
    meta={"dataset_id":"DS005620","source_file":"file.edf","extraction_status":extraction_status}
    windows=[{"dataset_id":"DS005620","row_id":"r0","source_file":"file.edf","window_id":"win-000","window_start_s":0.0,"window_end_s":1.0,"sample_start":0,"sample_end":10,"sample_rate_hz":10.0,"n_channels":2,"n_samples":10,"channel_names":["C3","C4"],"warnings":[]},]
    values={"dataset_id":"DS005620","source_file":"file.edf","windows":[{"row_id":"r0","window_id":"win-000","channel_names":["C3","C4"],"signal_values":[[0.0]*10,[1.0]*10]}]}
    if bad=="missing_values": values["windows"]=[]
    if bad=="channel_mismatch": values["windows"][0]["channel_names"]=["X","Y"]
    if bad=="n_channels": values["windows"][0]["signal_values"]=[[0.0]*10]
    if bad=="n_samples": values["windows"][0]["signal_values"][0]=[0.0]*9
    if bad=="non_numeric": values["windows"][0]["signal_values"][0][0]="x"
    if bad=="nan": values["windows"][0]["signal_values"][0][0]=math.nan
    if bad=="inf": values["windows"][0]["signal_values"][0][0]=math.inf
    (d/"mne_signal_metadata.json").write_text(json.dumps(meta))
    with open(d/"mne_signal_windows.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","sample_rate_hz","n_channels","n_samples","channel_names","warnings"]);w.writeheader();row=windows[0].copy();row["channel_names"]="C3|C4";row["warnings"]="";w.writerow(row)
    (d/"mne_signal_window_values.json").write_text(json.dumps(values, allow_nan=True))
    return d, meta, windows, values


def test_all(tmp_path):
    d, meta, windows, values = _fixture(tmp_path)
    assert load_mne_signal_metadata(str(d/"mne_signal_metadata.json"))["dataset_id"]=="DS005620"
    assert len(load_mne_signal_windows(str(d/"mne_signal_windows.csv")))==1
    assert load_mne_signal_window_values(str(d/"mne_signal_window_values.json"))["dataset_id"]=="DS005620"
    r=convert_mne_windows_to_canonical_blocks(meta,windows,values,"DS005620"); assert r.conversion_status=="converted" and r.ready_for_level_m_signal and r.ready_for_level_t_signal
    r=convert_mne_windows_to_canonical_blocks({**meta,"extraction_status":"dependency_missing"},windows,values,"DS005620"); assert r.conversion_status=="blocked_input_not_extracted"
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","missing_values")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","channel_mismatch")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","n_channels")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","n_samples")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","non_numeric")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","nan")[3],"DS005620").n_rejected_windows==1
    assert convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","inf")[3],"DS005620").n_rejected_windows==1
    r=convert_mne_windows_to_canonical_blocks(meta,windows,values,"DS005620");
    for k in STRICT_JOIN_KEYS: assert k in r.windows[0]
    assert r.windows[0]["row_id"]=="r0"
    w2=[{**windows[0]}]; w2[0].pop("row_id"); r2=convert_mne_windows_to_canonical_blocks(meta,w2,{"windows":[{**values["windows"][0],"row_id":"file__win_0"}]},"DS005620"); assert r2.windows[0]["row_id"].startswith("file__win_")
    r3=convert_mne_windows_to_canonical_blocks(meta,windows,_fixture(tmp_path,"extracted","missing_values")[3],"DS005620"); assert not r3.ready_for_level_m_signal and not r3.ready_for_level_t_signal
    out=tmp_path/"out"; files=write_mne_signal_block_outputs(r,out); assert len(files)==7
    for n in files: assert Path(files[n]).exists()
    json.loads((out/"signal_block_inventory.json").read_text());json.loads((out/"window_signal_values.json").read_text());json.loads((out/"reader_alignment_report.json").read_text());json.loads((out/"rejected_windows.json").read_text());json.loads((out/"omega_event.json").read_text())
    hdr=next(csv.DictReader(open(out/"window_inventory.csv"))); assert "dataset_id" in hdr and "conversion_status" in hdr
    assert json.loads((out/"reader_alignment_report.json").read_text())["p8_2_compatible"] is True
    assert "without inferring labels or targets" in json.loads((out/"omega_event.json").read_text())["safe_claim"].lower()
    md=(out/"report.md").read_text().lower(); assert "canonical signal-block artifacts" in md and "without inferring labels or targets" in md and "readiness for level m and level t" in md
    for p in BANNED_PHRASES: assert p not in md
    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks","--dataset-id","DS005620","--mock-fixture","--out",str(tmp_path/"cli1")]; assert subprocess.run(cmd).returncode==0
    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks","--dataset-id","DS005620","--mock-blocked-input","--out",str(tmp_path/"cli2")]; assert subprocess.run(cmd).returncode==0
    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks","--dataset-id","DS005620"]; assert subprocess.run(cmd).returncode!=0
    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks","--dataset-id","DS005620","--mne-extract",str(tmp_path/"none")]; assert subprocess.run(cmd,capture_output=True,text=True).returncode!=0
    cfg=(Path("configs/btc_icft/mne_signal_block_conversion.yaml").read_text()); assert "required_inputs" in cfg and "required_outputs" in cfg and "strict_join_keys" in cfg and "guardrails" in cfg
    alltxt="\n".join([(out/f).read_text(errors="ignore") for f in ["signal_block_inventory.json","window_signal_values.json","reader_alignment_report.json","omega_event.json","report.md"]]); assert '"y"' not in alltxt
    assert "label" in cfg  # guardrail declaration only
    imports=Path("sciencer_d/btc_icft/pipelines/convert_mne_to_signal_blocks.py").read_text(); assert "run_eeg_level_m_signal" not in imports and "run_eeg_level_t_signal" not in imports and "run_eeg_signal_mt" not in imports
    assert "p11" not in imports.lower() and "p12" not in imports.lower() and "p13" not in imports.lower() and "p17" not in imports.lower() and "p20" not in imports.lower()
    assert "mt_real" not in imports.lower()
    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks","--dataset-id","DS005620","--mock-fixture","--max-windows","1","--out",str(tmp_path/"cli3")]; assert subprocess.run(cmd).returncode==0
    inv=csv.DictReader(open(tmp_path/"cli3"/"window_inventory.csv")); assert len(list(inv))==1
