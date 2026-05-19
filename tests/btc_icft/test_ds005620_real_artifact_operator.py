"""
Tests for P20: DS005620 real artifact build operator.

All tests run without real DS005620 data. No real EEG files, no real downloads,
no label inference, no target fabrication, no peer-review confirmation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.p18.ds005620_real_artifact_operator import (
    DS005620RealArtifactBuildPlan,
    DS005620RealArtifactCommand,
    DS005620RealArtifactOperatorResult,
    DS005620RealArtifactPathConfig,
    DS005620RealArtifactStage,
    _FORBIDDEN_PHRASES,
    _PLANNER_VERSION,
    _SAFE_CLAIM,
    build_default_real_artifact_path_config,
    build_ds005620_real_artifact_build_plan,
    write_ds005620_real_artifact_operator_outputs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_cfg(tmp_path: Path) -> DS005620RealArtifactPathConfig:
    return build_default_real_artifact_path_config(
        metadata=str(tmp_path / "events.tsv"),
        raw_eeg_root=str(tmp_path / "raw"),
        reviewed_contract_source=str(tmp_path / "declaration.json"),
        reviewed_contract=str(tmp_path / "p12_external_contract.json"),
        reader_preflight=str(tmp_path / "eeg_reader_preflight"),
        mne_extract=str(tmp_path / "eeg_mne_extract"),
        signal_blocks=str(tmp_path / "signal_blocks"),
        level_m=str(tmp_path / "features_m_signal.csv"),
        level_t=str(tmp_path / "features_t_signal.csv"),
        real_execution_gate=str(tmp_path / "ready_for_real_execution.json"),
    )


def _seed_all_artifacts(cfg: DS005620RealArtifactPathConfig) -> None:
    """Create all expected artifact files/dirs so all stages are 'complete'."""
    Path(cfg.metadata_path).write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    Path(cfg.raw_eeg_root).mkdir(parents=True, exist_ok=True)
    (Path(cfg.raw_eeg_root) / "sub-01_eeg.bdf").write_text("dummy", encoding="utf-8")
    Path(cfg.reviewed_contract_source).write_text("{}", encoding="utf-8")
    Path(cfg.reviewed_contract_materialized).write_text("{}", encoding="utf-8")
    Path(cfg.reader_preflight_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.reader_preflight_path) / "preflight.json").write_text("{}", encoding="utf-8")
    Path(cfg.mne_extract_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.mne_extract_path) / "signal_block_inventory.json").write_text("{}", encoding="utf-8")
    Path(cfg.signal_blocks_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.signal_blocks_path) / "signal_block_inventory.json").write_text("{}", encoding="utf-8")
    Path(cfg.level_m_csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.level_m_csv_path).write_text("col\n", encoding="utf-8")
    Path(cfg.level_t_csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.level_t_csv_path).write_text("col\n", encoding="utf-8")
    Path(cfg.real_execution_gate_path).write_text(
        json.dumps({"ready_for_real_execution": True, "next_action": "human_peer_review_required"}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test 1 — path config has required fields
# ---------------------------------------------------------------------------

def test_path_config_has_required_fields():
    cfg = build_default_real_artifact_path_config()
    assert cfg.dataset_id == "DS005620"
    assert "events.tsv" in cfg.metadata_path
    assert "raw" in cfg.raw_eeg_root
    assert "activation_declaration" in cfg.reviewed_contract_source
    assert "p12_external_contract" in cfg.reviewed_contract_materialized
    assert "eeg_reader_preflight" in cfg.reader_preflight_path
    assert "eeg_mne_extract" in cfg.mne_extract_path
    assert "signal_blocks_from_mne" in cfg.signal_blocks_path
    assert "features_m_signal.csv" in cfg.level_m_csv_path
    assert "features_t_signal.csv" in cfg.level_t_csv_path
    assert "ready_for_real_execution.json" in cfg.real_execution_gate_path


# ---------------------------------------------------------------------------
# Test 2 — planner version
# ---------------------------------------------------------------------------

def test_planner_version_is_p20():
    assert _PLANNER_VERSION == "p20.0"


# ---------------------------------------------------------------------------
# Test 3 — plan builds with no artifacts present (all stages missing)
# ---------------------------------------------------------------------------

def test_plan_builds_when_all_artifacts_missing(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert isinstance(plan, DS005620RealArtifactBuildPlan)
    assert plan.dataset_id == "DS005620"
    assert not plan.all_stages_complete
    assert not plan.ready_for_real_execution_gate
    assert not plan.ready_for_manual_real_execution


# ---------------------------------------------------------------------------
# Test 4 — next_action is provide_metadata when nothing is present
# ---------------------------------------------------------------------------

def test_next_action_is_provide_metadata_when_empty(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert plan.next_action == "provide_metadata"


# ---------------------------------------------------------------------------
# Test 5 — stage list has exactly 10 stages
# ---------------------------------------------------------------------------

def test_plan_has_ten_stages(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert len(plan.stages) == 10


# ---------------------------------------------------------------------------
# Test 6 — stage IDs match expected list
# ---------------------------------------------------------------------------

def test_plan_stage_ids(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    stage_ids = [s.stage_id for s in plan.stages]
    assert "metadata" in stage_ids
    assert "raw_eeg_root" in stage_ids
    assert "reviewed_contract_source" in stage_ids
    assert "reviewed_contract_materialized" in stage_ids
    assert "eeg_reader_preflight" in stage_ids
    assert "mne_extraction" in stage_ids
    assert "canonical_signal_blocks" in stage_ids
    assert "level_m_features" in stage_ids
    assert "level_t_features" in stage_ids
    assert "real_execution_gate" in stage_ids


# ---------------------------------------------------------------------------
# Test 7 — manual_required stages are correct
# ---------------------------------------------------------------------------

def test_manual_required_stages(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    stage_map = {s.stage_id: s for s in plan.stages}
    assert stage_map["metadata"].manual_required is True
    assert stage_map["raw_eeg_root"].manual_required is True
    assert stage_map["reviewed_contract_source"].manual_required is True
    assert stage_map["reviewed_contract_materialized"].manual_required is False
    assert stage_map["eeg_reader_preflight"].manual_required is False


# ---------------------------------------------------------------------------
# Test 8 — executes_real_data stages never safe_to_auto_run
# ---------------------------------------------------------------------------

def test_real_data_stages_never_safe_to_auto_run(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    for s in plan.stages:
        if s.executes_real_data:
            assert s.safe_to_auto_run is False, f"Stage {s.stage_id} should not be safe_to_auto_run"


# ---------------------------------------------------------------------------
# Test 9 — no stage downloads data
# ---------------------------------------------------------------------------

def test_no_stage_downloads_data(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    for s in plan.stages:
        assert s.downloads_data is False, f"Stage {s.stage_id} should not download data"


# ---------------------------------------------------------------------------
# Test 10 — guardrails hardcoded false
# ---------------------------------------------------------------------------

def test_guardrails_hardcoded_false(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    g = plan.guardrails
    assert g["executes_real_benchmark"] is False
    assert g["downloads_data"] is False
    assert g["executes_real_data_automatically"] is False
    assert g["auto_confirms_peer_review"] is False
    assert g["infers_labels"] is False
    assert g["fabricates_targets"] is False
    assert g["modifies_p18_3_gate"] is False


# ---------------------------------------------------------------------------
# Test 11 — metadata complete advances next_action
# ---------------------------------------------------------------------------

def test_next_action_advances_when_metadata_present(tmp_path):
    cfg = _default_cfg(tmp_path)
    Path(cfg.metadata_path).write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert plan.next_action == "provide_raw_eeg"


# ---------------------------------------------------------------------------
# Test 12 — metadata + raw_eeg complete advances further
# ---------------------------------------------------------------------------

def test_next_action_advances_past_raw_eeg(tmp_path):
    cfg = _default_cfg(tmp_path)
    Path(cfg.metadata_path).write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    Path(cfg.raw_eeg_root).mkdir(parents=True, exist_ok=True)
    (Path(cfg.raw_eeg_root) / "dummy.bdf").write_text("x", encoding="utf-8")
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert plan.next_action == "prepare_reviewed_contract_declaration"


# ---------------------------------------------------------------------------
# Test 13 — all pre-gate stages complete → next_action is run_real_execution_gate
# ---------------------------------------------------------------------------

def test_next_action_is_run_real_execution_gate_when_pre_gate_complete(tmp_path):
    cfg = _default_cfg(tmp_path)
    # Seed everything except the gate
    Path(cfg.metadata_path).write_text("onset\n", encoding="utf-8")
    Path(cfg.raw_eeg_root).mkdir(parents=True, exist_ok=True)
    (Path(cfg.raw_eeg_root) / "dummy.bdf").write_text("x", encoding="utf-8")
    Path(cfg.reviewed_contract_source).write_text("{}", encoding="utf-8")
    Path(cfg.reviewed_contract_materialized).write_text("{}", encoding="utf-8")
    Path(cfg.reader_preflight_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.reader_preflight_path) / "p.json").write_text("{}", encoding="utf-8")
    Path(cfg.mne_extract_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.mne_extract_path) / "inv.json").write_text("{}", encoding="utf-8")
    Path(cfg.signal_blocks_path).mkdir(parents=True, exist_ok=True)
    (Path(cfg.signal_blocks_path) / "inv.json").write_text("{}", encoding="utf-8")
    Path(cfg.level_m_csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.level_m_csv_path).write_text("col\n", encoding="utf-8")
    Path(cfg.level_t_csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.level_t_csv_path).write_text("col\n", encoding="utf-8")
    # gate file not present
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert plan.next_action == "run_real_execution_gate"
    assert plan.ready_for_real_execution_gate is True


# ---------------------------------------------------------------------------
# Test 14 — all stages complete → next_action is human_peer_review_required
# ---------------------------------------------------------------------------

def test_next_action_human_peer_review_when_all_complete(tmp_path):
    cfg = _default_cfg(tmp_path)
    _seed_all_artifacts(cfg)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert plan.all_stages_complete is True
    assert plan.next_action == "human_peer_review_required"
    assert plan.ready_for_manual_real_execution is True


# ---------------------------------------------------------------------------
# Test 15 — commands list has one entry per stage
# ---------------------------------------------------------------------------

def test_commands_list_has_one_per_stage(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    assert len(plan.commands) == len(plan.stages)


# ---------------------------------------------------------------------------
# Test 16 — no command has safe_to_auto_run=True
# ---------------------------------------------------------------------------

def test_no_command_is_safe_to_auto_run(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    for cmd in plan.commands:
        assert cmd.safe_to_auto_run is False, f"Command {cmd.stage_id} should not be safe_to_auto_run"


# ---------------------------------------------------------------------------
# Test 17 — write_outputs creates all 6 files
# ---------------------------------------------------------------------------

def test_write_outputs_creates_six_files(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    out_dir = tmp_path / "operator_out"
    paths = write_ds005620_real_artifact_operator_outputs(plan, str(out_dir))
    assert len(paths) == 6
    expected = {
        "real_artifact_build_plan.json",
        "real_artifact_stage_status.json",
        "real_artifact_next_command.json",
        "real_artifact_required_paths.json",
        "real_artifact_commands.sh",
        "real_artifact_operator_report.md",
    }
    assert set(paths.keys()) == expected
    for name, path in paths.items():
        assert Path(path).exists(), f"{name} not written at {path}"


# ---------------------------------------------------------------------------
# Test 18 — build_plan.json contains required fields
# ---------------------------------------------------------------------------

def test_build_plan_json_has_required_fields(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    out_dir = tmp_path / "operator_out"
    write_ds005620_real_artifact_operator_outputs(plan, str(out_dir))
    data = json.loads((out_dir / "real_artifact_build_plan.json").read_text())
    assert "dataset_id" in data
    assert "planner_version" in data
    assert "all_stages_complete" in data
    assert "ready_for_real_execution_gate" in data
    assert "ready_for_manual_real_execution" in data
    assert "next_action" in data
    assert "next_command" in data
    assert "stages" in data
    assert "commands" in data
    assert "guardrails" in data
    assert "safe_claim" in data


# ---------------------------------------------------------------------------
# Test 19 — commands.sh does not auto-execute real data commands
# ---------------------------------------------------------------------------

def test_commands_sh_real_data_commands_are_commented_out(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    out_dir = tmp_path / "operator_out"
    write_ds005620_real_artifact_operator_outputs(plan, str(out_dir))
    sh = (out_dir / "real_artifact_commands.sh").read_text()
    # All real-data commands should be prefixed with "# "
    for line in sh.splitlines():
        stripped = line.strip()
        if stripped.startswith("python") and ("extract_mne" in stripped or "level_m" in stripped or "level_t" in stripped):
            pytest.fail(f"Real-data command is NOT commented out in commands.sh: {line!r}")


# ---------------------------------------------------------------------------
# Test 20 — operator report.md contains no forbidden phrases
# ---------------------------------------------------------------------------

def test_operator_report_md_has_no_forbidden_phrases(tmp_path):
    cfg = _default_cfg(tmp_path)
    plan = build_ds005620_real_artifact_build_plan(cfg)
    out_dir = tmp_path / "operator_out"
    write_ds005620_real_artifact_operator_outputs(plan, str(out_dir))
    md = (out_dir / "real_artifact_operator_report.md").read_text().lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in md, f"Forbidden phrase in report: {phrase!r}"


# ---------------------------------------------------------------------------
# Test 21 — safe_claim does not contain forbidden phrases
# ---------------------------------------------------------------------------

def test_safe_claim_has_no_forbidden_phrases():
    lower = _SAFE_CLAIM.lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in lower, f"Forbidden phrase in safe_claim: {phrase!r}"


# ---------------------------------------------------------------------------
# Test 22 — CLI exits 0 when artifacts are absent (planner still runs)
# ---------------------------------------------------------------------------

def test_cli_exits_0_when_no_artifacts(tmp_path):
    result = subprocess.run(
        [
            sys.executable, "-m",
            "sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts",
            "--out", str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"


# ---------------------------------------------------------------------------
# Test 23 — CLI --strict exits nonzero when stages missing
# ---------------------------------------------------------------------------

def test_cli_strict_exits_nonzero_when_stages_missing(tmp_path):
    result = subprocess.run(
        [
            sys.executable, "-m",
            "sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts",
            "--out", str(tmp_path / "out"),
            "--strict",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Test 24 — CLI --json produces valid JSON summary
# ---------------------------------------------------------------------------

def test_cli_json_produces_valid_summary(tmp_path):
    result = subprocess.run(
        [
            sys.executable, "-m",
            "sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts",
            "--out", str(tmp_path / "out"),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # stdout has file list lines + JSON — find the JSON block
    stdout = result.stdout
    # JSON starts with "{"
    json_start = stdout.find("{")
    assert json_start != -1, "No JSON in stdout"
    data = json.loads(stdout[json_start:])
    assert "dataset_id" in data
    assert "all_stages_complete" in data
    assert "next_action" in data
    assert "guardrails" in data


# ---------------------------------------------------------------------------
# Test 25 — Makefile has ds005620-real-artifact-plan target (no auto-execute)
# ---------------------------------------------------------------------------

def test_makefile_has_artifact_plan_target():
    makefile = Path("Makefile")
    if not makefile.exists():
        pytest.skip("Makefile not found")
    content = makefile.read_text()
    assert "ds005620-real-artifact-plan" in content


# ---------------------------------------------------------------------------
# Test 26 — Makefile has ds005620-real-readiness-loop target
# ---------------------------------------------------------------------------

def test_makefile_has_readiness_loop_target():
    makefile = Path("Makefile")
    if not makefile.exists():
        pytest.skip("Makefile not found")
    content = makefile.read_text()
    assert "ds005620-real-readiness-loop" in content


# ---------------------------------------------------------------------------
# Test 27 — config JSON has correct guardrails
# ---------------------------------------------------------------------------

def test_config_json_has_correct_guardrails():
    cfg_path = Path("configs/btc_icft/ds005620_real_artifact_operator.json")
    if not cfg_path.exists():
        pytest.skip("Config JSON not found")
    data = json.loads(cfg_path.read_text())
    assert data["dry_run_only"] is True
    assert data["executes_real_benchmark"] is False
    assert data["downloads_data"] is False
    g = data["guardrails"]
    assert g["executes_real_benchmark"] is False
    assert g["downloads_data"] is False
    assert g["auto_confirms_peer_review"] is False
    assert g["infers_labels"] is False
    assert g["fabricates_targets"] is False


# ---------------------------------------------------------------------------
# Test 28 — task inventory has ds005620_real_artifact_plan
# ---------------------------------------------------------------------------

def test_task_inventory_has_real_artifact_plan():
    from sciencer_d.btc_icft.runtime.task_inventory import build_default_science_task_registry
    registry = build_default_science_task_registry()
    task = registry.get("ds005620_real_artifact_plan")
    assert task is not None
    assert "plan_ds005620_real_artifacts" in task.module
