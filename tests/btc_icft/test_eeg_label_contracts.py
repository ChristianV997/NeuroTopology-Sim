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


# ---------------------------------------------------------------------------
# P12.1 external-contract tests
# ---------------------------------------------------------------------------

_STRICT_JOIN_KEYS = ["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end"]


def _valid_external_contract(dataset_id: str = "DS005620") -> dict:
    return {
        "dataset_id": dataset_id,
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "label_scope": "window",
        "join_keys": _STRICT_JOIN_KEYS[:],
        "guardrails": ["no_label_inference"],
    }


def _write_contract(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _signal_row_ext():
    return {"dataset_id":"DS005620","row_id":"r1","source_file":"f.edf","window_id":"w1",
            "window_start_s":"0","window_end_s":"1","sample_start":"0","sample_end":"10"}


def _meta_row_ext(label: str = "focus"):
    return {**_signal_row_ext(), "trial_type": label}


def test_external_contract_valid_aligns_explicit_labels(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract, run
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, _valid_external_contract())
    # Write signal CSV
    sig = tmp_path / "sig.csv"
    with sig.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_signal_row_ext())); w.writeheader(); w.writerow(_signal_row_ext())
    # Write metadata CSV
    meta = tmp_path / "meta.csv"
    with meta.open("w", newline="", encoding="utf-8") as f:
        row = _meta_row_ext("focus")
        w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)
    out = tmp_path / "out"
    rc = run("DS005620", str(sig), str(meta), str(out), external_contract=str(contract_path))
    assert rc == 0
    rep = json.loads((out / "label_alignment_report.json").read_text())
    assert rep["explicit_targets_available"] is True
    assert rep["n_aligned"] == 1


def test_external_contract_wrong_dataset_id_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = _valid_external_contract(dataset_id="DS002094")
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="dataset_id"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_wrong_status_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "contract_status": "preview_human_reviewed_not_active"}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="contract_status"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_missing_status_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {k: v for k, v in _valid_external_contract().items() if k != "contract_status"}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="contract_status"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_missing_explicit_label_column_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "explicit_label_column": ""}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="explicit_label_column"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_missing_positive_values_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "positive_values": []}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="positive_values"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_missing_negative_values_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "negative_values": []}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="negative_values"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_overlapping_values_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "positive_values": ["focus"], "negative_values": ["focus"]}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="overlap"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_missing_strict_join_keys_blocks(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.align_eeg_labels import load_external_contract
    data = {**_valid_external_contract(), "join_keys": ["row_id", "window_id"]}
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, data)
    with pytest.raises(ValueError, match="join_keys"):
        load_external_contract(str(contract_path), "DS005620")


def test_external_contract_cli_exits_0(tmp_path: Path):
    """CLI with valid --external-contract and matching metadata exits 0 and produces targets."""
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, _valid_external_contract())
    sig = tmp_path / "sig.csv"
    with sig.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_signal_row_ext())); w.writeheader(); w.writerow(_signal_row_ext())
    meta = tmp_path / "meta.csv"
    with meta.open("w", newline="", encoding="utf-8") as f:
        row = _meta_row_ext("focus")
        w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)
    out = tmp_path / "out"
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
         "--dataset-id", "DS005620",
         "--signal-features", str(sig),
         "--metadata", str(meta),
         "--external-contract", str(contract_path),
         "--out", str(out)],
        capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads((out / "label_alignment_report.json").read_text())
    assert rep["explicit_targets_available"] is True


def test_external_contract_cli_wrong_dataset_id_fails(tmp_path: Path):
    """CLI with wrong dataset_id in contract exits non-zero with clear error."""
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, _valid_external_contract(dataset_id="DS002094"))
    sig = tmp_path / "sig.csv"
    with sig.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_signal_row_ext())); w.writeheader(); w.writerow(_signal_row_ext())
    meta = tmp_path / "meta.csv"
    with meta.open("w", newline="", encoding="utf-8") as f:
        row = _meta_row_ext(); w2 = csv.DictWriter(f, fieldnames=list(row)); w2.writeheader(); w2.writerow(row)
    out = tmp_path / "out"
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
         "--dataset-id", "DS005620",
         "--signal-features", str(sig),
         "--metadata", str(meta),
         "--external-contract", str(contract_path),
         "--out", str(out)],
        capture_output=True, text=True
    )
    assert r.returncode != 0
    assert "dataset_id" in r.stdout


def test_p18_readiness_no_longer_blocked_p12_external_contract(tmp_path: Path):
    """After P12.1, _check_p12_supports_external_contract() returns True."""
    from sciencer_d.btc_icft.p18.ds005620_benchmark_readiness import _check_p12_supports_external_contract
    assert _check_p12_supports_external_contract() is True


def test_p18_dry_run_p12_no_blocked_handshake_blocker(tmp_path: Path):
    """P18.0 dry-run plan P12 step has no blocked_p12_external_contract_handshake_missing blocker."""
    from sciencer_d.btc_icft.p18.ds005620_benchmark_readiness import build_ds005620_benchmark_readiness
    inputs = {"reviewed_contract": None, "metadata": None, "signal_blocks": None, "level_m": None, "level_t": None}
    result = build_ds005620_benchmark_readiness(inputs)
    p12_cmd = next((c for c in result.dry_run_command_plan if c["stage"] == "P12"), None)
    assert p12_cmd is not None
    assert "blocked_p12_external_contract_handshake_missing" not in p12_cmd.get("blockers", [])
