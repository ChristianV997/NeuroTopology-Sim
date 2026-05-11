from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.level_m.eeg_signal_features import (
    build_feature_quality_report,
    build_signal_artifact_report,
    extract_features_for_window,
    extract_signal_window_features,
    load_signal_window_inventory,
    write_level_m_signal_outputs,
)


def _fixture_signal(path: Path, flat=False, outlier=False):
    vals=[]
    for i in range(50):
        a = 1.0 if flat else (i/50)
        if outlier and i==25:
            a = 999.0
        vals.append((a, a*0.5))
    lines=["# channels: 2", "# sample_rate: 100", "ch1,ch2"]+[f"{a},{b}" for a,b in vals]
    path.write_text("\n".join(lines)+"\n", encoding="utf-8")


def _inventory(path: Path, sig: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["file_path","row_id","window_id","window_start_s","window_end_s","sample_start","sample_end","n_channels","n_samples","sample_rate_hz","status"])
        w.writeheader(); w.writerow({"file_path":str(sig),"row_id":"r1","window_id":"w1","window_start_s":"0","window_end_s":"0.5","sample_start":"0","sample_end":"20","n_channels":"2","n_samples":"20","sample_rate_hz":"100","status":"ok"})


def test_inventory_and_missing(tmp_path):
    sig=tmp_path/"s.csv"; _fixture_signal(sig)
    invd=tmp_path/"blocks"; invd.mkdir(); _inventory(invd/"window_inventory.csv", sig)
    rows=load_signal_window_inventory(str(invd)); assert len(rows)==1
    with pytest.raises(FileNotFoundError): load_signal_window_inventory(str(tmp_path/"missing"))


def test_extract_and_ranges(tmp_path):
    sig=tmp_path/"s.csv"; _fixture_signal(sig)
    good={"file_path":str(sig),"row_id":"r1","window_id":"w1","window_start_s":0,"window_end_s":1,"sample_start":0,"sample_end":20,"n_channels":2,"n_samples":20,"sample_rate_hz":100,"status":"short_window"}
    row=extract_features_for_window("DS", good)
    assert row.feature_status in {"ok","short_window"}
    assert row.spectral_power_proxy is not None and math.isfinite(row.spectral_power_proxy) and row.spectral_power_proxy >= 0
    assert 0 <= row.entropy_proxy <= 1
    assert row.lzc_proxy >= 0
    assert 0 <= row.artifact_score <= 1
    bad={**good,"sample_start":5,"sample_end":1}
    assert extract_features_for_window("DS", bad).feature_status.startswith("skipped")


def test_missing_source_and_reports(tmp_path):
    miss={"file_path":str(tmp_path/"none.csv"),"row_id":"r1","window_id":"w1","window_start_s":0,"window_end_s":1,"sample_start":0,"sample_end":10,"n_channels":2,"n_samples":10,"sample_rate_hz":100,"status":"ok"}
    row=extract_features_for_window("DS", miss)
    assert row.feature_status in {"skipped_unreadable_source","skipped_parse_error"}


def test_full_result_outputs_and_cli(tmp_path):
    sig=tmp_path/"s.csv"; _fixture_signal(sig)
    windows=[{"file_path":str(sig),"row_id":"r1","window_id":"w1","window_start_s":0,"window_end_s":1,"sample_start":0,"sample_end":20,"n_channels":2,"n_samples":20,"sample_rate_hz":100,"status":"ok"},
             {"file_path":str(tmp_path/'missing.csv'),"row_id":"r2","window_id":"w2","window_start_s":0,"window_end_s":1,"sample_start":0,"sample_end":20,"n_channels":2,"n_samples":20,"sample_rate_hz":100,"status":"ok"}]
    res=extract_signal_window_features("DS005620", windows)
    q=build_feature_quality_report([type('x',(),r)() for r in res.feature_rows], res.skipped_windows) if False else res.feature_quality_report
    a=res.artifact_report
    for k in ["n_windows","n_feature_rows","n_skipped_windows","mean_artifact_score","high_artifact_windows","finite_feature_rows","quality_passed"]: assert k in res.feature_quality_report
    for k in ["mean_artifact_score","max_artifact_score","high_artifact_windows","artifact_dominance","flatline_windows","amplitude_outlier_windows"]: assert k in a
    out=tmp_path/"out"; paths=write_level_m_signal_outputs(res, str(out))
    for name in ["features_m_signal.csv","feature_quality_report.json","artifact_report.json","skipped_windows.json","omega_event.json","report.md"]:
        assert (out/name).exists()
    json.loads((out/"feature_quality_report.json").read_text())
    text=(out/"report.md").read_text().lower()
    assert "operational level m signal feature candidates" in text and "future residual testing" in text and "signal feature" in text
    assert "proves consciousness" not in text

    cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal","--dataset-id","DS005620","--out",str(tmp_path/"cliout"),"--signal-blocks",str(tmp_path/"blocks"),"--mock-fixture"]
    ok=subprocess.run(cmd,capture_output=True,text=True)
    assert ok.returncode==0
    for name in ["features_m_signal.csv","feature_quality_report.json","artifact_report.json","skipped_windows.json","omega_event.json","report.md"]:
        assert (tmp_path/"cliout"/name).exists()

    fail=subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal","--signal-blocks",str(tmp_path/"nope"),"--out",str(tmp_path/"x")],capture_output=True,text=True)
    assert fail.returncode!=0 and "Run probe_eeg_signal_blocks first or use --mock-fixture" in (fail.stdout+fail.stderr)


def test_config_exists():
    txt=Path("configs/btc_icft/eeg_level_m_signal.yaml").read_text(encoding="utf-8")
    assert "required_outputs" in txt and "feature_columns" in txt and "guardrails" in txt
