from __future__ import annotations
import csv
import json
import subprocess
import sys
from pathlib import Path
import pytest
from sciencer_d.btc_icft.labels.eeg_label_contracts import *



def _write_external_contract(path: Path, **overrides) -> Path:
    payload = {
        "dataset_id": "DS005620",
        "title": "Reviewed external contract",
        "source_hint": "reviewed_external_contract",
        "contract_status": "active_reviewed_external_contract",
        "label_scope": "window",
        "explicit_label_column": "explicit_state_label",
        "positive_values": ["target"],
        "negative_values": ["control"],
        "join_keys": ["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end"],
        "allowed_metadata_extensions": [".csv", ".tsv", ".json"],
        "caveats": [],
        "guardrails": ["no_label_inference", "no_target_fabrication"],
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path

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


# ---------------------------------------------------------------------------
# P12.1 — external reviewed contract support
# ---------------------------------------------------------------------------

_STRICT_JOIN_KEYS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
]


def _valid_external_contract(dataset_id: str = "DS005620") -> dict:
    return {
        "dataset_id": dataset_id,
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "label_scope": "window",
        "join_keys": _STRICT_JOIN_KEYS[:],
        "metadata_provenance": "data/DS005620/events.tsv",
        "activation_provenance": "p17_1_reviewed_materializer",
        "guardrails": ["no_label_inference"],
    }


def _write_signal_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS[:]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i in range(2):
            w.writerow({
                "dataset_id": "DS005620",
                "row_id": f"r{i}",
                "source_file": "f.edf",
                "window_id": f"w{i}",
                "window_start_s": str(i),
                "window_end_s": str(i + 1),
                "sample_start": str(i * 10),
                "sample_end": str((i + 1) * 10),
            })


def _write_metadata_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + ["trial_type"]
    rows = [
        {
            "dataset_id": "DS005620",
            "row_id": "r0",
            "source_file": "f.edf",
            "window_id": "w0",
            "window_start_s": "0",
            "window_end_s": "1",
            "sample_start": "0",
            "sample_end": "10",
            "trial_type": "focus",
        },
        {
            "dataset_id": "DS005620",
            "row_id": "r1",
            "source_file": "f.edf",
            "window_id": "w1",
            "window_start_s": "1",
            "window_end_s": "2",
            "sample_start": "10",
            "sample_end": "20",
            "trial_type": "mind_wandering",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def test_external_contract_valid_aligns_labels(tmp_path: Path):
    contract_path = tmp_path / "p12_external_contract.json"
    contract_path.write_text(json.dumps(_valid_external_contract()), encoding="utf-8")
    sig_path = tmp_path / "features_m_signal.csv"
    meta_path = tmp_path / "metadata.csv"
    _write_signal_csv(sig_path)
    _write_metadata_csv(meta_path)

    out_dir = tmp_path / "out"
    r = subprocess.run(
        [
            sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
            "--dataset-id", "DS005620",
            "--signal-features", str(sig_path),
            "--metadata", str(meta_path),
            "--external-contract", str(contract_path),
            "--out", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    aligned = (out_dir / "label_alignment.csv").read_text().strip().splitlines()
    header = aligned[0].split(",")
    rows = [dict(zip(header, line.split(","))) for line in aligned[1:]]
    aligned_rows = [r for r in rows if r["alignment_status"] == "aligned"]
    assert len(aligned_rows) == 2
    ys = sorted({r["y"] for r in aligned_rows})
    # y values should only be from explicit positive/negative mapping
    assert ys == ["0", "1"]


def test_external_contract_rejects_wrong_dataset_id(tmp_path: Path):
    bad = _valid_external_contract(dataset_id="DSXXX")
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="dataset_id"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_missing_or_wrong_status(tmp_path: Path):
    bad = _valid_external_contract()
    bad["contract_status"] = "preview_human_reviewed_not_active"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="contract_status"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_missing_explicit_label_column(tmp_path: Path):
    bad = _valid_external_contract()
    bad["explicit_label_column"] = ""
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit_label_column"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_empty_positive_values(tmp_path: Path):
    bad = _valid_external_contract()
    bad["positive_values"] = []
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="positive_values"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_empty_negative_values(tmp_path: Path):
    bad = _valid_external_contract()
    bad["negative_values"] = []
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="negative_values"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_overlapping_positive_negative_values(tmp_path: Path):
    bad = _valid_external_contract()
    bad["positive_values"] = ["focus", "shared"]
    bad["negative_values"] = ["mind_wandering", "shared"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_external_contract_rejects_missing_strict_join_keys(tmp_path: Path):
    bad = _valid_external_contract()
    bad["join_keys"] = ["dataset_id", "row_id"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="strict keys"):
        load_external_eeg_label_contract(str(p), "DS005620")


def test_existing_mock_fixture_still_passes(tmp_path: Path):
    out = tmp_path / "inactive"
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
         "--dataset-id", "DS005620", "--out", str(out), "--mock-fixture"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    rep = json.loads((out / "label_alignment_report.json").read_text())
    assert rep["explicit_targets_available"] is False


def test_existing_activate_mock_contract_still_passes(tmp_path: Path):
    out = tmp_path / "active"
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
         "--dataset-id", "DS005620", "--out", str(out),
         "--mock-fixture", "--activate-mock-contract"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    rep = json.loads((out / "label_alignment_report.json").read_text())
    assert rep["explicit_targets_available"] is True


def test_external_contract_missing_file_returns_nonzero(tmp_path: Path):
    sig_path = tmp_path / "features_m_signal.csv"
    meta_path = tmp_path / "metadata.csv"
    _write_signal_csv(sig_path)
    _write_metadata_csv(meta_path)

    r = subprocess.run(
        [
            sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
            "--dataset-id", "DS005620",
            "--signal-features", str(sig_path),
            "--metadata", str(meta_path),
            "--external-contract", str(tmp_path / "missing.json"),
            "--out", str(tmp_path / "out"),
        ],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "External reviewed contract" in r.stderr

def test_cli_external_contract_validation_and_alignment(tmp_path: Path):
    s = tmp_path/"s.csv"
    s.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end\nDS005620,r0,f.edf,w0,0,1,0,10\n")
    m = tmp_path/"m.csv"
    m.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end,explicit_state_label\nDS005620,r0,f.edf,w0,0,1,0,10,target\n")
    c = _write_external_contract(tmp_path/"contract.json")
    out = tmp_path/"out"
    r = subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--signal-features",str(s),"--metadata",str(m),"--external-contract",str(c),"--out",str(out)],capture_output=True,text=True)
    assert r.returncode == 0
    rep=json.loads((out/"label_alignment_report.json").read_text())
    assert rep["n_targets_available"] == 1 and rep["explicit_targets_available"] is True


def test_cli_external_contract_rejections(tmp_path: Path):
    s = tmp_path/"s.csv"
    s.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end\nDS005620,r0,f.edf,w0,0,1,0,10\n")
    m = tmp_path/"m.csv"
    m.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end,explicit_state_label\nDS005620,r0,f.edf,w0,0,1,0,10,target\n")
    def run_bad(payload):
        c = _write_external_contract(tmp_path/"bad.json", **payload)
        return subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--signal-features",str(s),"--metadata",str(m),"--external-contract",str(c),"--out",str(tmp_path/"o")],capture_output=True,text=True)
    assert run_bad({"dataset_id":"DSX"}).returncode != 0
    assert run_bad({"contract_status":"inactive_until_metadata_supplied"}).returncode != 0
    assert run_bad({"explicit_label_column":""}).returncode != 0
    assert run_bad({"positive_values":[]}).returncode != 0
    assert run_bad({"negative_values":[]}).returncode != 0
    assert run_bad({"positive_values":["target"],"negative_values":["target"]}).returncode != 0
    assert run_bad({"join_keys":["dataset_id"]}).returncode != 0

def test_external_contract_legacy_status_compatibility(tmp_path: Path):
    c = _write_external_contract(tmp_path/"legacy.json")
    payload = json.loads(c.read_text())
    payload.pop("contract_status")
    payload["status"] = "active_reviewed_external_contract"
    c.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_external_eeg_label_contract(str(c), "DS005620")
    assert loaded.status == "active"


def test_cli_rejects_external_plus_activate_mock(tmp_path: Path):
    s = tmp_path/"s.csv"
    s.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end\nDS005620,r0,f.edf,w0,0,1,0,10\n")
    m = tmp_path/"m.csv"
    m.write_text("dataset_id,row_id,source_file,window_id,window_start_s,window_end_s,sample_start,sample_end,explicit_state_label\nDS005620,r0,f.edf,w0,0,1,0,10,target\n")
    c = _write_external_contract(tmp_path/"contract.json")
    out = tmp_path/"out"
    r = subprocess.run([sys.executable,"-m","sciencer_d.btc_icft.pipelines.align_eeg_labels","--dataset-id","DS005620","--signal-features",str(s),"--metadata",str(m),"--external-contract",str(c),"--activate-mock-contract","--out",str(out)],capture_output=True,text=True)
    assert r.returncode != 0
    assert "cannot be combined" in r.stdout
    assert not (out/"label_alignment_report.json").exists()
