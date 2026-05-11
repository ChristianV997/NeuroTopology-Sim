"""Tests for P11 EEG signal-level M+T residual benchmark (Issue #68).

All tests are offline and stdlib-only. No MNE, scipy, or numpy required.
Legacy ds005620_mt_real files are NOT imported.

Spec-required tests (35):
 1. load_level_m_signal_features reads minimal features_m_signal.csv
 2. load_level_t_signal_features reads minimal features_t_signal.csv
 3. missing M/T file raises FileNotFoundError with actionable message
 4. missing M required column raises ValueError listing missing column
 5. missing T required column raises ValueError listing missing column
 6. strict join preserves composite key fields
 7. duplicate M keys fail
 8. duplicate T keys fail
 9. M rows without matching T rows fail
10. extra T rows are ignored with warning
11. no y targets => predictive_metrics_available false
12. no y targets => promoted false
13. no y targets => promotion_reason "blocked: no explicit targets available"
14. labels alone do not create y
15. y present with one class => insufficient class variation
16. y present with two classes => metrics available
17. metrics dict contains auc/brier/ece/delta keys
18. null report unavailable when no targets
19. ablation report includes all required ablations
20. ablation entries unavailable when no targets
21. alignment_report includes required fields and alignment_passed
22. artifact_report includes required fields
23. artifact dominance triggers on high artifact score
24. artifact dominance triggers on low topology quality
25. write_signal_mt_outputs writes all eight files
26. JSON outputs parse
27. features_joined_signal.csv contains required columns
28. report.md contains cautious terms
29. report.md does not contain banned phrases
30. CLI mock fixture smoke returns 0 and writes eight files
31. CLI missing inputs fails cleanly with required message
32. config exists and contains outputs, join keys, promotion gate, guardrails
33. legacy mt_real files are not imported or required for this path
34. no target fabrication from labels/state/text
35. optional y from M input is preserved if explicit
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sciencer_d.btc_icft.evaluation.eeg_signal_residual import (
    EEGSignalMTJoinedRow,
    EEGSignalMTResidualResult,
    load_level_m_signal_features,
    load_level_t_signal_features,
    join_signal_m_t_rows,
    evaluate_signal_mt_residual,
    build_signal_alignment_report,
    build_signal_artifact_report,
    build_signal_null_report,
    build_signal_ablation_report,
    write_signal_mt_outputs,
    _validate_safe_text,
    _SAFE_CLAIM,
    _JOINED_COLS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_M_COLS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
    "artifact_score", "feature_status", "warnings",
]

_T_COLS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "q_net", "q_abs", "f_dress", "defect_density",
    "n_triangles", "n_valid_triangles", "topology_quality",
    "topology_status", "warnings",
]


def _write_m_csv(path: Path, rows: list[dict], extra_cols: list[str] | None = None) -> None:
    cols = _M_COLS + (extra_cols or [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in cols})


def _write_t_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_T_COLS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in _T_COLS})


def _mk_m_row(i: int = 0, y: str = "", label: str = "") -> dict:
    return {
        "dataset_id": "DS005620",
        "row_id": f"r{i}",
        "source_file": f"/s/{i}.csv",
        "window_id": f"win-{i:03d}",
        "window_start_s": str(float(i)),
        "window_end_s": str(float(i) + 1.0),
        "sample_start": str(i * 100),
        "sample_end": str(i * 100 + 100),
        "n_channels": "4",
        "n_samples": "100",
        "sample_rate_hz": "100.0",
        "spectral_power_proxy": f"{0.3 + i * 0.05:.4f}",
        "entropy_proxy": f"{0.5 + i * 0.03:.4f}",
        "lzc_proxy": f"{0.4 + i * 0.04:.4f}",
        "artifact_score": f"{0.1 + i * 0.02:.4f}",
        "feature_status": "ok",
        "warnings": "",
        "y": y,
        "label": label,
    }


def _mk_t_row(i: int = 0) -> dict:
    return {
        "dataset_id": "DS005620",
        "row_id": f"r{i}",
        "source_file": f"/s/{i}.csv",
        "window_id": f"win-{i:03d}",
        "window_start_s": str(float(i)),
        "window_end_s": str(float(i) + 1.0),
        "sample_start": str(i * 100),
        "sample_end": str(i * 100 + 100),
        "n_channels": "4",
        "n_samples": "100",
        "sample_rate_hz": "100.0",
        "q_net": f"{0.1 + i * 0.01:.4f}",
        "q_abs": f"{0.2 + i * 0.02:.4f}",
        "f_dress": f"{0.05 + i * 0.01:.4f}",
        "defect_density": f"{0.15:.4f}",
        "n_triangles": "4",
        "n_valid_triangles": "3",
        "topology_quality": f"{0.7 + i * 0.02:.4f}",
        "topology_status": "ok",
        "warnings": "",
    }


def _make_result(tmp_path: Path, n: int = 5, with_y: bool = False) -> tuple:
    m_rows = [_mk_m_row(i, y=str(i % 2) if with_y else "") for i in range(n)]
    t_rows = [_mk_t_row(i) for i in range(n)]
    joined, warnings = join_signal_m_t_rows(m_rows, t_rows)
    result = evaluate_signal_mt_residual(
        joined, "DS005620", m_rows=m_rows, t_rows=t_rows, join_warnings=warnings
    )
    return result, joined, m_rows, t_rows


# ---------------------------------------------------------------------------
# Test 1: load_level_m_signal_features reads minimal CSV
# ---------------------------------------------------------------------------

class TestLoadMFeatures:
    def test_reads_minimal_csv(self, tmp_path):
        p = tmp_path / "features_m_signal.csv"
        _write_m_csv(p, [_mk_m_row(0)])
        rows = load_level_m_signal_features(str(p))
        assert len(rows) == 1
        assert "row_id" in rows[0]


# ---------------------------------------------------------------------------
# Test 2: load_level_t_signal_features reads minimal CSV
# ---------------------------------------------------------------------------

class TestLoadTFeatures:
    def test_reads_minimal_csv(self, tmp_path):
        p = tmp_path / "features_t_signal.csv"
        _write_t_csv(p, [_mk_t_row(0)])
        rows = load_level_t_signal_features(str(p))
        assert len(rows) == 1
        assert "q_net" in rows[0]


# ---------------------------------------------------------------------------
# Test 3: Missing file raises FileNotFoundError with actionable message
# ---------------------------------------------------------------------------

class TestMissingFiles:
    def test_missing_m_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc:
            load_level_m_signal_features(str(tmp_path / "nope.csv"))
        assert "run_eeg_level_m_signal" in str(exc.value) or "mock-fixture" in str(exc.value)

    def test_missing_t_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc:
            load_level_t_signal_features(str(tmp_path / "nope.csv"))
        assert "run_eeg_level_t_signal" in str(exc.value) or "mock-fixture" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 4: Missing M required column raises ValueError
# ---------------------------------------------------------------------------

class TestMissingMColumn:
    def test_missing_m_column_raises(self, tmp_path):
        p = tmp_path / "features_m_signal.csv"
        # Write with spectral_power_proxy missing
        with open(p, "w") as f:
            f.write("dataset_id,row_id,source_file\n")
            f.write("DS005620,r0,/s/0.csv\n")
        with pytest.raises(ValueError) as exc:
            load_level_m_signal_features(str(p))
        assert "missing" in str(exc.value).lower() or "column" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Test 5: Missing T required column raises ValueError
# ---------------------------------------------------------------------------

class TestMissingTColumn:
    def test_missing_t_column_raises(self, tmp_path):
        p = tmp_path / "features_t_signal.csv"
        with open(p, "w") as f:
            f.write("dataset_id,row_id,source_file\n")
            f.write("DS005620,r0,/s/0.csv\n")
        with pytest.raises(ValueError) as exc:
            load_level_t_signal_features(str(p))
        assert "missing" in str(exc.value).lower() or "column" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Test 6: Strict join preserves composite key fields
# ---------------------------------------------------------------------------

class TestJoinKeyPreservation:
    def test_composite_keys_preserved(self):
        m_rows = [_mk_m_row(i) for i in range(3)]
        t_rows = [_mk_t_row(i) for i in range(3)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        assert len(joined) == 3
        for i, row in enumerate(joined):
            assert row.dataset_id == "DS005620"
            assert row.row_id == f"r{i}"
            assert row.window_id == f"win-{i:03d}"


# ---------------------------------------------------------------------------
# Test 7: Duplicate M keys fail
# ---------------------------------------------------------------------------

class TestDuplicateMKeys:
    def test_duplicate_m_raises(self):
        m_rows = [_mk_m_row(0), _mk_m_row(0)]  # same key twice
        t_rows = [_mk_t_row(0)]
        with pytest.raises(ValueError, match="Duplicate M key"):
            join_signal_m_t_rows(m_rows, t_rows)


# ---------------------------------------------------------------------------
# Test 8: Duplicate T keys fail
# ---------------------------------------------------------------------------

class TestDuplicateTKeys:
    def test_duplicate_t_raises(self):
        m_rows = [_mk_m_row(0)]
        t_rows = [_mk_t_row(0), _mk_t_row(0)]  # same key twice
        with pytest.raises(ValueError, match="Duplicate T key"):
            join_signal_m_t_rows(m_rows, t_rows)


# ---------------------------------------------------------------------------
# Test 9: M rows without matching T rows fail
# ---------------------------------------------------------------------------

class TestMissingTForM:
    def test_missing_t_raises(self):
        m_rows = [_mk_m_row(0), _mk_m_row(1)]
        t_rows = [_mk_t_row(0)]  # missing T for row 1
        with pytest.raises(ValueError):
            join_signal_m_t_rows(m_rows, t_rows)


# ---------------------------------------------------------------------------
# Test 10: Extra T rows are ignored with warning
# ---------------------------------------------------------------------------

class TestExtraTRows:
    def test_extra_t_ignored_with_warning(self):
        m_rows = [_mk_m_row(0)]
        t_rows = [_mk_t_row(0), _mk_t_row(99)]  # row 99 has no matching M
        joined, warnings = join_signal_m_t_rows(m_rows, t_rows)
        assert len(joined) == 1
        assert any("Extra T row" in w or "extra" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests 11-13: No y targets => metrics unavailable, promoted=false, reason
# ---------------------------------------------------------------------------

class TestNoYTargets:
    def test_predictive_metrics_false(self):
        result, _, _, _ = _make_result(None, n=5, with_y=False)  # type: ignore
        assert result.predictive_metrics_available is False

    def test_promoted_false(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, w = join_signal_m_t_rows(m, t)
        result = evaluate_signal_mt_residual(j, "DS005620", m_rows=m, t_rows=t)
        assert result.promoted is False

    def test_promotion_reason_blocked_no_targets(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, w = join_signal_m_t_rows(m, t)
        result = evaluate_signal_mt_residual(j, "DS005620", m_rows=m, t_rows=t)
        assert "blocked" in result.promotion_reason
        assert "no explicit targets" in result.promotion_reason


# ---------------------------------------------------------------------------
# Test 14: Labels alone do not create y
# ---------------------------------------------------------------------------

class TestLabelsAloneNoY:
    def test_label_text_does_not_create_y(self):
        # Row has label="awake" but no numeric y
        m_rows = [_mk_m_row(i, y="", label="awake") for i in range(3)]
        t_rows = [_mk_t_row(i) for i in range(3)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        # y should be None since no numeric y was provided
        for row in joined:
            assert row.y is None


# ---------------------------------------------------------------------------
# Test 15: y present with one class => insufficient class variation
# ---------------------------------------------------------------------------

class TestOneClass:
    def test_one_class_blocks(self):
        m_rows = [_mk_m_row(i, y="0") for i in range(4)]  # all class 0
        t_rows = [_mk_t_row(i) for i in range(4)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        result = evaluate_signal_mt_residual(joined, "DS005620", m_rows=m_rows, t_rows=t_rows)
        assert result.predictive_metrics_available is False
        assert "insufficient class variation" in result.promotion_reason


# ---------------------------------------------------------------------------
# Test 16: y with two classes => metrics available
# ---------------------------------------------------------------------------

class TestTwoClasses:
    def test_two_classes_metrics_available(self):
        m_rows = [_mk_m_row(i, y=str(i % 2)) for i in range(6)]
        t_rows = [_mk_t_row(i) for i in range(6)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        result = evaluate_signal_mt_residual(joined, "DS005620", m_rows=m_rows, t_rows=t_rows)
        assert result.predictive_metrics_available is True
        assert result.metrics.get("auc_m") is not None


# ---------------------------------------------------------------------------
# Test 17: Metrics dict contains auc/brier/ece/delta keys
# ---------------------------------------------------------------------------

class TestMetricsKeys:
    def test_metrics_keys_present(self):
        m_rows = [_mk_m_row(i, y=str(i % 2)) for i in range(6)]
        t_rows = [_mk_t_row(i) for i in range(6)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        result = evaluate_signal_mt_residual(joined, "DS005620", m_rows=m_rows, t_rows=t_rows)
        for key in ["auc_m", "auc_mt", "delta_auc", "brier_m", "brier_mt", "ece_m", "ece_mt", "delta_ece"]:
            assert key in result.metrics, f"Missing metrics key: {key}"


# ---------------------------------------------------------------------------
# Test 18: Null report unavailable when no targets
# ---------------------------------------------------------------------------

class TestNullReportNoTargets:
    def test_null_unavailable_no_targets(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, _ = join_signal_m_t_rows(m, t)
        metrics = {"explicit_targets_available": False}
        nr = build_signal_null_report(j, metrics)
        assert nr["status"] == "unavailable_no_explicit_targets"
        assert nr["nulls_passed"] is False
        assert "no targets were fabricated" in nr["note"]


# ---------------------------------------------------------------------------
# Test 19: Ablation report includes all required ablations
# ---------------------------------------------------------------------------

class TestAblationReportStructure:
    def test_all_ablations_present(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, _ = join_signal_m_t_rows(m, t)
        metrics = {"explicit_targets_available": False}
        abr = build_signal_ablation_report(j, metrics)
        for ab in [
            "M_only", "M_plus_q_net", "M_plus_q_abs", "M_plus_f_dress",
            "M_plus_defect_density", "M_plus_topology_quality", "M_plus_all_T"
        ]:
            assert ab in abr["ablation_entries"], f"Missing ablation: {ab}"


# ---------------------------------------------------------------------------
# Test 20: Ablation entries unavailable when no targets
# ---------------------------------------------------------------------------

class TestAblationEntriesNoTargets:
    def test_ablation_entries_unavailable(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, _ = join_signal_m_t_rows(m, t)
        metrics = {"explicit_targets_available": False}
        abr = build_signal_ablation_report(j, metrics)
        for entry in abr["ablation_entries"].values():
            assert entry["status"] == "unavailable_no_explicit_targets"
            assert entry["auc"] is None


# ---------------------------------------------------------------------------
# Test 21: Alignment report includes required fields and alignment_passed
# ---------------------------------------------------------------------------

class TestAlignmentReport:
    def test_required_fields_present(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, w = join_signal_m_t_rows(m, t)
        ar = build_signal_alignment_report(j, m, t, w)
        for key in [
            "n_m_rows", "n_t_rows", "n_joined_rows",
            "missing_t_for_m", "extra_t_rows",
            "duplicate_m_keys", "duplicate_t_keys",
            "alignment_passed", "warnings",
        ]:
            assert key in ar, f"Missing alignment key: {key}"

    def test_alignment_passed_true_for_clean_join(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, w = join_signal_m_t_rows(m, t)
        ar = build_signal_alignment_report(j, m, t, w)
        assert ar["alignment_passed"] is True


# ---------------------------------------------------------------------------
# Test 22: Artifact report includes required fields
# ---------------------------------------------------------------------------

class TestArtifactReport:
    def test_required_fields_present(self):
        m = [_mk_m_row(i) for i in range(4)]
        t = [_mk_t_row(i) for i in range(4)]
        j, _ = join_signal_m_t_rows(m, t)
        ar = build_signal_artifact_report(j)
        for key in [
            "mean_artifact_score_m", "max_artifact_score_m",
            "mean_topology_quality", "low_topology_quality_rows",
            "high_artifact_rows", "artifact_dominance",
            "m_feature_status_counts", "t_topology_status_counts",
        ]:
            assert key in ar, f"Missing artifact key: {key}"


# ---------------------------------------------------------------------------
# Test 23: Artifact dominance on high artifact score
# ---------------------------------------------------------------------------

class TestArtifactDominanceHighArtifact:
    def test_high_artifact_score_triggers_dominance(self):
        m_row = _mk_m_row(0)
        m_row["artifact_score"] = "0.9"  # very high
        t_row = _mk_t_row(0)
        t_row["topology_quality"] = "0.8"
        j, _ = join_signal_m_t_rows([m_row], [t_row])
        j[0].artifact_score_m = 0.9
        ar = build_signal_artifact_report(j)
        assert ar["artifact_dominance"] is True


# ---------------------------------------------------------------------------
# Test 24: Artifact dominance on low topology quality
# ---------------------------------------------------------------------------

class TestArtifactDominanceLowTopology:
    def test_low_topology_quality_triggers_dominance(self):
        m = [_mk_m_row(i) for i in range(3)]
        t = [_mk_t_row(i) for i in range(3)]
        j, _ = join_signal_m_t_rows(m, t)
        for row in j:
            row.topology_quality = 0.1  # below 0.25
        ar = build_signal_artifact_report(j)
        assert ar["artifact_dominance"] is True


# ---------------------------------------------------------------------------
# Test 25: write_signal_mt_outputs writes all eight files
# ---------------------------------------------------------------------------

class TestWriteOutputsAllEight:
    def test_all_eight_written(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=4)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        expected = {
            "features_joined_signal", "metrics_signal_mt",
            "nulls_signal", "ablations_signal",
            "alignment_report", "artifact_report",
            "omega_event", "report",
        }
        assert expected == set(outputs.keys())
        for name, path in outputs.items():
            assert Path(path).exists(), f"Missing: {name}"


# ---------------------------------------------------------------------------
# Test 26: JSON outputs parse
# ---------------------------------------------------------------------------

class TestJsonOutputsParse:
    def test_json_parseable(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        for name in ["metrics_signal_mt", "nulls_signal", "ablations_signal",
                     "alignment_report", "artifact_report", "omega_event"]:
            with open(outputs[name]) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{name} not a dict"


# ---------------------------------------------------------------------------
# Test 27: features_joined_signal.csv contains required columns
# ---------------------------------------------------------------------------

class TestJoinedCsvColumns:
    def test_required_columns(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        with open(outputs["features_joined_signal"], newline="") as f:
            header = next(csv.reader(f))
        for col in _JOINED_COLS:
            assert col in header, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Test 28: report.md contains cautious terms
# ---------------------------------------------------------------------------

class TestReportCautiousTerms:
    def test_cautious_terms(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        text = Path(outputs["report"]).read_text()
        assert "controlled signal-level residual benchmarking" in text
        assert "Level M signal features" in text
        assert "Level T topology telemetry" in text

    def test_report_title_and_next_step(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        text = Path(outputs["report"]).read_text()
        assert "EEG Signal-Level M+T Residual Benchmark" in text
        assert "explicit validated labels" in text or "explicit validated" in text


# ---------------------------------------------------------------------------
# Test 29: report.md does not contain banned phrases
# ---------------------------------------------------------------------------

class TestReportNoBannedPhrases:
    def test_no_banned_phrases(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        text = Path(outputs["report"]).read_text().lower()
        for phrase in [
            "proves consciousness", "consciousness proven", "soul proven",
            "afterlife proven", "liberation detected", "ontology solved",
            "ultimate reality", "q equals self", "q equals soul",
            "q_abs equals suffering", "f_dress equals karma",
        ]:
            assert phrase not in text, f"Banned phrase found: {phrase!r}"


# ---------------------------------------------------------------------------
# Test 30: CLI mock fixture smoke returns 0 and writes eight files
# ---------------------------------------------------------------------------

class TestCliMockFixture:
    def test_cli_returns_0(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
                "--mock-fixture",
                "--out", str(tmp_path / "cli_out"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

    def test_cli_writes_eight_files(self, tmp_path):
        out_dir = str(tmp_path / "cli_out2")
        subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
                "--mock-fixture",
                "--out", out_dir,
            ],
            capture_output=True,
            text=True,
        )
        out_path = Path(out_dir)
        for fname in [
            "features_joined_signal.csv", "metrics_signal_mt.json",
            "nulls_signal.json", "ablations_signal.json",
            "alignment_report.json", "artifact_report.json",
            "omega_event.json", "report.md",
        ]:
            assert (out_path / fname).exists(), f"Missing: {fname}"


# ---------------------------------------------------------------------------
# Test 31: CLI missing inputs fails cleanly with required message
# ---------------------------------------------------------------------------

class TestCliMissingInputs:
    def test_missing_inputs_fails_nonzero(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
                "--m-features", str(tmp_path / "nope_m.csv"),
                "--t-features", str(tmp_path / "nope_t.csv"),
                "--out", str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_missing_inputs_error_message(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
                "--m-features", str(tmp_path / "nope_m.csv"),
                "--t-features", str(tmp_path / "nope_t.csv"),
                "--out", str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        assert (
            "run_eeg_level_m_signal" in combined or
            "mock-fixture" in combined or
            "mock_fixture" in combined
        )


# ---------------------------------------------------------------------------
# Test 32: config exists and contains required content
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_exists(self):
        assert Path("configs/btc_icft/eeg_signal_mt.yaml").exists()

    def test_config_outputs(self):
        text = Path("configs/btc_icft/eeg_signal_mt.yaml").read_text()
        for out in [
            "features_joined_signal.csv", "metrics_signal_mt.json",
            "nulls_signal.json", "ablations_signal.json",
            "alignment_report.json", "artifact_report.json",
            "omega_event.json", "report.md",
        ]:
            assert out in text, f"Config missing output: {out}"

    def test_config_join_keys(self):
        text = Path("configs/btc_icft/eeg_signal_mt.yaml").read_text()
        for k in ["dataset_id", "row_id", "window_id", "sample_start", "sample_end"]:
            assert k in text, f"Config missing join key: {k}"

    def test_config_promotion_gate(self):
        text = Path("configs/btc_icft/eeg_signal_mt.yaml").read_text()
        assert "require_explicit_targets" in text
        assert "min_delta_auc" in text
        assert "require_no_artifact_dominance" in text

    def test_config_guardrails(self):
        text = Path("configs/btc_icft/eeg_signal_mt.yaml").read_text()
        for g in [
            "no_target_fabrication", "no_label_inference",
            "no_legacy_mt_real_change", "q_not_self", "q_not_soul",
        ]:
            assert g in text, f"Config missing guardrail: {g}"


# ---------------------------------------------------------------------------
# Test 33: Legacy mt_real files NOT imported or required
# ---------------------------------------------------------------------------

class TestNoLegacyImport:
    def test_legacy_mt_real_not_in_module(self):
        import importlib
        import ast
        src = Path("sciencer_d/btc_icft/evaluation/eeg_signal_residual.py").read_text()
        assert "ds005620_residual" not in src
        assert "run_ds005620_mt_real" not in src
        assert "mt_real" not in src


# ---------------------------------------------------------------------------
# Test 34: No target fabrication from labels/state/text
# ---------------------------------------------------------------------------

class TestNoTargetFabrication:
    def test_sedation_label_no_y(self):
        m_rows = [_mk_m_row(i, y="", label="sedated") for i in range(3)]
        t_rows = [_mk_t_row(i) for i in range(3)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        for row in joined:
            assert row.y is None

    def test_responsiveness_label_no_y(self):
        m_rows = [_mk_m_row(i, y="", label="responsive") for i in range(3)]
        t_rows = [_mk_t_row(i) for i in range(3)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        result = evaluate_signal_mt_residual(joined, "DS005620", m_rows=m_rows, t_rows=t_rows)
        assert "no explicit targets" in result.promotion_reason


# ---------------------------------------------------------------------------
# Test 35: Optional y from M input is preserved if explicit
# ---------------------------------------------------------------------------

class TestYPreserved:
    def test_explicit_y_preserved(self):
        m_rows = [_mk_m_row(i, y=str(i % 2)) for i in range(4)]
        t_rows = [_mk_t_row(i) for i in range(4)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        for i, row in enumerate(joined):
            assert row.y == i % 2

    def test_y_missing_in_csv_preserved_as_none(self):
        # Write M CSV without y column
        m_rows = [_mk_m_row(i) for i in range(3)]
        t_rows = [_mk_t_row(i) for i in range(3)]
        joined, _ = join_signal_m_t_rows(m_rows, t_rows)
        for row in joined:
            assert row.y is None


# ---------------------------------------------------------------------------
# Additional: safe-text guardrail
# ---------------------------------------------------------------------------

class TestSafeTextGuardrail:
    def test_safe_claim_passes(self):
        _validate_safe_text(_SAFE_CLAIM)

    def test_banned_phrase_raises(self):
        with pytest.raises(ValueError, match="consciousness"):
            _validate_safe_text("This proves consciousness.")

    def test_omega_event_safe_claim(self, tmp_path):
        result, joined, _, _ = _make_result(tmp_path, n=3)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined)
        with open(outputs["omega_event"]) as f:
            data = json.load(f)
        assert "controlled signal-level residual benchmarking" in data["safe_claim"]
        assert data["promoted"] is False
