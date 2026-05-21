from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

from sciencer_d.btc_icft.labels.eeg_label_contracts import (
    load_external_label_contract,
    normalize_external_label_contract,
    validate_external_label_contract,
)

def _contract(**overrides):
    base = {
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "explicit_state_label",
        "positive_values": ["target"],
        "negative_values": ["control"],
        "label_scope": "window",
        "join_keys": ["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end"],
        "metadata_provenance": "x",
        "activation_provenance": "y",
        "guardrails": ["no_label_inference", "no_target_fabrication"],
    }
    base.update(overrides)
    return base

def test_load_external_label_contract_reads_json(tmp_path: Path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(_contract()), encoding="utf-8")
    assert load_external_label_contract(str(p))["dataset_id"] == "DS005620"

def test_missing_and_malformed_fail_cleanly(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_external_label_contract(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_external_label_contract(str(bad))

def test_validation_rules():
    with pytest.raises(ValueError): validate_external_label_contract(_contract(dataset_id="X"), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(contract_status="inactive"), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(explicit_label_column=""), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(positive_values=[]), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(negative_values=[]), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(negative_values=["target"]), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(join_keys=["dataset_id"]), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(metadata_provenance=None), "DS005620")
    with pytest.raises(ValueError): validate_external_label_contract(_contract(guardrails=[]), "DS005620")
    assert validate_external_label_contract(_contract(), "DS005620")["status"] == "active"

def test_normalized_shape():
    n = normalize_external_label_contract(_contract())
    assert n["status"] == "active"
    assert n["contract_status"] == "active_reviewed_external_contract"

def test_cli_external_contract_outputs(tmp_path: Path):
    out = tmp_path / "out"
    c = tmp_path / "c.json"
    c.write_text(json.dumps(_contract()), encoding="utf-8")
    r = subprocess.run([
        sys.executable, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
        "--dataset-id", "DS005620",
        "--external-contract", str(c),
        "--mock-fixture",
        "--out", str(out),
    ], capture_output=True, text=True)
    assert r.returncode == 0
    lc = json.loads((out / "label_contract.json").read_text())
    rep = json.loads((out / "label_alignment_report.json").read_text())
    omg = json.loads((out / "omega_event.json").read_text())
    md = (out / "report.md").read_text().lower()
    assert lc["contract_source"] == "external_reviewed_contract"
    assert rep["external_contract_used"] is True
    assert "without inferring labels or targets" in omg["safe_claim"].lower()
    assert "reviewed external contract" in md
    assert "run p13 target injection only after inspecting p12 alignment outputs" in md
    for ban in ["proves consciousness","consciousness proven","soul proven","afterlife proven","liberation detected","ontology solved","ultimate reality","q equals self","q equals soul","q_abs equals suffering","f_dress equals karma","sedated implies no_experience","unresponsive implies unconscious","topology proves liberation","eeg proves consciousness"]:
        assert ban not in md
