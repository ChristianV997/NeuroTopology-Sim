"""NER-1 reliability guards: no circular-empirical claims, no zero-filled skips."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from adapters.mne_bids_feature_recipe import compute_features_for_epochs
from pipelines.run_eeg import _infer_metadata
from sciencer_d.btc_icft.io.eeg_signal_blocks import (
    parse_fixture_signal_file,
    probe_signal_paths,
    write_signal_probe_outputs,
)
from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    build_mock_ds005620_level_m_rows,
    evaluate_level_m_baseline,
    write_level_m_outputs,
)
from sciencer_d.btc_icft.level_t.eeg_signal_topology import (
    _METRIC_KIND,
    EEGLevelTSignalTopologyRow,
    compute_signal_topology_for_window,
    compute_topology_from_channels,
)
from tools.check_eeg_artifact_watermarks import main as watermark_scan_main
from tools.check_eeg_artifact_watermarks import scan_json


def test_mock_baseline_is_watermarked_non_empirical(tmp_path: Path):
    rows = build_mock_ds005620_level_m_rows()
    assert all(r.evidence_class == "synthetic_circular_demonstration" for r in rows)
    assert all(r.signal_provenance == "label_conditioned_toy_vector" for r in rows)
    res = evaluate_level_m_baseline(rows, task="awake_vs_sedated")
    assert res.metrics_are_empirical is False
    assert res.circular_label_conditioned_signal is True
    assert "empirical EEG" not in res.safe_claim.lower() or "not empirical" in res.safe_claim.lower()
    outs = write_level_m_outputs(res, str(tmp_path))
    report = Path(outs["report.md"]).read_text().lower()
    assert "operational empirical baseline" not in report
    assert "synthetic_circular_demonstration" in report
    metrics = json.loads(Path(outs["metrics_m.json"]).read_text())
    assert metrics["evidence_class"] == "synthetic_circular_demonstration"
    assert metrics["run_mode"] == "mock"
    assert metrics["metrics_are_empirical"] is False
    assert watermark_scan_main([str(tmp_path)]) == 0


def test_skipped_window_metrics_are_null_not_zero(tmp_path: Path):
    window = {
        "file_path": str(tmp_path / "missing.csv"),
        "row_id": "ghost",
        "window_id": "win-0",
        "window_start_s": "0.0",
        "window_end_s": "1.0",
        "sample_start": "0",
        "sample_end": "50",
        "n_channels": "4",
        "n_samples": "50",
        "sample_rate_hz": "100.0",
        "status": "full_window",
    }
    row = compute_signal_topology_for_window("DS005620", window)
    assert row.topology_status.startswith("skipped_")
    assert row.is_valid is False
    assert row.mean_diff_proxy_net is None
    assert row.mean_diff_proxy_abs is None
    assert row.mean_diff_proxy_excess is None
    assert row.q_net is None
    assert row.q_abs is None
    assert row.f_dress is None
    assert row.defect_density is None
    assert row.topology_quality is None
    assert row.metric_kind == _METRIC_KIND


def test_empty_channel_compute_returns_null_metrics():
    result = compute_topology_from_channels([])
    assert result == (None, None, None, None, 0, 0, None)


def test_run_eeg_does_not_infer_state_from_path_keywords():
    meta = _infer_metadata(
        Path("/data/ds005620/sub-01/ses-01/eeg/sub-01_task-rest_anesthesia_awake.edf"),
        "ds005620",
    )
    assert meta["subject_id"] == "01"
    assert meta["condition"] == "rest"
    assert meta["state_label"] == "unknown"
    assert meta["label_inference"] == "forbidden"


def test_consumers_must_check_metric_kind_and_is_valid_before_q_aliases():
    """Legacy q_* dual-write is not winding charge; nulls stay null when invalid."""
    valid = EEGLevelTSignalTopologyRow(
        dataset_id="ds",
        row_id="r1",
        source_file="x.csv",
        window_id="w0",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=4,
        n_samples=10,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=0.25,
        mean_diff_proxy_abs=0.5,
        mean_diff_proxy_excess=0.1,
        defect_density=0.0,
        n_triangles=4,
        n_valid_triangles=4,
        topology_quality=0.8,
        topology_status="ok",
        metric_kind=_METRIC_KIND,
        is_valid=True,
    )
    assert valid.metric_kind == "channel_mean_correlation_proxy"
    assert valid.metric_kind != "phase_grid_topology"
    assert valid.q_net == valid.mean_diff_proxy_net
    assert valid.q_abs == valid.mean_diff_proxy_abs
    assert valid.f_dress == valid.mean_diff_proxy_excess

    invalid = EEGLevelTSignalTopologyRow(
        dataset_id="ds",
        row_id="r2",
        source_file="missing.csv",
        window_id="w1",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=4,
        n_samples=10,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=None,
        mean_diff_proxy_abs=None,
        mean_diff_proxy_excess=None,
        defect_density=None,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=None,
        topology_status="skipped_unreadable_source",
        metric_kind=_METRIC_KIND,
        q_net=None,
        q_abs=None,
        f_dress=None,
        is_valid=False,
    )
    assert invalid.is_valid is False
    assert invalid.q_net is None
    assert invalid.mean_diff_proxy_net is None
    # Consumer contract: never treat null/invalid q_* as observed zero charge.
    assert not (invalid.is_valid and invalid.q_net == 0.0)


def test_fixture_parser_requires_sample_rate_no_silent_100(tmp_path: Path):
    p = tmp_path / "no_sr.csv"
    p.write_text("0.1,0.2\n0.3,0.4\n", encoding="utf-8")
    missing = parse_fixture_signal_file(str(p))
    assert missing.readable is False
    assert missing.sample_rate_hz is None
    assert any("missing_sample_rate_hz" in e for e in missing.errors)
    assert missing.scientific_eligible is False

    header = tmp_path / "with_sr.csv"
    header.write_text("# sample_rate: 250.0\n0.1,0.2\n0.3,0.4\n", encoding="utf-8")
    ok = parse_fixture_signal_file(str(header))
    assert ok.readable is True
    assert ok.sample_rate_hz == 250.0
    assert ok.sample_rate_source == "header"
    assert ok.scientific_eligible is True

    explicit = parse_fixture_signal_file(str(p), sample_rate_hz=42.0)
    assert explicit.readable is True
    assert explicit.sample_rate_hz == 42.0
    assert explicit.sample_rate_source == "caller_explicit"
    assert explicit.scientific_eligible is False


def test_probe_artifacts_carry_evidence_watermarks(tmp_path: Path):
    csv_path = tmp_path / "sig.csv"
    csv_path.write_text(
        "# channels: 2\n# sample_rate: 100.0\n0.1,0.2\n0.3,0.4\n0.5,0.6\n",
        encoding="utf-8",
    )
    result = probe_signal_paths([str(csv_path)], window_seconds=0.02, max_windows_per_file=1)
    assert result.evidence_class == "fixture_signal_block_scaffold"
    assert result.scientific_pass is False
    outs = write_signal_probe_outputs(result, str(tmp_path / "out"))
    inventory = json.loads(Path(outs["signal_block_inventory"]).read_text())
    assert inventory["evidence_class"] == "fixture_signal_block_scaffold"
    assert inventory["run_mode"]
    assert inventory["scientific_pass"] is False
    report = Path(outs["report"]).read_text().lower()
    assert "evidence watermark" in report
    assert "evidence_class" in report
    assert watermark_scan_main([str(tmp_path / "out")]) == 0


def test_feature_recipe_skips_partial_nan_without_nan_to_num():
    clean = np.ones((2, 64), dtype=float)
    dirty = np.ones((2, 64), dtype=float)
    dirty[0, 10] = float("nan")
    bands = {"alpha": [8.0, 13.0]}
    clean_out = compute_features_for_epochs(
        [clean],
        sfreq=64.0,
        requested_features=["spectral.alpha_power", "qc.missing_value_fraction"],
        frequency_bands=bands,
    )
    dirty_out = compute_features_for_epochs(
        [dirty],
        sfreq=64.0,
        requested_features=["spectral.alpha_power", "qc.missing_value_fraction"],
        frequency_bands=bands,
    )
    assert dirty_out["qc.missing_value_fraction"] > 0.0
    # Contaminated channel is skipped; remaining finite channel still contributes.
    assert math.isfinite(dirty_out["spectral.alpha_power"])
    # All-NaN epoch yields NaN spectral feature (eligibility-blocking).
    all_nan = np.full((2, 64), np.nan)
    blocked = compute_features_for_epochs(
        [all_nan],
        sfreq=64.0,
        requested_features=["spectral.alpha_power"],
        frequency_bands=bands,
    )
    assert math.isnan(blocked["spectral.alpha_power"])
    assert math.isfinite(clean_out["spectral.alpha_power"])


def test_invalid_row_forces_null_q_aliases_even_if_numeric_supplied():
    """Stricter quarantine: is_valid=False / skipped_* nulls all Q aliases."""
    row = EEGLevelTSignalTopologyRow(
        dataset_id="ds",
        row_id="r-bad",
        source_file="x.csv",
        window_id="w0",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=4,
        n_samples=10,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=9.9,
        mean_diff_proxy_abs=8.8,
        mean_diff_proxy_excess=7.7,
        defect_density=0.5,
        n_triangles=4,
        n_valid_triangles=4,
        topology_quality=0.9,
        topology_status="skipped_missing_sample_rate",
        q_net=9.9,
        q_abs=8.8,
        f_dress=7.7,
        is_valid=True,  # post_init must force False + null
    )
    assert row.is_valid is False
    assert row.metric_kind == _METRIC_KIND
    assert row.q_net is None
    assert row.q_abs is None
    assert row.f_dress is None
    assert row.mean_diff_proxy_net is None
    assert row.defect_density is None


def test_scanner_rejects_empirical_claim_on_mock(tmp_path: Path):
    bad = tmp_path / "metrics_m.json"
    bad.write_text(
        json.dumps(
            {
                "evidence_class": "synthetic_circular_demonstration",
                "run_mode": "mock",
                "metrics_are_empirical": True,
                "signal_provenance": "label_conditioned_toy_vector",
            }
        ),
        encoding="utf-8",
    )
    errs = scan_json(bad)
    assert any("metrics_are_empirical" in e for e in errs)
    assert watermark_scan_main([str(tmp_path)]) == 1


def test_scanner_rejects_q_alias_without_metric_kind(tmp_path: Path):
    path = tmp_path / "omega_event.json"
    path.write_text(
        json.dumps(
            {
                "event_type": "level_t_signal_topology",
                "evidence_class": "level_t_signal_proxy_scaffold",
                "run_mode": "offline_fixture",
                "q_net": 1.0,
                "scientific_pass": False,
            }
        ),
        encoding="utf-8",
    )
    errs = scan_json(path)
    assert any("metric_kind" in e for e in errs)


def test_level_t_missing_sample_rate_skips(tmp_path: Path):
    src = tmp_path / "norate.csv"
    src.write_text("0.1,0.2,0.3\n0.2,0.3,0.4\n", encoding="utf-8")
    window = {
        "file_path": str(src),
        "row_id": "r0",
        "window_id": "win-0",
        "window_start_s": "0.0",
        "window_end_s": "1.0",
        "sample_start": "0",
        "sample_end": "2",
        "n_channels": "3",
        "n_samples": "2",
        "sample_rate_hz": "0",
        "status": "full_window",
    }
    row = compute_signal_topology_for_window("DS005620", window)
    assert row.topology_status == "skipped_missing_sample_rate"
    assert row.is_valid is False
    assert row.q_net is None
    assert row.metric_kind == _METRIC_KIND
