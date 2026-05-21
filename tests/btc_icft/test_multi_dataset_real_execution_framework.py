"""
Tests for P22: Multi-dataset real-execution framework.

No real datasets are required. Tests use tmp_path fixtures and the in-repo
source manifest. No Makefile targets are executed inside tests.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.runtime.multi_dataset_paths import (
    DatasetProfile,
    DatasetRealPathConfig,
    build_dataset_output_roots,
    build_dataset_path_config,
    load_multi_dataset_source_manifest,
)
from sciencer_d.btc_icft.runtime.generic_real_artifact_operator import (
    build_generic_real_artifact_plan,
)
from sciencer_d.btc_icft.runtime.generic_real_execution_gate import (
    build_generic_real_execution_gate,
)
from sciencer_d.btc_icft.runtime.multi_dataset_real_execution_matrix import (
    build_multi_dataset_matrix,
    write_matrix_outputs,
)
from sciencer_d.btc_icft.runtime.multi_dataset_autonomous_iteration import (
    run_multi_dataset_autonomous_iteration,
)


PLANNED_DATASETS = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]

BANNED_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality",
]


def _profile(ds_id: str):
    return next(
        p for p in load_multi_dataset_source_manifest() if p.dataset_id == ds_id
    )


# ---------------------------------------------------------------------------
# Test 1 — source manifest contains all six datasets
# ---------------------------------------------------------------------------

def test_source_manifest_contains_all_six_datasets():
    profiles = load_multi_dataset_source_manifest()
    ids = [p.dataset_id for p in profiles]
    for ds in PLANNED_DATASETS:
        assert ds in ids, f"Missing dataset {ds} in manifest"


# ---------------------------------------------------------------------------
# Test 2 — path config supports all six datasets
# ---------------------------------------------------------------------------

def test_path_config_supports_all_six_datasets():
    profiles = load_multi_dataset_source_manifest()
    for p in profiles:
        cfg = build_dataset_path_config(p)
        assert isinstance(cfg, DatasetRealPathConfig)
        assert cfg.dataset_id == p.dataset_id


# ---------------------------------------------------------------------------
# Test 3 — DS005620 preserves legacy output paths
# ---------------------------------------------------------------------------

def test_ds005620_preserves_legacy_output_paths():
    cfg = build_dataset_path_config(_profile("DS005620"))
    assert cfg.metadata_path == "data/DS005620/events.tsv"
    assert "ds005620_reviewed_contract" in cfg.reviewed_contract_materialized
    assert "eeg_mne_extract/DS005620" in cfg.mne_extract_path
    assert "ds005620_real_execution_gate" in cfg.real_execution_gate_path
    roots = build_dataset_output_roots("DS005620")
    assert roots.artifact_operator_root == "outputs/btc_icft/ds005620_real_artifact_operator"
    assert roots.autonomous_iteration_root == "outputs/btc_icft/ds005620_autonomous_iteration"


# ---------------------------------------------------------------------------
# Test 4 — non-DS005620 uses generic output paths
# ---------------------------------------------------------------------------

def test_non_ds005620_uses_generic_paths():
    cfg = build_dataset_path_config(_profile("ds001787"))
    assert "outputs/btc_icft/ds001787/" in cfg.reviewed_contract_materialized
    assert "outputs/btc_icft/ds001787/" in cfg.real_execution_gate_path


# ---------------------------------------------------------------------------
# Test 5 — local availability missing root marks missing_local_root
# ---------------------------------------------------------------------------

def test_missing_local_root_marks_missing_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = _profile("ds001787")  # path will not exist under tmp_path
    matrix = build_multi_dataset_matrix([profile])
    assert matrix.datasets["ds001787"]["local_data"]["readiness_status"] == "missing_local_root"


# ---------------------------------------------------------------------------
# Test 6 — metadata-only fixture marks metadata_present_no_raw_eeg
# ---------------------------------------------------------------------------

def test_metadata_only_marks_metadata_present_no_raw_eeg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create data/ds001787/events.tsv only
    ds_dir = tmp_path / "data" / "ds001787"
    ds_dir.mkdir(parents=True)
    (ds_dir / "events.tsv").write_text("onset\tduration\ttrial_type\n0\t1\tx\n")
    profile = _profile("ds001787")
    matrix = build_multi_dataset_matrix([profile])
    status = matrix.datasets["ds001787"]["local_data"]["readiness_status"]
    assert status == "metadata_present_no_raw_eeg"


# ---------------------------------------------------------------------------
# Test 7 — raw-only fixture marks raw_eeg_present_no_metadata
# ---------------------------------------------------------------------------

def test_raw_only_marks_raw_eeg_present_no_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ds_dir = tmp_path / "data" / "ds001787"
    ds_dir.mkdir(parents=True)
    (ds_dir / "sub-01.edf").write_text("fake binary")
    profile = _profile("ds001787")
    matrix = build_multi_dataset_matrix([profile])
    status = matrix.datasets["ds001787"]["local_data"]["readiness_status"]
    assert status == "raw_eeg_present_no_metadata"


# ---------------------------------------------------------------------------
# Test 8 — metadata + raw fixture marks local_data_present
# ---------------------------------------------------------------------------

def test_metadata_plus_raw_marks_local_data_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ds_dir = tmp_path / "data" / "ds001787"
    ds_dir.mkdir(parents=True)
    (ds_dir / "events.tsv").write_text("onset\tduration\ttrial_type\n0\t1\tx\n")
    (ds_dir / "sub-01.edf").write_text("fake binary")
    profile = _profile("ds001787")
    matrix = build_multi_dataset_matrix([profile])
    status = matrix.datasets["ds001787"]["local_data"]["readiness_status"]
    assert status == "local_data_present"


# ---------------------------------------------------------------------------
# Test 9 — label readiness never infers positive/negative mapping
# ---------------------------------------------------------------------------

def test_label_readiness_never_infers_positive_negative_mapping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Even with materialized contract, no inference should happen
    ds_dir = tmp_path / "data" / "ds001787"
    ds_dir.mkdir(parents=True)
    (ds_dir / "events.tsv").write_text("onset\tduration\ttrial_type\n0\t1\tA\n1\t1\tB\n")
    profile = _profile("ds001787")
    matrix = build_multi_dataset_matrix([profile])
    lc = matrix.datasets["ds001787"]["label_contract"]
    # No materialized contract → not active
    assert lc["readiness_status"] != "contract_active"


# ---------------------------------------------------------------------------
# Test 10 — generic artifact operator writes stages for all datasets
# ---------------------------------------------------------------------------

def test_generic_operator_produces_eleven_stages_for_every_dataset():
    for ds in PLANNED_DATASETS:
        plan = build_generic_real_artifact_plan(_profile(ds))
        assert len(plan.stages) == 11, f"{ds} has {len(plan.stages)} stages"


# ---------------------------------------------------------------------------
# Test 11 — generic operator marks real-data stages manual or blocked
# ---------------------------------------------------------------------------

def test_non_ds005620_real_data_stages_blocked():
    plan = build_generic_real_artifact_plan(_profile("ds001787"))
    stage_map = {s.stage_id: s for s in plan.stages}
    for sid in ("mne_extraction", "canonical_signal_blocks", "level_m_features", "level_t_features"):
        assert stage_map[sid].status == "blocked_dataset_specific_support_required"
    # reviewed_contract is blocked too for non-DS005620
    assert stage_map["reviewed_contract"].status == "blocked_dataset_specific_support_required"


# ---------------------------------------------------------------------------
# Test 12 — generic gate keeps peer_review_confirmed_by_human=false
# ---------------------------------------------------------------------------

def test_generic_gate_peer_review_always_false():
    for ds in PLANNED_DATASETS:
        g = build_generic_real_execution_gate(_profile(ds))
        assert g.peer_review_confirmed_by_human is False
        assert g.peer_review_required is True


# ---------------------------------------------------------------------------
# Test 13 — generic gate keeps can_use_execute_flag=false
# ---------------------------------------------------------------------------

def test_generic_gate_can_use_execute_flag_always_false():
    for ds in PLANNED_DATASETS:
        g = build_generic_real_execution_gate(_profile(ds))
        assert g.can_use_execute_flag is False
        assert g.can_use_peer_reviewed_contract_confirmed_flag is False


# ---------------------------------------------------------------------------
# Test 14 — generic gate marks non-DS005620 executor unavailable
# ---------------------------------------------------------------------------

def test_non_ds005620_executor_unavailable():
    for ds in PLANNED_DATASETS:
        if ds == "DS005620":
            continue
        g = build_generic_real_execution_gate(_profile(ds))
        assert g.dataset_specific_executor_available is False
        assert g.ready_for_real_execution is False


def test_ds005620_executor_is_marked_available():
    g = build_generic_real_execution_gate(_profile("DS005620"))
    assert g.dataset_specific_executor_available is True


# ---------------------------------------------------------------------------
# Test 15 — matrix writes all expected outputs
# ---------------------------------------------------------------------------

def test_matrix_writes_all_outputs(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    paths = write_matrix_outputs(matrix, str(tmp_path))
    expected = {
        "dataset_source_matrix.json",
        "local_data_availability_matrix.json",
        "label_contract_readiness_matrix.json",
        "eeg_reader_readiness_matrix.json",
        "artifact_operator_matrix.json",
        "real_execution_gate_matrix.json",
        "autonomous_iteration_matrix.json",
        "empirical_readiness_matrix.json",
        "ontology_scope_matrix.json",
        "next_actions.json",
        "operator_report.md",
    }
    assert set(paths.keys()) == expected
    for name in expected:
        assert (tmp_path / name).exists()


# ---------------------------------------------------------------------------
# Test 16 — matrix includes all six datasets
# ---------------------------------------------------------------------------

def test_matrix_includes_all_six_datasets():
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    assert set(matrix.datasets.keys()) == set(PLANNED_DATASETS)


# ---------------------------------------------------------------------------
# Test 17 — matrix empirical readiness remains blocked without controls
# ---------------------------------------------------------------------------

def test_empirical_readiness_blocked_without_controls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    for ds, d in matrix.datasets.items():
        emp = d["empirical_readiness"]
        assert emp["empirical_claims_permitted"] is False
        assert emp["readiness_status"] in (
            "blocked_no_real_execution", "blocked_missing_controls"
        )


# ---------------------------------------------------------------------------
# Test 18 — matrix ontology scope remains quarantined
# ---------------------------------------------------------------------------

def test_ontology_scope_always_quarantined():
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    for ds, d in matrix.datasets.items():
        ont = d["ontology_scope"]
        assert ont["ontology_quarantined"] is True
        assert ont["claim_scope_cap"] == "engineering_runtime"
        assert ont["promotion_state"] == "engineering_validated"


# ---------------------------------------------------------------------------
# Test 19 — multi-dataset autonomous dry-run writes all outputs
# ---------------------------------------------------------------------------

def test_multi_dataset_dry_run_writes_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "iter_out"
    matrix_dir = tmp_path / "matrix_out"
    result = run_multi_dataset_autonomous_iteration(
        out_dir=str(out_dir),
        matrix_out_dir=str(matrix_dir),
        cwd=str(tmp_path),
        dry_run=True,
    )
    expected = {
        "iteration_state.json", "iteration_plan.json", "iteration_results.json",
        "iteration_decision_log.json", "iteration_next_actions.json",
        "iteration_artifact_index.json", "iteration_report.md",
        "iteration_events.jsonl",
    }
    assert set(result.output_paths.keys()) == expected
    for name in expected:
        assert (out_dir / name).exists()


# ---------------------------------------------------------------------------
# Test 20 — multi-dataset iteration does not execute real commands
# ---------------------------------------------------------------------------

def test_iteration_never_runs_real_data_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_multi_dataset_autonomous_iteration(
        out_dir=str(tmp_path / "out"),
        matrix_out_dir=str(tmp_path / "mout"),
        cwd=str(tmp_path),
        dry_run=False,
    )
    # All manual_real_execution steps stay manual_required, never succeeded
    for r in result.step_results:
        if r.step_id.endswith("__manual_real_execution"):
            assert r.status == "manual_required"
    # No step has executes_real_data=True with status=succeeded
    plan_steps = {s.step_id: s for s in result.plan.steps}
    for r in result.step_results:
        step = plan_steps[r.step_id]
        if step.executes_real_data and r.status == "succeeded":
            pytest.fail(f"Real-data step {r.step_id} was executed")


# ---------------------------------------------------------------------------
# Test 21 — generated commands do not include download commands
# ---------------------------------------------------------------------------

def test_generated_commands_no_download_substrings(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    write_matrix_outputs(matrix, str(tmp_path))
    na = json.loads((tmp_path / "next_actions.json").read_text())
    for ds, action in na["per_dataset"].items():
        cmd = action["next_command"].lower()
        for forbidden in ("dandi download", "openneuro download", " wget ", " curl ", "aws s3 cp"):
            assert forbidden not in cmd, f"{ds} command contains {forbidden!r}"


# ---------------------------------------------------------------------------
# Test 22 — generated commands do not auto-run --execute --peer-reviewed
# ---------------------------------------------------------------------------

def test_generated_commands_no_auto_execute(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    write_matrix_outputs(matrix, str(tmp_path))
    na = json.loads((tmp_path / "next_actions.json").read_text())
    for ds, action in na["per_dataset"].items():
        cmd = action["next_command"]
        # Must not be an auto-runnable execute command
        if "--execute" in cmd and "--peer-reviewed-contract-confirmed" in cmd:
            # Only acceptable if it's clearly a manual command (starts with #)
            assert cmd.strip().startswith("#"), (
                f"{ds} command auto-runs execute flag: {cmd!r}"
            )


# ---------------------------------------------------------------------------
# Test 23 — report.md avoids banned phrases
# ---------------------------------------------------------------------------

def test_report_md_no_banned_phrases(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    write_matrix_outputs(matrix, str(tmp_path))
    report = (tmp_path / "operator_report.md").read_text().lower()
    for phrase in BANNED_PHRASES:
        assert phrase not in report


# ---------------------------------------------------------------------------
# Test 24 — validator passes on default no-real-data matrix
# ---------------------------------------------------------------------------

def test_validator_passes_on_default_matrix(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    write_matrix_outputs(matrix, str(tmp_path))
    r = subprocess.run(
        [sys.executable, "tools/validate_multi_dataset_real_execution_matrix.py",
         "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"Validator failed: {r.stderr}"


# ---------------------------------------------------------------------------
# Test 25 — validator fails on fixture with fake empirical readiness
# ---------------------------------------------------------------------------

def test_validator_fails_on_fake_empirical_readiness(tmp_path):
    profiles = load_multi_dataset_source_manifest()
    matrix = build_multi_dataset_matrix(profiles)
    paths = write_matrix_outputs(matrix, str(tmp_path))
    # Corrupt empirical_readiness_matrix.json to claim ready without execution
    emp_path = tmp_path / "empirical_readiness_matrix.json"
    emp = json.loads(emp_path.read_text())
    ds_first = list(emp["datasets"].keys())[0]
    emp["datasets"][ds_first]["empirical_claims_permitted"] = True
    emp_path.write_text(json.dumps(emp, indent=2))
    r = subprocess.run(
        [sys.executable, "tools/validate_multi_dataset_real_execution_matrix.py",
         "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


# ---------------------------------------------------------------------------
# Test 26 — Makefile contains real-data-source-matrix
# ---------------------------------------------------------------------------

def test_makefile_has_real_data_source_matrix():
    mf = Path("Makefile")
    if not mf.exists():
        pytest.skip("Makefile not found")
    content = mf.read_text()
    assert "real-data-source-matrix:" in content


def test_makefile_has_multi_dataset_real_readiness():
    content = Path("Makefile").read_text()
    assert "multi-dataset-real-readiness:" in content


def test_makefile_has_multi_dataset_autonomous_iteration():
    content = Path("Makefile").read_text()
    assert "multi-dataset-autonomous-iteration:" in content


def test_makefile_has_multi_dataset_autonomous_iteration_dry_run():
    content = Path("Makefile").read_text()
    assert "multi-dataset-autonomous-iteration-dry-run:" in content


def test_makefile_has_validate_real_data_source_matrix():
    content = Path("Makefile").read_text()
    assert "validate-real-data-source-matrix:" in content


# ---------------------------------------------------------------------------
# Test 30 — task inventory includes multi-dataset tasks
# ---------------------------------------------------------------------------

def test_task_inventory_has_multi_dataset_tasks():
    from sciencer_d.btc_icft.runtime.task_inventory import (
        build_default_science_task_registry,
    )
    reg = build_default_science_task_registry()
    assert reg.get("multi_dataset_real_execution_matrix") is not None
    assert reg.get("multi_dataset_autonomous_iteration") is not None


# ---------------------------------------------------------------------------
# Test 31 — DS005620 autonomous iteration tests still pass (legacy paths)
# ---------------------------------------------------------------------------

def test_ds005620_legacy_targets_still_work():
    """Smoke-test that DS005620-specific runtime still imports cleanly."""
    from sciencer_d.btc_icft.runtime.ds005620_autonomous_iteration import (
        build_default_iteration_plan,
    )
    plan = build_default_iteration_plan()
    # Legacy P21 uses lowercase ID; P22 multi-dataset uses canonical "DS005620"
    assert plan.dataset_id.lower() == "ds005620"


# ---------------------------------------------------------------------------
# Test 32 — config manifest is valid JSON
# ---------------------------------------------------------------------------

def test_config_manifest_is_valid_json():
    cfg = Path("configs/btc_icft/multi_dataset_real_sources.json")
    assert cfg.exists()
    data = json.loads(cfg.read_text())
    assert "datasets" in data
    assert len(data["datasets"]) == 6


# ---------------------------------------------------------------------------
# Test 33 — iteration events.jsonl is written
# ---------------------------------------------------------------------------

def test_iteration_events_jsonl_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_multi_dataset_autonomous_iteration(
        out_dir=str(tmp_path / "out"),
        matrix_out_dir=str(tmp_path / "mout"),
        cwd=str(tmp_path),
        dry_run=True,
    )
    events_path = Path(result.output_paths["iteration_events.jsonl"])
    assert events_path.exists()


# ---------------------------------------------------------------------------
# Test 34 — manifest forbids automatic activation for all datasets
# ---------------------------------------------------------------------------

def test_manifest_guardrails_present_for_all_datasets():
    profiles = load_multi_dataset_source_manifest()
    for p in profiles:
        assert "no_data_download" in p.guardrails
        assert "no_label_inference" in p.guardrails
        assert "no_target_fabrication" in p.guardrails
        assert "no_auto_real_execution" in p.guardrails
        assert "no_auto_peer_review_confirmation" in p.guardrails
