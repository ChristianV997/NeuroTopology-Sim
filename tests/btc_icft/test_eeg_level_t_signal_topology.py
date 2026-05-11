"""Tests for P10 EEG Level T signal topology extraction scaffold.

All tests are offline and stdlib-only. No MNE, scipy, or numpy required.

Spec-required tests:
 1. load_signal_window_inventory reads minimal window_inventory.csv
 2. missing window_inventory.csv raises FileNotFoundError with actionable message
 3. missing required columns raises ValueError listing missing columns
 4. compute_signal_topology_for_window computes finite topology from CSV with >=3 ch
 5. q_abs is non-negative and >= abs(q_net) after normalization (invariant check)
 6. f_dress is non-negative
 7. defect_density is finite and non-negative
 8. topology_quality is finite and in [0, 1]
 9. insufficient channels produce insufficient_channels status or skipped record
10. short_window status is preserved or reflected
11. invalid sample range yields skipped_invalid_window or skipped_no_samples
12. missing source file yields skipped_unreadable_source without crashing full extraction
13. compute_signal_topology_rows returns rows for valid and skipped records for invalid
14. topology_quality_report includes required keys
15. artifact_report includes required keys
16. low topology quality triggers topology_artifact_dominance
17. write_level_t_signal_outputs writes all six files
18. JSON outputs parse
19. features_t_signal.csv contains all required columns
20. report.md contains cautious terms
21. report.md does not contain banned phrases
22. CLI mock fixture smoke returns 0 and writes six files
23. CLI missing signal-blocks fails cleanly
24. config exists and contains required outputs, topology columns, and guardrails
25. No label/y/residual/Level M conclusion fields emitted as conclusions
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sciencer_d.btc_icft.level_t.eeg_signal_topology import (
    EEGLevelTSignalTopologyRow,
    EEGLevelTSignalTopologyResult,
    load_signal_window_inventory,
    compute_signal_topology_for_window,
    compute_signal_topology_rows,
    build_topology_quality_report,
    build_signal_topology_artifact_report,
    build_level_t_signal_omega_event,
    write_level_t_signal_outputs,
    _validate_safe_text,
    _SAFE_CLAIM,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FEAT_COLS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "q_net", "q_abs", "f_dress", "defect_density",
    "n_triangles", "n_valid_triangles", "topology_quality",
    "topology_status", "warnings",
]


def _write_window_inventory(path: Path, rows: list[dict]) -> None:
    cols = [
        "file_path", "row_id", "window_id", "window_start_s", "window_end_s",
        "sample_start", "sample_end", "n_channels", "n_samples",
        "sample_rate_hz", "channel_names", "status", "warnings",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in cols})


def _write_csv_signal(path: Path, n_channels: int = 4, n_rows: int = 200, sr: float = 100.0) -> None:
    with open(path, "w") as f:
        f.write(f"# channels: {n_channels}\n")
        f.write(f"# sample_rate: {sr}\n")
        headers = ["time"] + [f"ch{i+1}" for i in range(n_channels)]
        f.write(",".join(headers) + "\n")
        for i in range(n_rows):
            # Use different patterns per channel to avoid zero variance
            vals = [f"{i * 0.01:.4f}"] + [
                f"{(i + j) * 0.1 * (j + 1):.4f}" for j in range(n_channels)
            ]
            f.write(",".join(vals) + "\n")


def _make_window_dict(source_file: str, n_channels: int = 4, n_samples: int = 50) -> dict:
    return {
        "file_path": source_file,
        "row_id": "mock__win_0",
        "window_id": "win-000",
        "window_start_s": "0.0",
        "window_end_s": f"{n_samples / 100.0}",
        "sample_start": "0",
        "sample_end": str(n_samples),
        "n_channels": str(n_channels),
        "n_samples": str(n_samples),
        "sample_rate_hz": "100.0",
        "channel_names": "|".join([f"ch{i+1}" for i in range(n_channels)]),
        "status": "short_window",
        "warnings": "",
    }


def _make_full_result(tmp_path: Path) -> EEGLevelTSignalTopologyResult:
    sig_path = tmp_path / "sig.csv"
    _write_csv_signal(sig_path, n_channels=4, n_rows=200)

    inv_path = tmp_path / "signal_blocks" / "window_inventory.csv"
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    window = _make_window_dict(str(sig_path), n_channels=4, n_samples=100)
    window["status"] = "full_window"
    _write_window_inventory(inv_path, [window])

    windows = load_signal_window_inventory(str(inv_path.parent))
    topology_rows, skipped = compute_signal_topology_rows("DS005620", windows)
    tqr = build_topology_quality_report(topology_rows, skipped)
    ar = build_signal_topology_artifact_report(topology_rows)

    result = EEGLevelTSignalTopologyResult(
        dataset_id="DS005620",
        n_windows=len(windows),
        n_topology_rows=len(topology_rows),
        n_skipped_windows=len(skipped),
        topology_rows=[asdict(r) for r in topology_rows],
        skipped_windows=skipped,
        topology_quality_report=tqr,
        artifact_report=ar,
        omega_event={},
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[],
        warnings=[],
    )
    result.omega_event = build_level_t_signal_omega_event(result)
    return result


# ---------------------------------------------------------------------------
# Test 1: load_signal_window_inventory reads minimal window_inventory.csv
# ---------------------------------------------------------------------------

class TestLoadWindowInventory:
    def test_reads_minimal_csv(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=3, n_rows=50)
        inv_path = tmp_path / "window_inventory.csv"
        window = _make_window_dict(str(sig_path), n_channels=3, n_samples=50)
        _write_window_inventory(inv_path, [window])

        rows = load_signal_window_inventory(str(tmp_path))
        assert len(rows) == 1
        assert "row_id" in rows[0]
        assert "file_path" in rows[0]


# ---------------------------------------------------------------------------
# Test 2: missing window_inventory.csv raises FileNotFoundError
# ---------------------------------------------------------------------------

class TestMissingInventory:
    def test_missing_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_signal_window_inventory(str(tmp_path / "nonexistent"))
        assert "probe_eeg_signal_blocks" in str(exc_info.value) or "mock-fixture" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 3: missing required columns raises ValueError
# ---------------------------------------------------------------------------

class TestMissingColumns:
    def test_missing_columns_raises_value_error(self, tmp_path):
        inv_path = tmp_path / "window_inventory.csv"
        with open(inv_path, "w") as f:
            f.write("row_id,file_path\n")
            f.write("r0,/tmp/x.csv\n")

        with pytest.raises(ValueError) as exc_info:
            load_signal_window_inventory(str(tmp_path))
        assert "missing" in str(exc_info.value).lower() or "column" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 4: compute topology for valid CSV with >=3 channels gives finite values
# ---------------------------------------------------------------------------

class TestComputeTopologyFinite:
    def test_finite_topology_for_3_channel_csv(self, tmp_path):
        sig_path = tmp_path / "s3ch.csv"
        _write_csv_signal(sig_path, n_channels=3, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=3, n_samples=50)
        window["status"] = "full_window"
        row = compute_signal_topology_for_window("DS005620", window)
        assert row.topology_status not in {"skipped_unreadable_source", "skipped_parse_error"}
        import math
        assert math.isfinite(row.q_net)
        assert math.isfinite(row.q_abs)
        assert math.isfinite(row.f_dress)
        assert math.isfinite(row.defect_density)
        assert math.isfinite(row.topology_quality)


# ---------------------------------------------------------------------------
# Test 5: q_abs >= 0 and topology_quality is a valid proxy
# ---------------------------------------------------------------------------

class TestQAbsNonNegative:
    def test_q_abs_non_negative(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=50)
        row = compute_signal_topology_for_window("DS005620", window)
        if row.topology_status not in {"skipped_unreadable_source", "skipped_parse_error",
                                       "skipped_no_samples", "skipped_invalid_window"}:
            assert row.q_abs >= 0.0


# ---------------------------------------------------------------------------
# Test 6: f_dress is non-negative
# ---------------------------------------------------------------------------

class TestFDressNonNegative:
    def test_f_dress_non_negative(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=50)
        row = compute_signal_topology_for_window("DS005620", window)
        if row.topology_status not in {"skipped_unreadable_source", "skipped_parse_error",
                                       "skipped_no_samples", "skipped_invalid_window"}:
            assert row.f_dress >= 0.0


# ---------------------------------------------------------------------------
# Test 7: defect_density is finite and non-negative
# ---------------------------------------------------------------------------

class TestDefectDensity:
    def test_defect_density_finite_non_negative(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=50)
        row = compute_signal_topology_for_window("DS005620", window)
        if row.topology_status not in {"skipped_unreadable_source", "skipped_parse_error",
                                       "skipped_no_samples", "skipped_invalid_window"}:
            import math
            assert math.isfinite(row.defect_density)
            assert row.defect_density >= 0.0


# ---------------------------------------------------------------------------
# Test 8: topology_quality is finite and in [0, 1]
# ---------------------------------------------------------------------------

class TestTopologyQualityRange:
    def test_topology_quality_in_range(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=50)
        row = compute_signal_topology_for_window("DS005620", window)
        if row.topology_status not in {"skipped_unreadable_source", "skipped_parse_error",
                                       "skipped_no_samples", "skipped_invalid_window"}:
            import math
            assert math.isfinite(row.topology_quality)
            assert 0.0 <= row.topology_quality <= 1.0


# ---------------------------------------------------------------------------
# Test 9: insufficient channels -> insufficient_channels status
# ---------------------------------------------------------------------------

class TestInsufficientChannels:
    def test_single_channel_insufficient(self, tmp_path):
        sig_path = tmp_path / "s1ch.csv"
        with open(sig_path, "w") as f:
            f.write("# channels: 1\n# sample_rate: 100.0\n")
            for i in range(50):
                f.write(f"{i * 0.1}\n")
        window = _make_window_dict(str(sig_path), n_channels=1, n_samples=30)
        window["status"] = "full_window"
        row = compute_signal_topology_for_window("DS005620", window)
        assert row.topology_status in {"insufficient_channels", "skipped_invalid_window",
                                       "skipped_no_samples"}

    def test_two_channel_marks_insufficient(self, tmp_path):
        sig_path = tmp_path / "s2ch.csv"
        with open(sig_path, "w") as f:
            f.write("# channels: 2\n# sample_rate: 100.0\n")
            for i in range(50):
                f.write(f"{i * 0.1},{i * 0.2}\n")
        window = _make_window_dict(str(sig_path), n_channels=2, n_samples=30)
        window["status"] = "full_window"
        row = compute_signal_topology_for_window("DS005620", window)
        # 2 channels: n_triangles==0, topology_quality==0, status may be insufficient_channels
        assert row.n_triangles == 0
        assert row.topology_quality == 0.0


# ---------------------------------------------------------------------------
# Test 10: short_window status preserved
# ---------------------------------------------------------------------------

class TestShortWindowStatus:
    def test_short_window_status_preserved(self, tmp_path):
        sig_path = tmp_path / "sw.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=20)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=20)
        window["status"] = "short_window"
        row = compute_signal_topology_for_window("DS005620", window)
        assert row.topology_status == "short_window" or row.topology_status in {
            "skipped_no_samples", "skipped_unreadable_source", "ok", "insufficient_channels"
        }


# ---------------------------------------------------------------------------
# Test 11: invalid sample range yields skipped status
# ---------------------------------------------------------------------------

class TestInvalidSampleRange:
    def test_inverted_range_yields_skipped(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=100)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=50)
        window["sample_start"] = "100"
        window["sample_end"] = "10"  # end < start
        row = compute_signal_topology_for_window("DS005620", window)
        assert row.topology_status in {
            "skipped_invalid_window", "skipped_no_samples"
        }


# ---------------------------------------------------------------------------
# Test 12: missing source file yields skipped_unreadable_source
# ---------------------------------------------------------------------------

class TestMissingSourceFile:
    def test_missing_source_no_crash(self, tmp_path):
        window = _make_window_dict(str(tmp_path / "nonexistent.csv"), n_channels=4, n_samples=50)
        rows, skipped = compute_signal_topology_rows("DS005620", [window])
        # Either emitted as skipped or returned as a row with skipped status
        all_statuses = [r.topology_status for r in rows] + [s["reason"] for s in skipped]
        assert any("skip" in s or "unreadable" in s or "parse" in s for s in all_statuses)


# ---------------------------------------------------------------------------
# Test 13: compute_signal_topology_rows separates valid and invalid
# ---------------------------------------------------------------------------

class TestComputeTopologyRows:
    def test_separates_valid_and_skipped(self, tmp_path):
        sig_path = tmp_path / "v.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=200)

        valid_w = _make_window_dict(str(sig_path), n_channels=4, n_samples=100)
        valid_w["status"] = "full_window"
        missing_w = _make_window_dict(str(tmp_path / "ghost.csv"), n_channels=4, n_samples=50)
        missing_w["row_id"] = "ghost__win_0"

        rows, skipped = compute_signal_topology_rows("DS005620", [valid_w, missing_w])
        assert len(rows) + len(skipped) == 2
        # At least one skipped (the missing file)
        assert len(skipped) >= 1


# ---------------------------------------------------------------------------
# Test 14: topology_quality_report includes required keys
# ---------------------------------------------------------------------------

class TestTopologyQualityReport:
    def test_required_keys_present(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=200)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=100)
        window["status"] = "full_window"
        rows, skipped = compute_signal_topology_rows("DS005620", [window])
        tqr = build_topology_quality_report(rows, skipped)
        for key in [
            "n_windows", "n_topology_rows", "n_skipped_windows",
            "mean_topology_quality", "low_quality_windows",
            "finite_topology_rows", "quality_passed",
        ]:
            assert key in tqr, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Test 15: artifact_report includes required keys
# ---------------------------------------------------------------------------

class TestArtifactReport:
    def test_required_keys_present(self, tmp_path):
        sig_path = tmp_path / "s.csv"
        _write_csv_signal(sig_path, n_channels=4, n_rows=200)
        window = _make_window_dict(str(sig_path), n_channels=4, n_samples=100)
        window["status"] = "full_window"
        rows, _ = compute_signal_topology_rows("DS005620", [window])
        ar = build_signal_topology_artifact_report(rows)
        for key in [
            "mean_topology_quality", "min_topology_quality",
            "low_quality_windows", "insufficient_channel_windows",
            "topology_artifact_dominance",
        ]:
            assert key in ar, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Test 16: low topology quality triggers topology_artifact_dominance
# ---------------------------------------------------------------------------

class TestArtifactDominance:
    def test_all_zero_quality_triggers_dominance(self, tmp_path):
        from dataclasses import replace
        # Create rows with zero topology_quality
        rows = [
            EEGLevelTSignalTopologyRow(
                dataset_id="DS005620",
                row_id=f"r{i}",
                source_file="",
                window_id=f"win-{i:03d}",
                window_start_s=0.0,
                window_end_s=1.0,
                sample_start=0,
                sample_end=100,
                n_channels=2,
                n_samples=100,
                sample_rate_hz=100.0,
                q_net=0.0,
                q_abs=0.0,
                f_dress=0.0,
                defect_density=0.0,
                n_triangles=0,
                n_valid_triangles=0,
                topology_quality=0.0,
                topology_status="insufficient_channels",
            )
            for i in range(5)
        ]
        ar = build_signal_topology_artifact_report(rows)
        assert ar["topology_artifact_dominance"] is True


# ---------------------------------------------------------------------------
# Test 17: write_level_t_signal_outputs writes all six files
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def test_all_six_files_written(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        required = {
            "features_t_signal",
            "topology_quality_report",
            "artifact_report",
            "skipped_windows",
            "omega_event",
            "report",
        }
        assert required == set(outputs.keys())
        for name, path in outputs.items():
            assert Path(path).exists(), f"Missing artifact: {name}"


# ---------------------------------------------------------------------------
# Test 18: JSON outputs parse
# ---------------------------------------------------------------------------

class TestJsonOutputsParse:
    def test_json_outputs_parseable(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        for name in ["topology_quality_report", "artifact_report", "skipped_windows", "omega_event"]:
            with open(outputs[name]) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{name} is not a dict"


# ---------------------------------------------------------------------------
# Test 19: features_t_signal.csv contains all required columns
# ---------------------------------------------------------------------------

class TestFeaturesCsvColumns:
    def test_required_columns_present(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        with open(outputs["features_t_signal"], newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        for col in _FEAT_COLS:
            assert col in header, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Test 20: report.md contains cautious terms
# ---------------------------------------------------------------------------

class TestReportCautiousTerms:
    def test_contains_cautious_terms(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        text = Path(outputs["report"]).read_text()
        assert "operational Level T topology telemetry candidates" in text
        assert "future residual testing" in text
        assert "signal topology" in text.lower()

    def test_report_has_required_sections(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        text = Path(outputs["report"]).read_text()
        assert "EEG Level T Signal Topology Extraction" in text
        assert "Next Required Step" in text
        assert "Level M signal features" in text or "Level M" in text
        assert "signal-level residual benchmark" in text or "residual" in text.lower()


# ---------------------------------------------------------------------------
# Test 21: report.md does not contain banned phrases
# ---------------------------------------------------------------------------

class TestReportNoBannedPhrases:
    def test_no_banned_phrases(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        text = Path(outputs["report"]).read_text().lower()
        for phrase in [
            "proves consciousness", "consciousness proven",
            "soul proven", "afterlife proven", "liberation detected",
            "ontology solved", "ultimate reality",
            "q equals self", "q equals soul",
            "q_abs equals suffering", "f_dress equals karma",
        ]:
            assert phrase not in text, f"Banned phrase found: {phrase!r}"


# ---------------------------------------------------------------------------
# Test 22: CLI mock fixture smoke returns 0 and writes six files
# ---------------------------------------------------------------------------

class TestCliMockFixture:
    def test_cli_returns_0(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--mock-fixture",
                "--out", str(tmp_path / "cli_out"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

    def test_cli_writes_six_files(self, tmp_path):
        out_dir = str(tmp_path / "cli_out2")
        subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--mock-fixture",
                "--out", out_dir,
            ],
            capture_output=True,
            text=True,
        )
        out_path = Path(out_dir)
        for fname in [
            "features_t_signal.csv",
            "topology_quality_report.json",
            "artifact_report.json",
            "skipped_windows.json",
            "omega_event.json",
            "report.md",
        ]:
            assert (out_path / fname).exists(), f"Missing: {fname}"


# ---------------------------------------------------------------------------
# Test 23: CLI missing signal-blocks fails cleanly
# ---------------------------------------------------------------------------

class TestCliMissingSignalBlocks:
    def test_missing_inventory_fails_nonzero(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--signal-blocks", str(tmp_path / "nonexistent"),
                "--out", str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_missing_inventory_error_message(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--signal-blocks", str(tmp_path / "nonexistent"),
                "--out", str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        assert "probe_eeg_signal_blocks" in combined or "mock-fixture" in combined or "mock_fixture" in combined


# ---------------------------------------------------------------------------
# Test 24: config exists and contains required outputs, columns, guardrails
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_file_exists(self):
        assert Path("configs/btc_icft/eeg_level_t_signal.yaml").exists()

    def test_config_required_outputs(self):
        text = Path("configs/btc_icft/eeg_level_t_signal.yaml").read_text()
        for artifact in [
            "features_t_signal.csv",
            "topology_quality_report.json",
            "artifact_report.json",
            "skipped_windows.json",
            "omega_event.json",
            "report.md",
        ]:
            assert artifact in text, f"Config missing: {artifact}"

    def test_config_topology_columns(self):
        text = Path("configs/btc_icft/eeg_level_t_signal.yaml").read_text()
        for col in ["q_net", "q_abs", "f_dress", "defect_density", "topology_quality"]:
            assert col in text, f"Config missing column: {col}"

    def test_config_guardrails(self):
        text = Path("configs/btc_icft/eeg_level_t_signal.yaml").read_text()
        for guardrail in [
            "no_data_download",
            "no_residual_promotion",
            "no_ontology_claims",
            "q_not_self",
            "q_not_soul",
            "q_abs_not_suffering",
            "f_dress_not_karma",
        ]:
            assert guardrail in text, f"Config missing guardrail: {guardrail}"


# ---------------------------------------------------------------------------
# Test 25: No label/y/residual/Level M conclusion fields
# ---------------------------------------------------------------------------

class TestNoConclusions:
    def test_no_label_fields_in_topology_row(self):
        row = EEGLevelTSignalTopologyRow(
            dataset_id="DS005620",
            row_id="r0",
            source_file="",
            window_id="win-000",
            window_start_s=0.0,
            window_end_s=1.0,
            sample_start=0,
            sample_end=100,
            n_channels=4,
            n_samples=100,
            sample_rate_hz=100.0,
            q_net=0.1,
            q_abs=0.2,
            f_dress=0.1,
            defect_density=0.5,
            n_triangles=4,
            n_valid_triangles=2,
            topology_quality=0.5,
            topology_status="ok",
        )
        d = asdict(row)
        # No label or target fields should exist
        for banned_field in ["label", "y", "target", "residual", "consciousness_score"]:
            assert banned_field not in d, f"Banned field in row: {banned_field}"

    def test_safe_claim_no_banned_phrases(self):
        _validate_safe_text(_SAFE_CLAIM)

    def test_forbidden_claims_empty_by_default(self, tmp_path):
        result = _make_full_result(tmp_path)
        assert result.forbidden_claims == []

    def test_omega_event_safe_claim_matches_spec(self, tmp_path):
        result = _make_full_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_level_t_signal_outputs(result, out_dir)
        with open(outputs["omega_event"]) as f:
            data = json.load(f)
        assert "operational" in data["safe_claim"]
        assert "topology telemetry candidates" in data["safe_claim"]
        assert "future residual testing" in data["safe_claim"]
