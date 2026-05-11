"""Tests for tools/validate_eeg_signal_artifacts.py.

All tests use tmp_path only — no real pipeline outputs required.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Load module without requiring it on sys.path
_spec = importlib.util.spec_from_file_location(
    "validate_eeg_signal_artifacts",
    "tools/validate_eeg_signal_artifacts.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

validate_stage = _mod.validate_stage
validate_all = _mod.validate_all
ValidationError = _mod.ValidationError

DATASET_ID = "DS005620"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, cols: list[str], rows: list[list] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        if rows:
            for row in rows:
                w.writerow(row)
        else:
            w.writerow(["x"] * len(cols))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_md(path: Path, text: str = "operational signal pipeline output") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mk_signal_blocks(root: Path) -> Path:
    """Minimal valid signal_blocks artifacts."""
    ds_lower = DATASET_ID.lower()
    sdir = root / ds_lower / "signal_blocks"
    sdir.mkdir(parents=True, exist_ok=True)

    _write_json(sdir / "signal_block_inventory.json", {"n_files": 1})
    _write_csv(sdir / "window_inventory.csv", [
        "file_path", "row_id", "window_id", "window_start_s", "window_end_s",
        "sample_start", "sample_end", "n_channels", "n_samples", "sample_rate_hz",
        "status",
    ])
    _write_json(sdir / "reader_alignment_report.json", {
        "ready_for_p9_signal_extraction": True,
    })
    _write_json(sdir / "skipped_files.json", {"skipped": []})
    _write_json(sdir / "omega_event.json", {"safe_claim": "operational telemetry"})
    _write_md(sdir / "report.md")
    return sdir


def _mk_eeg_level_m(root: Path) -> Path:
    sdir = root / "eeg_level_m" / DATASET_ID
    sdir.mkdir(parents=True, exist_ok=True)

    _write_csv(sdir / "features_m_signal.csv", [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
        "artifact_score", "feature_status",
    ])
    _write_json(sdir / "feature_quality_report.json", {
        "quality_passed": True,
        "n_feature_rows": 5,
        "n_skipped_windows": 0,
    })
    _write_json(sdir / "artifact_report.json", {"artifact_dominance": False})
    _write_json(sdir / "skipped_windows.json", {"skipped": []})
    _write_json(sdir / "omega_event.json", {"safe_claim": "operational features"})
    _write_md(sdir / "report.md")
    return sdir


def _mk_eeg_level_t(root: Path) -> Path:
    sdir = root / "eeg_level_t" / DATASET_ID
    sdir.mkdir(parents=True, exist_ok=True)

    _write_csv(sdir / "features_t_signal.csv", [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "q_net", "q_abs", "f_dress", "defect_density",
        "n_triangles", "n_valid_triangles", "topology_quality", "topology_status",
    ])
    _write_json(sdir / "topology_quality_report.json", {
        "quality_passed": True,
        "n_topology_rows": 5,
        "n_skipped_windows": 0,
    })
    _write_json(sdir / "artifact_report.json", {"artifact_dominance": False})
    _write_json(sdir / "skipped_windows.json", {"skipped": []})
    _write_json(sdir / "omega_event.json", {"safe_claim": "operational topology"})
    _write_md(sdir / "report.md")
    return sdir


def _mk_eeg_signal_mt(root: Path) -> Path:
    sdir = root / "eeg_signal_mt" / DATASET_ID
    sdir.mkdir(parents=True, exist_ok=True)

    _write_csv(sdir / "features_joined_signal.csv", [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
        "artifact_score_m", "feature_status",
        "q_net", "q_abs", "f_dress", "defect_density",
        "n_triangles", "n_valid_triangles", "topology_quality", "topology_status",
        "y", "label",
    ])
    _write_json(sdir / "metrics_signal_mt.json", {
        "predictive_metrics_available": False,
        "promoted": False,
        "promotion_reason": "blocked: no explicit targets available",
    })
    _write_json(sdir / "nulls_signal.json", {
        "real_nulls_performed": False,
        "nulls_passed": False,
    })
    _write_json(sdir / "ablations_signal.json", {
        "ablations_passed": False,
        "ablation_entries": {"M_only": {}, "M_plus_all_T": {}},
    })
    _write_json(sdir / "alignment_report.json", {
        "alignment_passed": True,
        "n_joined_rows": 5,
    })
    _write_json(sdir / "artifact_report.json", {"artifact_dominance": False})
    _write_json(sdir / "omega_event.json", {"safe_claim": "operational residual benchmark"})
    _write_md(sdir / "report.md")
    return sdir


def _mk_eeg_studies(root: Path) -> Path:
    sdir = root / "eeg_studies" / DATASET_ID
    sdir.mkdir(parents=True, exist_ok=True)

    _write_json(sdir / "study_card.json", {"safe_claim": "operational"})
    _write_json(sdir / "file_readability_report.json", {"n_files": 1})
    _write_json(sdir / "reader_capability_report.json", {"adapters": []})
    _write_json(sdir / "dataset_readiness_report.json", {
        "dataset_id": DATASET_ID,
        "readiness_status": "fixture_readable",
    })
    _write_md(sdir / "report.md")
    return sdir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSignalBlocksStage:
    def test_passes_on_complete_minimal_artifacts(self, tmp_path):
        _mk_signal_blocks(tmp_path)
        result = validate_stage(tmp_path, "signal_blocks", DATASET_ID)
        assert result["ok"] is True

    def test_fails_on_missing_required_file(self, tmp_path):
        sdir = _mk_signal_blocks(tmp_path)
        (sdir / "omega_event.json").unlink()
        with pytest.raises(ValidationError, match="missing required files"):
            validate_stage(tmp_path, "signal_blocks", DATASET_ID)

    def test_fails_on_missing_csv_column(self, tmp_path):
        sdir = _mk_signal_blocks(tmp_path)
        _write_csv(sdir / "window_inventory.csv", ["file_path", "row_id"])
        with pytest.raises(ValidationError, match="missing columns"):
            validate_stage(tmp_path, "signal_blocks", DATASET_ID)

    def test_fails_on_missing_json_key(self, tmp_path):
        sdir = _mk_signal_blocks(tmp_path)
        _write_json(sdir / "reader_alignment_report.json", {"other": True})
        with pytest.raises(ValidationError, match="missing keys"):
            validate_stage(tmp_path, "signal_blocks", DATASET_ID)


class TestEegLevelMStage:
    def test_passes_on_complete_minimal_artifacts(self, tmp_path):
        _mk_eeg_level_m(tmp_path)
        result = validate_stage(tmp_path, "eeg_level_m", DATASET_ID)
        assert result["ok"] is True

    def test_fails_on_missing_required_file(self, tmp_path):
        sdir = _mk_eeg_level_m(tmp_path)
        (sdir / "feature_quality_report.json").unlink()
        with pytest.raises(ValidationError, match="missing required files"):
            validate_stage(tmp_path, "eeg_level_m", DATASET_ID)

    def test_fails_on_missing_csv_column(self, tmp_path):
        sdir = _mk_eeg_level_m(tmp_path)
        _write_csv(sdir / "features_m_signal.csv", ["dataset_id", "row_id"])
        with pytest.raises(ValidationError, match="missing columns"):
            validate_stage(tmp_path, "eeg_level_m", DATASET_ID)

    def test_fails_on_missing_json_key(self, tmp_path):
        sdir = _mk_eeg_level_m(tmp_path)
        _write_json(sdir / "feature_quality_report.json", {"quality_passed": True})
        with pytest.raises(ValidationError, match="missing keys"):
            validate_stage(tmp_path, "eeg_level_m", DATASET_ID)


class TestEegLevelTStage:
    def test_passes_on_complete_minimal_artifacts(self, tmp_path):
        _mk_eeg_level_t(tmp_path)
        result = validate_stage(tmp_path, "eeg_level_t", DATASET_ID)
        assert result["ok"] is True

    def test_fails_on_missing_required_file(self, tmp_path):
        sdir = _mk_eeg_level_t(tmp_path)
        (sdir / "topology_quality_report.json").unlink()
        with pytest.raises(ValidationError, match="missing required files"):
            validate_stage(tmp_path, "eeg_level_t", DATASET_ID)

    def test_fails_on_missing_csv_column(self, tmp_path):
        sdir = _mk_eeg_level_t(tmp_path)
        _write_csv(sdir / "features_t_signal.csv", ["dataset_id", "row_id"])
        with pytest.raises(ValidationError, match="missing columns"):
            validate_stage(tmp_path, "eeg_level_t", DATASET_ID)

    def test_fails_on_missing_json_key(self, tmp_path):
        sdir = _mk_eeg_level_t(tmp_path)
        _write_json(sdir / "topology_quality_report.json", {"quality_passed": True})
        with pytest.raises(ValidationError, match="missing keys"):
            validate_stage(tmp_path, "eeg_level_t", DATASET_ID)


class TestEegSignalMtStage:
    def test_passes_on_complete_minimal_artifacts(self, tmp_path):
        _mk_eeg_signal_mt(tmp_path)
        result = validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)
        assert result["ok"] is True

    def test_fails_on_missing_required_file(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        (sdir / "metrics_signal_mt.json").unlink()
        with pytest.raises(ValidationError, match="missing required files"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_fails_on_missing_json_key_metrics(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        _write_json(sdir / "metrics_signal_mt.json", {"predictive_metrics_available": False})
        with pytest.raises(ValidationError, match="missing keys"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_features_joined_signal_csv_requires_both_m_and_t_columns(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        # Only M columns — missing T columns like q_net
        _write_csv(sdir / "features_joined_signal.csv", [
            "dataset_id", "row_id", "source_file", "window_id",
            "window_start_s", "window_end_s", "sample_start", "sample_end",
            "n_channels", "n_samples", "sample_rate_hz",
            "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
            "artifact_score_m", "feature_status",
        ])
        with pytest.raises(ValidationError, match="missing columns"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_metrics_signal_mt_requires_promoted_and_promotion_reason(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        _write_json(sdir / "metrics_signal_mt.json", {
            "predictive_metrics_available": False,
        })
        with pytest.raises(ValidationError, match="missing keys"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)


class TestGuardrails:
    def test_fails_on_banned_phrase_in_report_md(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        _write_md(sdir / "report.md", "proves consciousness")
        with pytest.raises(ValidationError, match="proves consciousness"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_fails_on_banned_phrase_in_json(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        _write_json(sdir / "omega_event.json", {
            "safe_claim": "soul proven in EEG signal",
        })
        with pytest.raises(ValidationError, match="soul proven"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_fails_when_omega_event_lacks_claim_key(self, tmp_path):
        sdir = _mk_eeg_signal_mt(tmp_path)
        _write_json(sdir / "omega_event.json", {"no_claim_key": "x"})
        with pytest.raises(ValidationError, match="missing claim key"):
            validate_stage(tmp_path, "eeg_signal_mt", DATASET_ID)

    def test_fails_on_sedated_implies_no_experience(self, tmp_path):
        sdir = _mk_eeg_level_m(tmp_path)
        _write_md(sdir / "report.md", "sedated implies no_experience")
        with pytest.raises(ValidationError):
            validate_stage(tmp_path, "eeg_level_m", DATASET_ID)


class TestValidateAll:
    def test_json_success_output_parses_with_ok_true(self, tmp_path):
        _mk_signal_blocks(tmp_path)
        _mk_eeg_level_m(tmp_path)
        _mk_eeg_level_t(tmp_path)
        _mk_eeg_signal_mt(tmp_path)
        _mk_eeg_studies(tmp_path)

        cp = subprocess.run(
            [
                sys.executable,
                "tools/validate_eeg_signal_artifacts.py",
                "--root", str(tmp_path),
                "--dataset-id", DATASET_ID,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert cp.returncode == 0
        result = json.loads(cp.stdout)
        assert result["ok"] is True

    def test_json_failure_output_parses_with_ok_false(self, tmp_path):
        # Stage missing entirely
        cp = subprocess.run(
            [
                sys.executable,
                "tools/validate_eeg_signal_artifacts.py",
                "--root", str(tmp_path),
                "--dataset-id", DATASET_ID,
                "--stage", "eeg_signal_mt",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert cp.returncode != 0
        result = json.loads(cp.stdout)
        assert result["ok"] is False

    def test_allow_missing_permits_absent_non_selected_stages(self, tmp_path):
        _mk_eeg_signal_mt(tmp_path)
        result = validate_all(
            tmp_path,
            dataset_id=DATASET_ID,
            stages=["eeg_signal_mt"],
            allow_missing=False,
        )
        assert result["ok"] is True

    def test_stage_filtering_validates_only_selected_stage(self, tmp_path):
        _mk_eeg_signal_mt(tmp_path)
        result = validate_all(
            tmp_path,
            dataset_id=DATASET_ID,
            stages=["eeg_signal_mt"],
        )
        assert result["ok"] is True
        assert "eeg_signal_mt" in result["stages"]
        assert "eeg_level_m" not in result["stages"]

    def test_allow_missing_skips_absent_dirs(self, tmp_path):
        result = validate_all(
            tmp_path,
            dataset_id=DATASET_ID,
            allow_missing=True,
        )
        assert result["ok"] is True
        assert len(result["warnings"]) > 0

    def test_eeg_studies_stage_passes(self, tmp_path):
        _mk_eeg_studies(tmp_path)
        result = validate_stage(tmp_path, "eeg_studies", DATASET_ID)
        assert result["ok"] is True
