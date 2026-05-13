"""Tests for P18.1 — DS005620 guarded real benchmark executor.

27 tests cover:
  - dry-run, execute-without-peer-review, executor blockers
  - prerequisite inspection per stage
  - fake-runner happy path
  - failure propagation
  - --stop-after / --continue-on-stage-failure
  - stdio preview bounds
  - omega invariants
  - banned-phrase rejection
  - mock fixtures
  - CLI dry-run / CLI mock-e2e
  - validator pass/fail
  - P11 consumes P13 labeled features
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.p18.ds005620_e2e_fixtures import (
    _STRICT_JOIN_KEYS,
    build_ds005620_mock_e2e_fixtures,
)
from sciencer_d.btc_icft.p18.ds005620_real_benchmark_executor import (
    _BANNED_PHRASES,
    _STDIO_PREVIEW_LIMIT,
    DS005620ExecutionPaths,
    DS005620StagePlan,
    build_execution_paths,
    build_stage_plan,
    inspect_stage_prerequisites,
    run_ds005620_real_benchmark_execution,
    run_stage,
    validate_safe_text,
    write_ds005620_real_benchmark_outputs,
)

_P18_1_ARTIFACTS = [
    "ds005620_real_benchmark_execution.json",
    "stage_execution_plan.json",
    "stage_results.json",
    "execution_blockers.json",
    "omega_event.json",
    "report.md",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paths(tmp_path: Path, with_fixtures: bool = False) -> DS005620ExecutionPaths:
    artifact_root = tmp_path / "p18_1_out"
    artifact_root.mkdir(parents=True, exist_ok=True)
    if with_fixtures:
        fx = build_ds005620_mock_e2e_fixtures(str(tmp_path / "fixtures"))
        return build_execution_paths(
            artifact_root=str(artifact_root),
            reviewed_contract=fx.reviewed_contract,
            metadata=fx.metadata,
            signal_blocks=fx.signal_blocks,
            level_m=fx.level_m,
            level_t=fx.level_t,
        )
    return build_execution_paths(
        artifact_root=str(artifact_root),
        reviewed_contract=str(tmp_path / "missing_contract.json"),
        metadata=str(tmp_path / "missing_metadata.tsv"),
        signal_blocks=str(tmp_path / "missing_signal_blocks"),
        level_m=str(tmp_path / "missing_level_m"),
        level_t=str(tmp_path / "missing_level_t"),
    )


def _fake_runner_success(stage_outputs: dict[str, list[str]]):
    """Fake runner that materializes expected outputs and returns success."""
    def runner(cmd: list[str]) -> dict:
        # Identify stage by module name in command
        if "align_eeg_labels" in " ".join(cmd):
            for out in stage_outputs.get("P12", []):
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("dataset_id,row_id,y\nDS005620,r0,1\n", encoding="utf-8")
        elif "inject_eeg_targets" in " ".join(cmd):
            for out in stage_outputs.get("P13", []):
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("dataset_id,row_id,y\nDS005620,r0,1\n", encoding="utf-8")
        elif "run_eeg_signal_mt" in " ".join(cmd):
            for out in stage_outputs.get("P11", []):
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text('{"predictive_metrics_available": true}', encoding="utf-8")
        return {"returncode": 0, "stdout": "ok\n", "stderr": ""}
    return runner


def _fake_runner_fail_stage(failing_id: str):
    def runner(cmd: list[str]) -> dict:
        cmd_str = " ".join(cmd)
        if failing_id == "P12" and "align_eeg_labels" in cmd_str:
            return {"returncode": 1, "stdout": "", "stderr": "P12 failure"}
        if failing_id == "P13" and "inject_eeg_targets" in cmd_str:
            return {"returncode": 1, "stdout": "", "stderr": "P13 failure"}
        if failing_id == "P11" and "run_eeg_signal_mt" in cmd_str:
            return {"returncode": 2, "stdout": "", "stderr": "P11 failure"}
        return {"returncode": 0, "stdout": "ok", "stderr": ""}
    return runner


# ---------------------------------------------------------------------------
# 1. Dry-run / executor invariants
# ---------------------------------------------------------------------------

def test_dry_run_creates_all_six_p18_1_artifacts(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    result = run_ds005620_real_benchmark_execution(paths)
    out_dir = tmp_path / "out"
    write_ds005620_real_benchmark_outputs(result, str(out_dir))
    for name in _P18_1_ARTIFACTS:
        assert (out_dir / name).is_file(), f"missing {name}"


def test_dry_run_executes_no_stages(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    result = run_ds005620_real_benchmark_execution(paths)
    assert result.dry_run is True
    assert result.p12_executed is False
    assert result.p13_executed is False
    assert result.p11_executed is False
    assert result.benchmark_completed is False


def test_execute_without_peer_review_blocks(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    result = run_ds005620_real_benchmark_execution(paths, execute=True)
    assert result.dry_run is True
    assert any(
        "peer_reviewed_contract_confirmation" in b
        for b in result.execution_blockers
    )


def test_execute_with_peer_review_no_stage_can_run_in_dry_run_mode(tmp_path: Path):
    # No prerequisites supplied; even with peer review, stages must not have ready_to_run=True
    paths = _make_paths(tmp_path, with_fixtures=False)
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
    )
    # dry_run is False, but stage prerequisites are missing, so nothing executed
    assert result.dry_run is False
    assert result.p12_executed is False
    assert result.p13_executed is False
    assert result.p11_executed is False


# ---------------------------------------------------------------------------
# 2. Prerequisite inspection per stage
# ---------------------------------------------------------------------------

def test_missing_reviewed_contract_blocks_p12(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=False)
    plan = build_stage_plan(paths)
    blockers = inspect_stage_prerequisites(plan[0])
    assert any("missing" in b for b in blockers)


def test_missing_metadata_blocks_p12(tmp_path: Path):
    fx = build_ds005620_mock_e2e_fixtures(str(tmp_path / "fx"))
    paths = build_execution_paths(
        artifact_root=str(tmp_path / "out"),
        reviewed_contract=fx.reviewed_contract,
        metadata=str(tmp_path / "no_meta.tsv"),
        signal_blocks=fx.signal_blocks,
        level_m=fx.level_m,
        level_t=fx.level_t,
    )
    plan = build_stage_plan(paths)
    blockers = inspect_stage_prerequisites(plan[0])
    assert any("no_meta.tsv" in b for b in blockers)


def test_missing_level_m_features_blocks_p12(tmp_path: Path):
    fx = build_ds005620_mock_e2e_fixtures(str(tmp_path / "fx"))
    paths = build_execution_paths(
        artifact_root=str(tmp_path / "out"),
        reviewed_contract=fx.reviewed_contract,
        metadata=fx.metadata,
        signal_blocks=fx.signal_blocks,
        level_m=str(tmp_path / "no_level_m"),
        level_t=fx.level_t,
    )
    plan = build_stage_plan(paths)
    blockers = inspect_stage_prerequisites(plan[0])
    assert any("features_m_signal.csv" in b for b in blockers)


def test_missing_p12_label_alignment_blocks_p13(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    blockers = inspect_stage_prerequisites(plan[1])
    assert any("label_alignment.csv" in b for b in blockers)


def test_missing_p13_labeled_m_blocks_p11(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    blockers = inspect_stage_prerequisites(plan[2])
    assert any("features_m_signal_labeled.csv" in b for b in blockers)


# ---------------------------------------------------------------------------
# 3. Fake-runner happy path & failure propagation
# ---------------------------------------------------------------------------

def test_fake_runner_successful_path_executes_p12_p13_p11_in_order(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    stage_outputs = {
        "P12": plan[0].expected_outputs,
        "P13": plan[1].expected_outputs,
        "P11": plan[2].expected_outputs,
    }
    runner = _fake_runner_success(stage_outputs)
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True, runner=runner,
    )
    assert result.p12_executed is True
    assert result.p13_executed is True
    assert result.p11_executed is True
    assert result.benchmark_completed is True


def test_p12_failure_prevents_p13_and_p11(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    runner = _fake_runner_fail_stage("P12")
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True, runner=runner,
    )
    assert result.p12_succeeded is False
    assert result.p13_executed is False
    assert result.p11_executed is False
    assert result.benchmark_completed is False


def test_p13_failure_prevents_p11(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)

    def runner(cmd: list[str]) -> dict:
        if "align_eeg_labels" in " ".join(cmd):
            for out in plan[0].expected_outputs:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("ok", encoding="utf-8")
            return {"returncode": 0, "stdout": "", "stderr": ""}
        if "inject_eeg_targets" in " ".join(cmd):
            return {"returncode": 1, "stdout": "", "stderr": "P13 fail"}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True, runner=runner,
    )
    assert result.p12_succeeded is True
    assert result.p13_succeeded is False
    assert result.p11_executed is False
    assert result.benchmark_completed is False


def test_p11_failure_recorded(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)

    def runner(cmd: list[str]) -> dict:
        cs = " ".join(cmd)
        if "align_eeg_labels" in cs:
            for out in plan[0].expected_outputs:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("ok", encoding="utf-8")
            return {"returncode": 0, "stdout": "", "stderr": ""}
        if "inject_eeg_targets" in cs:
            for out in plan[1].expected_outputs:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("ok", encoding="utf-8")
            return {"returncode": 0, "stdout": "", "stderr": ""}
        return {"returncode": 7, "stdout": "", "stderr": "P11 explode"}

    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True, runner=runner,
    )
    assert result.p11_executed is True
    assert result.p11_succeeded is False
    p11_result = next(s for s in result.stages if s["stage_id"] == "P11")
    assert p11_result["exit_code"] == 7
    assert "P11 explode" in p11_result["stderr_preview"]


# ---------------------------------------------------------------------------
# 4. --stop-after and --continue-on-stage-failure
# ---------------------------------------------------------------------------

def test_stop_after_p12(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    runner = _fake_runner_success({
        "P12": plan[0].expected_outputs,
        "P13": plan[1].expected_outputs,
        "P11": plan[2].expected_outputs,
    })
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
        runner=runner, stop_after="p12",
    )
    assert result.p12_executed is True
    assert result.p13_executed is False
    assert result.p11_executed is False


def test_stop_after_p13(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    runner = _fake_runner_success({
        "P12": plan[0].expected_outputs,
        "P13": plan[1].expected_outputs,
        "P11": plan[2].expected_outputs,
    })
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
        runner=runner, stop_after="p13",
    )
    assert result.p12_executed is True
    assert result.p13_executed is True
    assert result.p11_executed is False


def test_continue_on_stage_failure_runs_downstream(tmp_path: Path):
    """When P12 fails AND --continue-on-stage-failure is set, P13/P11 attempt to run.

    They will be marked not-ready (P12 outputs absent), but the executor must
    not bail out at P12.
    """
    paths = _make_paths(tmp_path, with_fixtures=True)
    runner = _fake_runner_fail_stage("P12")

    result_default = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
        runner=runner, continue_on_stage_failure=False,
    )
    # Default: P13/P11 skipped due to upstream
    p13_default = next(s for s in result_default.stages if s["stage_id"] == "P13")
    assert p13_default["skipped"] is True

    result_continue = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
        runner=runner, continue_on_stage_failure=True,
    )
    # With continue: P13 is not "skipped_due_to_upstream_failure"; it may
    # instead skip due to prerequisite missing, which is the correct
    # downstream state.
    p13_cont = next(s for s in result_continue.stages if s["stage_id"] == "P13")
    assert "skipped_due_to_upstream_failure" not in (p13_cont.get("blockers") or [])


# ---------------------------------------------------------------------------
# 5. Stdio preview bounds
# ---------------------------------------------------------------------------

def test_stdio_previews_are_bounded(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    huge = "x" * (_STDIO_PREVIEW_LIMIT * 3)

    def runner(cmd: list[str]) -> dict:
        if "align_eeg_labels" in " ".join(cmd):
            for out in plan[0].expected_outputs:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("ok", encoding="utf-8")
        return {"returncode": 0, "stdout": huge, "stderr": huge}

    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True,
        runner=runner, stop_after="p12",
    )
    p12 = next(s for s in result.stages if s["stage_id"] == "P12")
    assert len(p12["stdout_preview"]) <= _STDIO_PREVIEW_LIMIT + 100
    assert len(p12["stderr_preview"]) <= _STDIO_PREVIEW_LIMIT + 100
    assert "truncated" in p12["stdout_preview"]


# ---------------------------------------------------------------------------
# 6. Omega invariants & banned phrases
# ---------------------------------------------------------------------------

def test_omega_invariants_always_safe(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    result = run_ds005620_real_benchmark_execution(paths)
    omega = result.omega_event
    for inv in [
        "labels_inferred", "targets_fabricated", "source_contracts_modified",
        "legacy_mt_real_modified", "contracts_activated_by_executor",
        "p11_promotion_gate_modified", "consciousness_claims_made",
    ]:
        assert omega.get(inv) is False, f"omega invariant {inv} must be False"


def test_banned_phrase_validator_rejects(tmp_path: Path):
    with pytest.raises(ValueError, match="Banned phrase"):
        validate_safe_text("This proves consciousness ultimately.")


# ---------------------------------------------------------------------------
# 7. Mock fixture builder
# ---------------------------------------------------------------------------

def test_mock_fixture_builder_creates_both_y_classes(tmp_path: Path):
    fx = build_ds005620_mock_e2e_fixtures(str(tmp_path / "fx"), n_windows=4)
    rows = list(csv.DictReader(open(fx.metadata, newline="", encoding="utf-8")))
    trial_types = {r["trial_type"] for r in rows}
    assert {"focus", "mind_wandering"}.issubset(trial_types)


def test_mock_e2e_stage_plan_has_all_required_paths(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    assert [s.stage_id for s in plan] == ["P12", "P13", "P11"]
    for stage in plan:
        for req in stage.requires:
            assert isinstance(req, str) and req


def test_mock_e2e_execute_completes_with_fake_runner(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    runner = _fake_runner_success({
        "P12": plan[0].expected_outputs,
        "P13": plan[1].expected_outputs,
        "P11": plan[2].expected_outputs,
    })
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=True, runner=runner,
    )
    assert result.benchmark_completed is True
    out_dir = Path(tmp_path) / "p18_out"
    write_ds005620_real_benchmark_outputs(result, str(out_dir))
    for name in _P18_1_ARTIFACTS:
        assert (out_dir / name).is_file()


# ---------------------------------------------------------------------------
# 8. CLI
# ---------------------------------------------------------------------------

def test_cli_dry_run_exits_0(tmp_path: Path):
    from sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark import main
    rc = main(["--out", str(tmp_path / "out")])
    assert rc == 0


def test_cli_mock_e2e_exits_0_and_writes_final_artifacts(tmp_path: Path):
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
         "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed",
         "--out", str(tmp_path / "mock_e2e")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    for name in _P18_1_ARTIFACTS:
        assert (tmp_path / "mock_e2e" / name).is_file()


# ---------------------------------------------------------------------------
# 9. Validator
# ---------------------------------------------------------------------------

def test_validator_passes_on_mock_e2e_outputs(tmp_path: Path):
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
         "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed",
         "--out", str(tmp_path / "mock_e2e")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py",
         "--root", str(tmp_path / "mock_e2e")],
        capture_output=True, text=True,
    )
    assert rv.returncode == 0, rv.stderr


def test_validator_fails_when_core_artifact_missing(tmp_path: Path):
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
         "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed",
         "--out", str(tmp_path / "mock_e2e")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    (tmp_path / "mock_e2e" / "report.md").unlink()
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py",
         "--root", str(tmp_path / "mock_e2e")],
        capture_output=True, text=True,
    )
    assert rv.returncode != 0


# ---------------------------------------------------------------------------
# 10. P11 consumes P13 labeled features
# ---------------------------------------------------------------------------

def test_p11_command_uses_p13_labeled_features_not_raw_level_m(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    p11 = plan[2]
    cmd_str = " ".join(p11.command)
    assert "features_m_signal_labeled.csv" in cmd_str
    # Must not pass the raw Level M features_m_signal.csv as --m-features
    # (the raw path would also contain "features_m_signal.csv" as a substring,
    # so check that --m-features argument is the labeled one).
    idx = p11.command.index("--m-features")
    m_features_path = p11.command[idx + 1]
    assert m_features_path.endswith("features_m_signal_labeled.csv")


# ---------------------------------------------------------------------------
# 11. No stage executes without peer-review confirmation in execute mode
# ---------------------------------------------------------------------------

def test_no_stage_executes_without_peer_review_even_with_runner(tmp_path: Path):
    paths = _make_paths(tmp_path, with_fixtures=True)
    plan = build_stage_plan(paths)
    runner = _fake_runner_success({
        "P12": plan[0].expected_outputs,
        "P13": plan[1].expected_outputs,
        "P11": plan[2].expected_outputs,
    })
    result = run_ds005620_real_benchmark_execution(
        paths, execute=True, peer_reviewed_contract_confirmed=False,
        runner=runner,
    )
    assert result.dry_run is True
    assert result.p12_executed is False
    assert result.p13_executed is False
    assert result.p11_executed is False


def test_cli_execute_without_peer_review_exits_nonzero(tmp_path: Path):
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--execute", "--out", str(tmp_path / "blocked")],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0


def test_cli_execute_without_peer_review_writes_core_artifacts(tmp_path: Path):
    out = tmp_path / "blocked"
    r = subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--execute", "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    for name in _P18_1_ARTIFACTS:
        assert (out / name).is_file(), name


def test_cli_execute_without_peer_review_does_not_execute_stages(tmp_path: Path):
    out = tmp_path / "blocked"
    subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--execute", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    summary = json.loads((out / "ds005620_real_benchmark_execution.json").read_text())
    blockers = json.loads((out / "execution_blockers.json").read_text())
    assert summary["p12_executed"] is False
    assert summary["p13_executed"] is False
    assert summary["p11_executed"] is False
    assert "execute_requested_without_peer_reviewed_contract_confirmation" in blockers["execution_blockers"]


def test_validator_json_out_writes_summary(tmp_path: Path):
    out = tmp_path / "mock_e2e"
    subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed", "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    json_out = out / "validation_summary.json"
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py", "--root", str(out), "--json-out", str(json_out)],
        capture_output=True,
        text=True,
    )
    assert rv.returncode == 0
    summary = json.loads(json_out.read_text())
    assert summary["ok"] is True
    assert "checked_artifacts" in summary


def test_validator_quiet_suppresses_pass_output(tmp_path: Path):
    out = tmp_path / "mock_e2e"
    subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed", "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py", "--root", str(out), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert rv.returncode == 0
    assert "PASS" not in rv.stdout


def test_validator_fails_cleanly_when_root_missing(tmp_path: Path):
    missing = tmp_path / "not_found"
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py", "--root", str(missing), "--json-out", str(tmp_path / "sum.json")],
        capture_output=True,
        text=True,
    )
    assert rv.returncode == 1


def test_validator_reports_p11_labeled_feature_check_in_json_failures(tmp_path: Path):
    out = tmp_path / "mock_e2e"
    subprocess.run(
        [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark", "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed", "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    stage_results_path = out / "stage_results.json"
    stage_results = json.loads(stage_results_path.read_text())
    for stage in stage_results.get("stages", []):
        if stage.get("stage_id") == "P11":
            stage["command"] = ["python", "-m", "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt", "--m-features", "features_m_signal.csv"]
    stage_results_path.write_text(json.dumps(stage_results, indent=2) + "\n", encoding="utf-8")

    json_out = out / "validation_summary.json"
    rv = subprocess.run(
        [sys.executable, "tools/validate_ds005620_e2e_execution.py", "--root", str(out), "--json-out", str(json_out), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert rv.returncode == 1
    summary = json.loads(json_out.read_text())
    assert any("P11 command must consume the P13 features_m_signal_labeled.csv" in f for f in summary["failures"])
