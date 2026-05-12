"""Tests for P15 — target-aware activation smoke pipeline.

Most tests use a shared module-level fixture that runs the smoke pipeline once
into an isolated tmp directory.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Load pipeline module directly
_spec = importlib.util.spec_from_file_location(
    "run_target_aware_activation_smoke",
    "sciencer_d/btc_icft/pipelines/run_target_aware_activation_smoke.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

_build_stage_commands = _mod._build_stage_commands
_BANNED_PHRASES = _mod._BANNED_PHRASES
_SAFE_CLAIM = _mod._SAFE_CLAIM
_REAL_ACTIVATION_BLOCKED_MSG = _mod._REAL_ACTIVATION_BLOCKED_MSG

DATASET_ID = "DS005620"


# ---------------------------------------------------------------------------
# Shared smoke fixture (runs once per module)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def smoke_out(tmp_path_factory):
    """Run the P15 mock fixture smoke once and return output path."""
    root = str(tmp_path_factory.mktemp("btc_icft"))
    out = str(tmp_path_factory.mktemp("p15_out"))
    cp = subprocess.run(
        [
            sys.executable, "-m",
            "sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke",
            "--dataset-id", DATASET_ID,
            "--root", root,
            "--out", out,
            "--mock-fixture",
        ],
        capture_output=True,
        text=True,
    )
    return {
        "root": root,
        "out": out,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


# ---------------------------------------------------------------------------
# Test 1 — CLI --help works
# ---------------------------------------------------------------------------

class TestCli:
    def test_help_works(self):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke",
             "--help"],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0
        assert "mock-fixture" in cp.stdout.lower() or "dataset" in cp.stdout.lower()


# ---------------------------------------------------------------------------
# Test 2 — Without --mock-fixture exits nonzero
# ---------------------------------------------------------------------------

class TestNoMockFixtureBlocked:
    def test_without_mock_fixture_exits_nonzero(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke",
             "--dataset-id", DATASET_ID,
             "--root", str(tmp_path / "root"),
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert cp.returncode != 0

    def test_without_mock_fixture_prints_blocked_message(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke",
             "--dataset-id", DATASET_ID,
             "--root", str(tmp_path / "root"),
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert "mock activation" in cp.stderr.lower() or "blocked" in cp.stderr.lower() or \
               "real dataset" in cp.stderr.lower()


# ---------------------------------------------------------------------------
# Tests 3–22 — Full mock fixture run
# ---------------------------------------------------------------------------

class TestMockFixtureRun:
    def test_mock_fixture_exits_zero(self, smoke_out):
        assert smoke_out["returncode"] == 0, (
            f"P15 exited {smoke_out['returncode']}.\n"
            f"stdout: {smoke_out['stdout']}\nstderr: {smoke_out['stderr']}"
        )

    def test_writes_all_six_outputs(self, smoke_out):
        out = Path(smoke_out["out"])
        required = [
            "activation_smoke_summary.json",
            "activation_stage_results.json",
            "target_aware_metrics_snapshot.json",
            "activation_guardrail_report.json",
            "omega_event.json",
            "report.md",
        ]
        for name in required:
            assert (out / name).is_file(), f"Missing: {name}"

    def test_activation_smoke_summary_parses(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "activation_smoke_summary.json").read_text()
        )
        assert "dataset_id" in data
        assert "activation_smoke_passed" in data

    def test_activation_smoke_passed_is_true(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "activation_smoke_summary.json").read_text()
        )
        assert data["activation_smoke_passed"] is True

    def test_predictive_metrics_available_is_true(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "target_aware_metrics_snapshot.json").read_text()
        )
        assert data["predictive_metrics_available"] is True

    def test_explicit_targets_available_is_true(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "target_aware_metrics_snapshot.json").read_text()
        )
        assert data["explicit_targets_available"] is True

    def test_promotion_reason_key_present(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "target_aware_metrics_snapshot.json").read_text()
        )
        assert "promotion_reason" in data

    def test_promoted_not_forced_by_p15(self, smoke_out):
        # P15 must not hard-code promoted=True; it reads from P11 metrics
        src = Path(
            "sciencer_d/btc_icft/pipelines/run_target_aware_activation_smoke.py"
        ).read_text()
        assert '"promoted": True' not in src
        assert '"promoted": true' not in src
        # promoted in summary should come from metrics_snapshot, not fabricated
        summary = json.loads(
            (Path(smoke_out["out"]) / "activation_smoke_summary.json").read_text()
        )
        # promoted field is whatever P11 reported — may be True or False
        assert summary.get("promoted") in (True, False, None)

    def test_stage_results_include_p14_p12_p10_p13(self, smoke_out):
        results = json.loads(
            (Path(smoke_out["out"]) / "activation_stage_results.json").read_text()
        )
        stage_names = {r["stage"] for r in results}
        for expected in [
            "p14_adapter_readiness",
            "p12_explicit_label_alignment",
            "p10_level_t_signal_topology",
            "p13_target_injection",
        ]:
            assert expected in stage_names, f"Missing stage: {expected}"

    def test_p13_command_includes_mock_binary_targets(self, smoke_out):
        results = json.loads(
            (Path(smoke_out["out"]) / "activation_stage_results.json").read_text()
        )
        p13 = next(r for r in results if r["stage"] == "p13_target_injection")
        assert "--mock-binary-targets" in p13["command"]

    def test_p13_command_includes_run_p11_smoke(self, smoke_out):
        results = json.loads(
            (Path(smoke_out["out"]) / "activation_stage_results.json").read_text()
        )
        p13 = next(r for r in results if r["stage"] == "p13_target_injection")
        assert "--run-p11-smoke" in p13["command"]

    def test_target_aware_p11_output_dir_exists(self, smoke_out):
        p11_dir = (
            Path(smoke_out["root"]) / "eeg_signal_mt_targeted" / DATASET_ID
        )
        assert p11_dir.is_dir(), f"P11 targeted output dir missing: {p11_dir}"
        assert (p11_dir / "metrics_signal_mt.json").is_file()

    def test_guardrail_report_no_label_inference(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "activation_guardrail_report.json").read_text()
        )
        assert data["no_label_inference"] is True

    def test_guardrail_report_no_target_fabrication(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "activation_guardrail_report.json").read_text()
        )
        assert data["no_target_fabrication"] is True

    def test_guardrail_report_no_real_contract_activation(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "activation_guardrail_report.json").read_text()
        )
        assert data["no_real_contract_activation"] is True

    def test_report_contains_cautious_terms(self, smoke_out):
        text = (Path(smoke_out["out"]) / "report.md").read_text()
        assert "controlled activation smoke test" in text.lower()
        assert "explicit mock label contract" in text.lower()
        assert "target-aware signal benchmarking" in text.lower()

    def test_report_has_no_banned_phrases(self, smoke_out):
        text = (Path(smoke_out["out"]) / "report.md").read_text().lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in text, f"Banned phrase in report.md: {phrase}"

    def test_omega_event_safe_claim_has_no_banned_phrases(self, smoke_out):
        data = json.loads(
            (Path(smoke_out["out"]) / "omega_event.json").read_text()
        )
        claim = data.get("safe_claim", "").lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in claim, f"Banned phrase in safe_claim: {phrase}"

    def test_no_y_targets_fabricated_in_p15_module(self):
        src = Path(
            "sciencer_d/btc_icft/pipelines/run_target_aware_activation_smoke.py"
        ).read_text()
        # P15 should not contain target fabrication logic
        assert "y = 1" not in src
        assert "y = 0" not in src
        assert "infer_label" not in src
        assert "make_target" not in src


# ---------------------------------------------------------------------------
# Config and guardrails
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_contains_required_outputs(self):
        cfg = Path("configs/btc_icft/target_aware_activation_smoke.yaml").read_text()
        for item in [
            "activation_smoke_summary.json",
            "activation_stage_results.json",
            "target_aware_metrics_snapshot.json",
            "activation_guardrail_report.json",
            "omega_event.json",
            "report.md",
        ]:
            assert item in cfg

    def test_config_contains_required_stages(self):
        cfg = Path("configs/btc_icft/target_aware_activation_smoke.yaml").read_text()
        for stage in [
            "p14_adapter_readiness",
            "p12_explicit_label_alignment",
            "p10_level_t_signal_topology",
            "p13_target_injection",
            "p11_target_aware_signal_mt",
        ]:
            assert stage in cfg

    def test_config_contains_guardrails(self):
        cfg = Path("configs/btc_icft/target_aware_activation_smoke.yaml").read_text()
        for gr in [
            "no_label_inference",
            "no_target_fabrication",
            "no_real_contract_activation",
            "no_legacy_mt_real_change",
        ]:
            assert gr in cfg

    def test_config_no_banned_phrases(self):
        cfg = Path("configs/btc_icft/target_aware_activation_smoke.yaml").read_text().lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in cfg

    def test_safe_claim_has_no_banned_phrases(self):
        for phrase in _BANNED_PHRASES:
            assert phrase not in _SAFE_CLAIM.lower()


# ---------------------------------------------------------------------------
# Stage command structure
# ---------------------------------------------------------------------------

class TestStageCommandStructure:
    def test_build_commands_returns_four_stages(self):
        cmds = _build_stage_commands(DATASET_ID, "outputs/btc_icft", "/tmp/out")
        assert len(cmds) == 4

    def test_all_commands_use_sys_executable(self):
        cmds = _build_stage_commands(DATASET_ID, "outputs/btc_icft", "/tmp/out")
        for stage, cmd, _ in cmds:
            assert cmd[0] == sys.executable, f"Stage {stage} not using sys.executable"

    def test_no_real_dataset_activation_in_commands(self):
        cmds = _build_stage_commands(DATASET_ID, "outputs/btc_icft", "/tmp/out")
        for stage, cmd, _ in cmds:
            cmd_str = " ".join(cmd)
            # Should not activate real contracts (only mock)
            if "align_eeg_labels" in cmd_str:
                assert "--activate-mock-contract" in cmd_str
