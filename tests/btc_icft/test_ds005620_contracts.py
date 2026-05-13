from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CONTRACT_DIR = Path("contracts/btc_icft/ds005620/p18_1")
CONTRACT_FILES = [
    "ds005620_real_benchmark_execution.contract.json",
    "stage_execution_plan.contract.json",
    "stage_results.contract.json",
    "execution_blockers.contract.json",
    "omega_event.contract.json",
    "validation_summary.contract.json",
]

def _write_valid_root(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "report.md").write_text("ok\n", encoding="utf-8")
    (root / "ds005620_real_benchmark_execution.json").write_text(json.dumps({"dataset_id":"DS005620","mode":"mock_e2e","dry_run":False,"execute_requested":True,"peer_reviewed_contract_confirmed":True,"p12_executed":True,"p13_executed":True,"p11_executed":True,"p12_succeeded":True,"p13_succeeded":True,"p11_succeeded":True,"benchmark_completed":True,"artifact_root":str(root),"execution_blockers":[],"warnings":[],"safe_claim":"DS005620 P18.1 artifacts are now contract-validated for stable automation and replay-safe downstream tooling."}))
    (root / "stage_execution_plan.json").write_text(json.dumps({"stages":[{"stage_id":"P12","stage_name":"x","command":[sys.executable,"-m","align_eeg_labels","--external-contract","c"],"command_str":"align_eeg_labels --external-contract","ready_to_run":True,"expected_outputs":["a"]},{"stage_id":"P13","stage_name":"x","command":[sys.executable,"-m","inject_eeg_targets"],"command_str":"inject_eeg_targets","ready_to_run":True,"expected_outputs":["b"]},{"stage_id":"P11","stage_name":"x","command":[sys.executable,"-m","run_eeg_signal_mt","--m-features","features_m_signal_labeled.csv"],"command_str":"run_eeg_signal_mt --m-features features_m_signal_labeled.csv","ready_to_run":True,"expected_outputs":["c"]}],"paths":{}}))
    stages=[]
    for sid in ["P12","P13","P11"]:
        stages.append({"stage_id":sid,"stage_name":"x","command":[sid],"ready_to_run":True,"would_execute":True,"executed":True,"skipped":False,"succeeded":True,"exit_code":0,"blockers":[],"expected_outputs":[sid],"actual_outputs":[sid],"stdout_preview":"","stderr_preview":"","duration_seconds":0.1})
    (root / "stage_results.json").write_text(json.dumps({"stages":stages}))
    (root / "execution_blockers.json").write_text(json.dumps({"execution_blockers":[],"stage_blockers":{},"all_blockers":[],"blocker_counts":0}))
    (root / "omega_event.json").write_text(json.dumps({"event_id":"e","event_type":"ds005620_real_benchmark_execution","dataset_id":"DS005620","p12_executed":True,"p13_executed":True,"p11_executed":True,"benchmark_completed":True,"labels_inferred":False,"targets_fabricated":False,"source_contracts_modified":False,"legacy_mt_real_modified":False,"contracts_activated_by_executor":False,"p11_promotion_gate_modified":False,"consciousness_claims_made":False,"safe_claim":"DS005620 P18.1 artifacts are now contract-validated for stable automation and replay-safe downstream tooling.","forbidden_claims":[]}))
    (root / "validation_summary.json").write_text(json.dumps({"ok":True,"root":str(root),"failures":[],"checked_artifacts":["ds005620_real_benchmark_execution.json","stage_execution_plan.json","stage_results.json","execution_blockers.json","omega_event.json","report.md"],"checked_stages":["P12","P13","P11"],"benchmark_completed":True}))

def test_contract_files_exist():
    for f in CONTRACT_FILES:
        assert (CONTRACT_DIR / f).is_file()

def test_contract_files_are_valid_json():
    for f in CONTRACT_FILES:
        json.loads((CONTRACT_DIR / f).read_text(encoding="utf-8"))

def test_omega_contract_requires_false_invariants():
    data = json.loads((CONTRACT_DIR / "omega_event.contract.json").read_text())
    assert "labels_inferred" in data["required_false_keys"]

def test_stage_contract_allows_only_p12_p13_p11():
    data = json.loads((CONTRACT_DIR / "stage_execution_plan.contract.json").read_text())
    assert data["allowed_stage_ids"] == ["P12", "P13", "P11"]

def test_validator_passes_on_minimal_valid_mock_artifact_root(tmp_path: Path):
    _write_valid_root(tmp_path)
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 0

def test_validator_fails_missing_required_key(tmp_path: Path):
    _write_valid_root(tmp_path)
    p = tmp_path / "ds005620_real_benchmark_execution.json"
    d = json.loads(p.read_text()); d.pop("dataset_id"); p.write_text(json.dumps(d))
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 1

def test_validator_fails_benchmark_completed_true_but_p11_failed(tmp_path: Path):
    _write_valid_root(tmp_path)
    p = tmp_path / "ds005620_real_benchmark_execution.json"; d = json.loads(p.read_text()); d["p11_succeeded"] = False; p.write_text(json.dumps(d))
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 1

def test_validator_fails_when_p11_command_uses_raw_features_m(tmp_path: Path):
    _write_valid_root(tmp_path)
    p = tmp_path / "stage_execution_plan.json"; d = json.loads(p.read_text()); d["stages"][2]["command"][4] = "features_m_signal.csv"; p.write_text(json.dumps(d))
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 1

def test_validator_fails_when_omega_labels_inferred_true(tmp_path: Path):
    _write_valid_root(tmp_path)
    p = tmp_path / "omega_event.json"; d = json.loads(p.read_text()); d["labels_inferred"] = True; p.write_text(json.dumps(d))
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 1

def test_validator_writes_contract_validation_summary_json(tmp_path: Path):
    _write_valid_root(tmp_path)
    subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], check=False)
    assert (tmp_path / "contract_validation_summary.json").is_file()

def test_validator_quiet_suppresses_pass_output(tmp_path: Path):
    _write_valid_root(tmp_path)
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path), "--quiet"], capture_output=True, text=True)
    assert "PASS" not in rc.stdout

def test_validator_validates_validation_summary_when_present(tmp_path: Path):
    _write_valid_root(tmp_path)
    p = tmp_path / "validation_summary.json"; d = json.loads(p.read_text()); d["ok"] = True; d["failures"]=["x"]; p.write_text(json.dumps(d))
    rc = subprocess.run([sys.executable, "tools/validate_ds005620_contracts.py", "--root", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 1
