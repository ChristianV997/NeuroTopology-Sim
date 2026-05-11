"""Tests for tools/run_eeg_signal_pipeline_smoke.py.

Most tests are unit tests around command construction. One real subprocess
smoke test runs the full pipeline with --mock-fixture in an isolated tmp root.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Load module without requiring it on sys.path
_spec = importlib.util.spec_from_file_location(
    "run_eeg_signal_pipeline_smoke",
    "tools/run_eeg_signal_pipeline_smoke.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

_build_commands = _mod._build_commands
_read_promotion_status = _mod._read_promotion_status
run_smoke = _mod.run_smoke

DATASET_ID = "DS005620"
_EXPECTED_MODULES = [
    "sciencer_d.btc_icft.pipelines.feed_eeg_study_dataset",
    "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks",
    "sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal",
    "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
    "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
]


class TestCli:
    def test_help_works(self):
        cp = subprocess.run(
            [sys.executable, "tools/run_eeg_signal_pipeline_smoke.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert cp.returncode == 0
        assert "smoke" in cp.stdout.lower() or "dataset" in cp.stdout.lower()


class TestCommandConstruction:
    def test_uses_expected_module_names(self):
        commands = _build_commands(DATASET_ID, "outputs/btc_icft")
        # cmd structure: [sys.executable, "-m", module_name, ...]
        modules_used = [cmd[2] for _, cmd in commands]
        for expected in _EXPECTED_MODULES:
            assert expected in modules_used, f"Missing module: {expected}"

    def test_all_commands_include_mock_fixture(self):
        commands = _build_commands(DATASET_ID, "outputs/btc_icft")
        for name, cmd in commands:
            assert "--mock-fixture" in cmd, f"Stage {name} missing --mock-fixture"

    def test_all_commands_use_sys_executable(self):
        commands = _build_commands(DATASET_ID, "outputs/btc_icft")
        for name, cmd in commands:
            assert cmd[0] == sys.executable, f"Stage {name} not using sys.executable"

    def test_no_p12_command_in_sequence(self):
        commands = _build_commands(DATASET_ID, "outputs/btc_icft")
        all_args = " ".join(arg for _, cmd in commands for arg in cmd)
        assert "align_eeg_labels" not in all_args
        assert "eeg_label_contracts" not in all_args

    def test_no_labels_y_fabrication_in_source(self):
        src = Path("tools/run_eeg_signal_pipeline_smoke.py").read_text()
        assert "align_eeg_labels" not in src
        assert "eeg_label_contracts" not in src
        # No actual label/target-generation logic (docstring negations are ok)
        assert "infer_label" not in src
        assert "make_target" not in src
        assert "create_y" not in src

    def test_dataset_id_appears_in_output_paths(self):
        commands = _build_commands("DS099999", "outputs/x")
        for name, cmd in commands:
            joined = " ".join(cmd)
            if name not in ("probe_eeg_signal_blocks",):
                assert "DS099999" in joined, f"Dataset ID missing in {name} command"


class TestPromotionReading:
    def test_returns_none_when_metrics_missing(self, tmp_path):
        result = _read_promotion_status(str(tmp_path), DATASET_ID)
        assert result is None

    def test_reads_promoted_false_correctly(self, tmp_path):
        metrics_dir = tmp_path / "eeg_signal_mt" / DATASET_ID
        metrics_dir.mkdir(parents=True)
        (metrics_dir / "metrics_signal_mt.json").write_text(
            json.dumps({
                "promoted": False,
                "promotion_reason": "blocked: no explicit targets available",
                "predictive_metrics_available": False,
            }),
            encoding="utf-8",
        )
        result = _read_promotion_status(str(tmp_path), DATASET_ID)
        assert result is not None
        assert result["promoted"] is False
        assert "no explicit targets" in result["promotion_reason"]


class TestSmokeFinalMetrics:
    def test_fixture_smoke_promoted_false(self, tmp_path):
        """Full end-to-end smoke with --mock-fixture in isolated tmp root."""
        rc = run_smoke(dataset_id=DATASET_ID, root=str(tmp_path), validate=False)
        assert rc == 0

        metrics_path = (
            tmp_path / "eeg_signal_mt" / DATASET_ID / "metrics_signal_mt.json"
        )
        assert metrics_path.is_file(), "metrics_signal_mt.json not produced"
        data = json.loads(metrics_path.read_text())
        assert data["promoted"] is False
        assert "no explicit targets" in data["promotion_reason"]
