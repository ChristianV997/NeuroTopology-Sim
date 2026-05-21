"""Tests for DS005620 real/local execution gate (P18.3)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.p18.ds005620_real_local_execution_gate import (
    DS005620RealLocalPathConfig,
    build_default_real_local_path_config,
    build_real_local_execution_gate,
    inspect_reviewed_contract_static_gate,
    validate_gate_safe_text,
    write_real_local_execution_gate_outputs,
    _FORBIDDEN_PHRASES,
    _CHECKLIST_ITEMS,
    _STRICT_JOIN_KEYS,
)
from sciencer_d.btc_icft.runtime.task_inventory import build_default_science_task_registry
from sciencer_d.btc_icft.runtime.state import build_runtime_state

_PIPELINE_PATH = (
    Path(__file__).parent.parent.parent
    / "sciencer_d" / "btc_icft" / "pipelines"
    / "prepare_ds005620_real_local_execution.py"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("prepare_gate", _PIPELINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_cfg(tmp_path: Path, **overrides) -> DS005620RealLocalPathConfig:
    defaults = dict(
        dataset_id="DS005620",
        metadata=str(tmp_path / "events.tsv"),
        reviewed_contract=str(tmp_path / "p12_external_contract.json"),
        mne_extract=str(tmp_path / "mne_extract"),
        signal_blocks=str(tmp_path / "signal_blocks"),
        level_m=str(tmp_path / "features_m_signal.csv"),
        level_t=str(tmp_path / "features_t_signal.csv"),
        execution_root=str(tmp_path / "execution"),
    )
    defaults.update(overrides)
    return build_default_real_local_path_config(**defaults)


def _valid_contract(tmp_path: Path) -> Path:
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["anesthesia"],
        "negative_values": ["wakefulness"],
        "join_keys": list(_STRICT_JOIN_KEYS),
    }), encoding="utf-8")
    return p


def _seed_all_artifacts(tmp_path: Path) -> None:
    (tmp_path / "events.tsv").write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    _valid_contract(tmp_path)
    (tmp_path / "mne_extract").mkdir()
    (tmp_path / "signal_blocks").mkdir()
    (tmp_path / "features_m_signal.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "features_t_signal.csv").write_text("a,b\n1,2\n", encoding="utf-8")


# -----------------------------------------------------------------------
# 1. Missing all artifacts → ready_for_real_execution=false
# -----------------------------------------------------------------------
def test_missing_all_artifacts_not_ready(tmp_path):
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.ready_for_real_execution is False


# -----------------------------------------------------------------------
# 2. Missing metadata → next_action=provide_metadata
# -----------------------------------------------------------------------
def test_missing_metadata_next_action(tmp_path):
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "provide_metadata"


# -----------------------------------------------------------------------
# 3. Metadata present but contract missing → next_action=run_p17_1
# -----------------------------------------------------------------------
def test_metadata_present_contract_missing_next_action(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "run_p17_1_reviewed_contract_materializer"


# -----------------------------------------------------------------------
# 4. Invalid contract status blocks readiness
# -----------------------------------------------------------------------
def test_invalid_contract_status_blocks(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "draft",
        "explicit_label_column": "trial_type",
        "positive_values": ["anesthesia"],
        "negative_values": ["wakefulness"],
        "join_keys": list(_STRICT_JOIN_KEYS),
    }), encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert not result.reviewed_contract_static_gate_passed
    assert result.next_action == "fix_reviewed_contract"


# -----------------------------------------------------------------------
# 5. Overlapping positive/negative values blocks readiness
# -----------------------------------------------------------------------
def test_overlapping_values_blocks(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["anesthesia", "shared"],
        "negative_values": ["wakefulness", "shared"],
        "join_keys": list(_STRICT_JOIN_KEYS),
    }), encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert not result.reviewed_contract_static_gate_passed


# -----------------------------------------------------------------------
# 6. Missing explicit_label_column blocks readiness
# -----------------------------------------------------------------------
def test_missing_label_column_blocks(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "",
        "positive_values": ["anesthesia"],
        "negative_values": ["wakefulness"],
        "join_keys": list(_STRICT_JOIN_KEYS),
    }), encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert not result.reviewed_contract_static_gate_passed


# -----------------------------------------------------------------------
# 7. Missing strict join key blocks readiness
# -----------------------------------------------------------------------
def test_missing_join_key_blocks(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    incomplete_keys = [k for k in _STRICT_JOIN_KEYS if k != "window_id"]
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["anesthesia"],
        "negative_values": ["wakefulness"],
        "join_keys": incomplete_keys,
    }), encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert not result.reviewed_contract_static_gate_passed
    cg = inspect_reviewed_contract_static_gate(str(p))
    assert "window_id" in cg.join_keys_missing


# -----------------------------------------------------------------------
# 8. Contract present + valid, MNE missing → next_action=run_p19_1
# -----------------------------------------------------------------------
def test_contract_valid_mne_missing_next_action(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    _valid_contract(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "run_p19_1_mne_extraction"


# -----------------------------------------------------------------------
# 9. MNE present, signal blocks missing → next_action=run_p19_2
# -----------------------------------------------------------------------
def test_mne_present_signal_blocks_missing_next_action(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    _valid_contract(tmp_path)
    (tmp_path / "mne_extract").mkdir()
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "run_p19_2_signal_block_conversion"


# -----------------------------------------------------------------------
# 10. Signal blocks present, Level M missing → next_action=run_p9_level_m_signal
# -----------------------------------------------------------------------
def test_signal_blocks_present_level_m_missing_next_action(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    _valid_contract(tmp_path)
    (tmp_path / "mne_extract").mkdir()
    (tmp_path / "signal_blocks").mkdir()
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "run_p9_level_m_signal"


# -----------------------------------------------------------------------
# 11. Level M present, Level T missing → next_action=run_p10_level_t_signal
# -----------------------------------------------------------------------
def test_level_m_present_level_t_missing_next_action(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    _valid_contract(tmp_path)
    (tmp_path / "mne_extract").mkdir()
    (tmp_path / "signal_blocks").mkdir()
    (tmp_path / "features_m_signal.csv").write_text("a\n1\n", encoding="utf-8")
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.next_action == "run_p10_level_t_signal"


# -----------------------------------------------------------------------
# 12. All artifacts present and contract valid → all_required_artifacts_present=true
# -----------------------------------------------------------------------
def test_all_artifacts_present_all_required_true(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.all_required_artifacts_present is True
    assert result.reviewed_contract_static_gate_passed is True


# -----------------------------------------------------------------------
# 13. All artifacts present → peer_review_confirmed_by_human=false (always)
# -----------------------------------------------------------------------
def test_all_artifacts_peer_review_still_false(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.peer_review_confirmed_by_human is False


# -----------------------------------------------------------------------
# 14. All artifacts present → can_use_execute_flag=false (always)
# -----------------------------------------------------------------------
def test_all_artifacts_can_use_execute_flag_false(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.can_use_execute_flag is False


# -----------------------------------------------------------------------
# 15. All artifacts present → can_use_peer_reviewed_contract_confirmed_flag=false
# -----------------------------------------------------------------------
def test_all_artifacts_can_use_contract_flag_false(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    assert result.can_use_peer_reviewed_contract_confirmed_flag is False


# -----------------------------------------------------------------------
# 16. Command plan contains --execute and --peer-reviewed-contract-confirmed
#     but not_executed_by_gate=true
# -----------------------------------------------------------------------
def test_command_plan_has_execute_flags_but_not_run(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    plan = result.command_plan
    assert plan is not None
    assert "--execute" in plan.command_parts
    assert "--peer-reviewed-contract-confirmed" in plan.command_parts
    assert plan.not_executed_by_gate is True
    assert plan.requires_human_confirmation is True
    assert plan.can_run_now is False


# -----------------------------------------------------------------------
# 17. Human checklist JSON has all required items
# -----------------------------------------------------------------------
def test_checklist_json_has_required_items(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    paths = write_real_local_execution_gate_outputs(result, str(tmp_path / "out"))
    data = json.loads(Path(paths["human_peer_review_checklist.json"]).read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["checklist"]}
    for expected in ("C01", "C06", "C11", "C16", "C17", "C18"):
        assert expected in ids
    assert data["peer_review_required"] is True
    assert data["human_review_confirmed_by_gate"] is False


# -----------------------------------------------------------------------
# 18. Human checklist Markdown avoids banned phrases
# -----------------------------------------------------------------------
def test_checklist_md_avoids_banned_phrases(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    paths = write_real_local_execution_gate_outputs(result, str(tmp_path / "out"))
    text = Path(paths["human_peer_review_checklist.md"]).read_text(encoding="utf-8").lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in text, f"banned phrase found in checklist.md: {phrase!r}"


# -----------------------------------------------------------------------
# 19. report.md avoids banned phrases
# -----------------------------------------------------------------------
def test_report_md_avoids_banned_phrases(tmp_path):
    _seed_all_artifacts(tmp_path)
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    paths = write_real_local_execution_gate_outputs(result, str(tmp_path / "out"))
    text = Path(paths["report.md"]).read_text(encoding="utf-8").lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in text, f"banned phrase found in report.md: {phrase!r}"


# -----------------------------------------------------------------------
# 20. CLI writes all seven outputs
# -----------------------------------------------------------------------
def test_cli_writes_all_seven_outputs(tmp_path):
    mod = _load_cli()
    out_dir = str(tmp_path / "gate_out")
    rc = mod.main(["--out", out_dir])
    assert rc == 0
    expected = [
        "ready_for_real_execution.json",
        "real_execution_gate.json",
        "real_execution_command_plan.json",
        "human_peer_review_checklist.json",
        "human_peer_review_checklist.md",
        "missing_artifacts.json",
        "report.md",
    ]
    for name in expected:
        assert (Path(out_dir) / name).exists(), f"missing output: {name}"


# -----------------------------------------------------------------------
# 21. CLI exits 0 when artifacts are missing
# -----------------------------------------------------------------------
def test_cli_exits_0_when_artifacts_missing(tmp_path):
    mod = _load_cli()
    out_dir = str(tmp_path / "gate_out")
    rc = mod.main(["--out", out_dir])
    assert rc == 0


# -----------------------------------------------------------------------
# 22. missing_artifacts.json lists missing groups
# -----------------------------------------------------------------------
def test_missing_artifacts_json_lists_groups(tmp_path):
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    paths = write_real_local_execution_gate_outputs(result, str(tmp_path / "out"))
    data = json.loads(Path(paths["missing_artifacts.json"]).read_text(encoding="utf-8"))
    assert "missing_groups" in data
    assert "metadata" in data["missing_groups"]


# -----------------------------------------------------------------------
# 23. Config file exists and says executes_real_benchmark=false
# -----------------------------------------------------------------------
def test_config_file_exists_and_safe():
    cfg_path = Path("configs/btc_icft/ds005620_real_local_execution_gate.json")
    assert cfg_path.exists(), f"Config not found: {cfg_path}"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["executes_real_benchmark"] is False
    assert data["downloads_data"] is False
    assert data["peer_review_required"] is True
    assert data["dry_run_only"] is True


# -----------------------------------------------------------------------
# 24. Makefile contains ds005620-real-execution-gate
# -----------------------------------------------------------------------
def test_makefile_has_real_execution_gate_target():
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "ds005620-real-execution-gate" in makefile


# -----------------------------------------------------------------------
# 25. Makefile does NOT contain a target using --execute --peer-reviewed-contract-confirmed
#     outside of the task_inventory / comments
# -----------------------------------------------------------------------
def test_makefile_has_no_auto_execute_real_target():
    makefile = Path("Makefile").read_text(encoding="utf-8")
    # Walk line by line; a recipe using --execute + --peer-reviewed-contract-confirmed
    # is allowed ONLY when --mock-e2e is also present (mock E2E target).
    # A real (non-mock) auto-execute target is forbidden.
    for lineno, line in enumerate(makefile.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if (
            "--execute" in stripped
            and "--peer-reviewed-contract-confirmed" in stripped
            and "--mock-e2e" not in stripped
        ):
            pytest.fail(
                f"Makefile line {lineno} contains real execute flags without --mock-e2e: {line!r}"
            )


# -----------------------------------------------------------------------
# 26. Task inventory includes ds005620_real_execution_gate
# -----------------------------------------------------------------------
def test_task_inventory_includes_real_execution_gate():
    registry = build_default_science_task_registry()
    task = registry.get("ds005620_real_execution_gate")
    assert task is not None
    assert "prepare_ds005620_real_local_execution" in task.module


# -----------------------------------------------------------------------
# 27. Runtime next_action mentions real execution gate after paper skeleton
# -----------------------------------------------------------------------
def test_runtime_next_action_run_real_execution_gate(tmp_path):
    # Write mock execution so runtime sees completed mock e2e
    (tmp_path / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({
            "benchmark_completed": True,
            "p12_succeeded": True,
            "p13_succeeded": True,
            "p11_succeeded": True,
            "mode": "mock_e2e",
            "stages": [],
        }),
        encoding="utf-8",
    )
    # Write artifact manifest
    (tmp_path / "artifact_manifest.json").write_text(
        json.dumps({"artifact_count": 0, "artifacts": []}), encoding="utf-8"
    )
    # Write ontology eval
    ont = tmp_path / "ontology"
    ont.mkdir()
    (ont / "ontology_claim_evaluation.json").write_text(
        json.dumps({
            "max_claim_scope": "engineering_runtime",
            "promotion_state": "engineering_validated",
            "ontology_claim_status": "ontology_quarantined",
            "claims": [],
            "blockers": [],
            "safe_claim": "test",
        }),
        encoding="utf-8",
    )
    (ont / "ontology_promotion_decision.json").write_text(
        json.dumps({"ontology_promotion": False, "empirical_marker_promotion": False,
                    "empirical_topology_promotion": False, "mechanism_promotion": False,
                    "metaphysical_promotion": False}),
        encoding="utf-8",
    )
    (ont / "bridge_claim_status.json").write_text(
        json.dumps({"bridge_statuses": []}), encoding="utf-8"
    )
    # Write evidence + paper skeleton
    (tmp_path / "evidence_packet.json").write_text("{}", encoding="utf-8")
    (tmp_path / "paper_skeleton.md").write_text("# skeleton", encoding="utf-8")
    # Gate output does NOT exist yet
    state = build_runtime_state(
        "DS005620",
        str(tmp_path),
        ontology_root=str(ont),
        gate_dir=str(tmp_path / "nonexistent_gate"),
    )
    assert state.next_action == "run_real_execution_gate"


# -----------------------------------------------------------------------
# Additional: validate_gate_safe_text rejects banned phrases
# -----------------------------------------------------------------------
def test_validate_gate_safe_text_catches_violations():
    bad = "This eeg proves consciousness via topology."
    violations = validate_gate_safe_text(bad)
    assert "eeg proves consciousness" in violations


def test_validate_gate_safe_text_clean_text():
    clean = "Engineering validation only. No empirical claims."
    violations = validate_gate_safe_text(clean)
    assert violations == []


# -----------------------------------------------------------------------
# Additional: contract gate with shortcut indicator blocked
# -----------------------------------------------------------------------
def test_contract_shortcut_indicator_blocks(tmp_path):
    (tmp_path / "events.tsv").write_text("onset\n", encoding="utf-8")
    p = tmp_path / "p12_external_contract.json"
    p.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["anesthesia"],
        "negative_values": ["wakefulness"],
        "join_keys": list(_STRICT_JOIN_KEYS),
        "label_inference_enabled": True,
    }), encoding="utf-8")
    cg = inspect_reviewed_contract_static_gate(str(p))
    assert not cg.static_gate_passed
    assert any("label_inference_enabled" in b for b in cg.blockers)


# -----------------------------------------------------------------------
# Additional: ready_for_real_execution.json has all required fields
# -----------------------------------------------------------------------
def test_ready_for_real_execution_json_fields(tmp_path):
    cfg = _make_cfg(tmp_path)
    result = build_real_local_execution_gate(cfg)
    paths = write_real_local_execution_gate_outputs(result, str(tmp_path / "out"))
    data = json.loads(Path(paths["ready_for_real_execution.json"]).read_text(encoding="utf-8"))
    required_keys = {
        "dataset_id",
        "ready_for_real_execution",
        "ready_for_p18_1_execute",
        "reviewed_contract_static_gate_passed",
        "all_required_artifacts_present",
        "peer_review_required",
        "peer_review_confirmed_by_human",
        "can_use_execute_flag",
        "can_use_peer_reviewed_contract_confirmed_flag",
        "blockers",
        "warnings",
        "next_action",
        "next_command",
        "real_execution_command",
        "generated_at",
    }
    assert required_keys.issubset(set(data.keys()))
    assert data["peer_review_required"] is True
    assert data["peer_review_confirmed_by_human"] is False
    assert data["can_use_execute_flag"] is False
    assert data["can_use_peer_reviewed_contract_confirmed_flag"] is False
