from __future__ import annotations
import json, subprocess, sys
from pathlib import Path


def test_real_runbook_cycle(tmp_path: Path):
    out = tmp_path / "runbook"
    rc = subprocess.run([sys.executable, "-m", "tools.ds005620_real_runbook.readiness_report", "--out", str(out)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    required = [
        "data_room_audit.json","missing_local_files.json","operator_checklist.md","reviewed_contract_audit.json",
        "real_run_command_manual_only.json","post_run_expected_artifacts.json","ds005620_real_runbook_report.md","generation_manifest.json","readiness_report.json"
    ]
    for f in required:
        assert (out / f).exists(), f
    cmd = json.loads((out / "real_run_command_manual_only.json").read_text())
    assert cmd["not_executed_by_tool"] is True
    assert cmd["requires_human_peer_review"] is True
    assert cmd["can_auto_execute"] is False
    rep = json.loads((out / "readiness_report.json").read_text())
    assert rep["empirical_claims_permitted"] is False


def test_validator_rejects_auto_execute(tmp_path: Path):
    out = tmp_path / "runbook"
    subprocess.run([sys.executable, "-m", "tools.ds005620_real_runbook.readiness_report", "--out", str(out)], check=True)
    p = out / "real_run_command_manual_only.json"
    d = json.loads(p.read_text()); d["can_auto_execute"] = True; p.write_text(json.dumps(d), encoding="utf-8")
    rc = subprocess.run([sys.executable, "-m", "tools.ds005620_real_runbook.validator", "--root", str(out)], capture_output=True, text=True)
    assert rc.returncode != 0
    val = json.loads((out / "validation.json").read_text())
    assert any("auto-execute" in e for e in val["errors"])
