"""P1 reliability: fail-closed NaN, explicit sample_rate, watermarks, q_* quarantine."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from adapters.mne_bids_feature_recipe import (
    _RECIPE_EVIDENCE_CLASS,
    _RECIPE_RUN_MODE,
    compute_features_for_epochs,
    write_recipe_outputs,
)
from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1
from scripts.scan_mock_empirical_claims import main as scan_main
from scripts.scan_mock_empirical_claims import scan_file
from sciencer_d.btc_icft.io.eeg_signal_blocks import (
    _PROBE_EVIDENCE_CLASS,
    _PROBE_RUN_MODE,
    parse_fixture_signal_file,
    probe_signal_paths,
    write_signal_probe_outputs,
)
from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    build_mock_ds005620_level_m_rows,
    evaluate_level_m_baseline,
    write_level_m_outputs,
)
from sciencer_d.btc_icft.level_t.ds005620_features import (
    _MOCK_T_METRIC_KIND,
    build_mock_ds005620_level_t_rows,
    evaluate_mt_residual,
    join_level_m_and_t_rows,
    write_mt_outputs,
)
from sciencer_d.btc_icft.level_t.eeg_signal_topology import (
    _METRIC_KIND,
    EEGLevelTSignalTopologyRow,
    compute_signal_topology_for_window,
    observed_proxy_metrics,
)


_SFREQ = 128.0


def test_partial_nan_channel_skipped_not_imputed():
    """Partial-NaN channels must not be nan_to_num'd into spectral features."""
    good = np.sin(2 * np.pi * 10 * np.arange(256) / _SFREQ)
    bad = good.copy()
    bad[10] = np.nan
    epoch = np.stack([good, bad], axis=0)
    result = compute_features_for_epochs(
        [epoch],
        sfreq=_SFREQ,
        requested_features=["spectral.alpha_power", "qc.missing_value_fraction"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    # Only the fully-finite channel contributes; result is finite (not fabricated from NaNs).
    assert math.isfinite(result["spectral.alpha_power"])
    assert result["qc.missing_value_fraction"] > 0.0

    all_nan = np.full((1, 256), np.nan)
    emptyish = compute_features_for_epochs(
        [all_nan],
        sfreq=_SFREQ,
        requested_features=["spectral.alpha_power"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    assert math.isnan(emptyish["spectral.alpha_power"])


def test_recipe_outputs_carry_non_empirical_watermarks(tmp_path: Path):
    from adapters.mne_bids_feature_recipe import run_feature_recipe

    rng = np.random.RandomState(0)
    n = 128
    t = np.arange(n) / _SFREQ
    epoch = [(rng.randn(n) * 1e-5 + 0.01 * np.sin(2 * np.pi * 10 * t)).tolist()] * 2
    table_payload = {
        "sfreq": _SFREQ,
        "channels": ["C3", "C4"],
        "subjects": {
            "sub-01": {
                "session": None,
                "epochs": {
                    "rest_marker": [epoch, epoch],
                    "task_marker": [epoch, epoch],
                },
            },
            "sub-02": {
                "session": None,
                "epochs": {
                    "rest_marker": [epoch, epoch],
                    "task_marker": [epoch, epoch],
                },
            },
        },
    }
    table = tmp_path / "epoch_table.json"
    table.write_text(json.dumps(table_payload), encoding="utf-8")
    spec = FeatureRecipeSpecV1.make(
        dataset_id="p1_watermark_ds",
        feature_set_id="mne_bids_spectral_v1",
        source_state="rest",
        target_state="task",
        requested_features=["spectral.alpha_power", "qc.valid_epoch_count"],
        max_subjects=5,
        max_runs=5,
        max_epochs_per_state=10,
        max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={
            "spectral.alpha_power": "Mean relative alpha-band power over valid epochs.",
            "qc.valid_epoch_count": "Count of valid epochs used per state.",
        },
        input_kind="epoch_table",
        limitations=["synthetic fixture test"],
        provenance="p1 watermark unit test",
    )
    result = run_feature_recipe(spec, epoch_table_path=table)
    # write_recipe_outputs requires a repo-relative target root.
    out_rel = Path("outputs/feature_recipes/p1-watermark-test")
    try:
        _features, mapping_path, _manifest, summary_path = write_recipe_outputs(
            spec, result, out_rel
        )
        mapping = json.loads(mapping_path.read_text())
        summary = json.loads(summary_path.read_text())
        assert mapping["evidence_class"] == _RECIPE_EVIDENCE_CLASS
        assert mapping["run_mode"] == _RECIPE_RUN_MODE
        assert mapping["scientific_pass"] is False
        assert mapping["metrics_are_empirical"] is False
        assert mapping["preprocessing_provenance"]["nan_imputation"] == "forbidden"
        assert summary["evidence_class"] == _RECIPE_EVIDENCE_CLASS
        assert summary["run_mode"] == _RECIPE_RUN_MODE
    finally:
        import shutil

        shutil.rmtree(out_rel, ignore_errors=True)


def test_parse_fixture_requires_explicit_sample_rate(tmp_path: Path):
    bare = tmp_path / "bare.csv"
    bare.write_text("0.1,0.2\n0.3,0.4\n", encoding="utf-8")
    missing = parse_fixture_signal_file(str(bare))
    assert missing.readable is False
    assert "missing_sample_rate_hz" in missing.errors
    assert missing.sample_rate_hz is None
    assert missing.scientific_eligible is False

    caller = parse_fixture_signal_file(str(bare), sample_rate_hz=42.0)
    assert caller.readable is True
    assert caller.sample_rate_hz == pytest.approx(42.0)
    assert caller.sample_rate_source == "caller_explicit"
    assert caller.scientific_eligible is False

    headed = tmp_path / "headed.csv"
    headed.write_text("# sample_rate: 250.0\n0.1,0.2\n0.3,0.4\n", encoding="utf-8")
    hdr = parse_fixture_signal_file(str(headed))
    assert hdr.readable is True
    assert hdr.sample_rate_hz == pytest.approx(250.0)
    assert hdr.sample_rate_source == "header"
    assert hdr.scientific_eligible is True


def test_probe_defaults_do_not_invent_100hz(tmp_path: Path):
    bare = tmp_path / "bare.csv"
    bare.write_text("0.1,0.2\n0.3,0.4\n", encoding="utf-8")
    result = probe_signal_paths([str(bare)])
    assert result.n_readable_files == 0
    assert result.skipped_files[0]["reason"] == "missing_sample_rate_hz"
    assert result.evidence_class == _PROBE_EVIDENCE_CLASS
    assert result.run_mode == _PROBE_RUN_MODE
    assert result.scientific_pass is False
    assert result.metrics_are_empirical is False

    outs = write_signal_probe_outputs(result, str(tmp_path / "probe_out"))
    inventory = json.loads(Path(outs["signal_block_inventory"]).read_text())
    assert inventory["evidence_class"] == _PROBE_EVIDENCE_CLASS
    report = Path(outs["report"]).read_text().lower()
    assert "evidence_class" in report
    assert "metrics_are_empirical" in report


def test_observed_proxy_metrics_rejects_null_and_invalid():
    skipped = EEGLevelTSignalTopologyRow(
        dataset_id="DS",
        row_id="r",
        source_file="x.csv",
        window_id="w",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=0,
        n_samples=0,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=None,
        mean_diff_proxy_abs=None,
        mean_diff_proxy_excess=None,
        defect_density=None,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=None,
        topology_status="skipped_no_samples",
        metric_kind=_METRIC_KIND,
        q_net=None,
        q_abs=None,
        f_dress=None,
        is_valid=False,
    )
    assert observed_proxy_metrics(skipped) is None

    # Zeros with is_valid=False must not be treated as observed charge.
    zero_invalid = EEGLevelTSignalTopologyRow(
        dataset_id="DS",
        row_id="r2",
        source_file="x.csv",
        window_id="w",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=4,
        n_samples=10,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=0.0,
        mean_diff_proxy_abs=0.0,
        mean_diff_proxy_excess=0.0,
        defect_density=0.0,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=0.0,
        topology_status="skipped_invalid_window",
        metric_kind=_METRIC_KIND,
        q_net=0.0,
        q_abs=0.0,
        f_dress=0.0,
        is_valid=False,
    )
    assert observed_proxy_metrics(zero_invalid) is None

    valid = EEGLevelTSignalTopologyRow(
        dataset_id="DS",
        row_id="r3",
        source_file="x.csv",
        window_id="w",
        window_start_s=0.0,
        window_end_s=1.0,
        sample_start=0,
        sample_end=10,
        n_channels=4,
        n_samples=10,
        sample_rate_hz=100.0,
        mean_diff_proxy_net=0.1,
        mean_diff_proxy_abs=0.2,
        mean_diff_proxy_excess=0.05,
        defect_density=0.01,
        n_triangles=4,
        n_valid_triangles=2,
        topology_quality=0.5,
        topology_status="ok",
        metric_kind=_METRIC_KIND,
        q_net=0.1,
        q_abs=0.2,
        f_dress=0.05,
        is_valid=True,
    )
    observed = observed_proxy_metrics(valid)
    assert observed is not None
    assert observed["metric_kind"] == _METRIC_KIND
    assert observed["q_net_alias"] == pytest.approx(0.1)


def test_topology_window_missing_sample_rate_skips(tmp_path: Path):
    sig = tmp_path / "nosr.csv"
    sig.write_text("0.1,0.2,0.3,0.4\n" * 20, encoding="utf-8")
    window = {
        "file_path": str(sig),
        "row_id": "r1",
        "window_id": "win-0",
        "window_start_s": "0.0",
        "window_end_s": "1.0",
        "sample_start": "0",
        "sample_end": "10",
        "n_channels": "4",
        "n_samples": "10",
        "sample_rate_hz": "0",
        "status": "full_window",
    }
    row = compute_signal_topology_for_window("DS005620", window)
    assert row.is_valid is False
    assert row.q_net is None
    assert observed_proxy_metrics(row) is None


def test_mock_level_t_rows_watermarked_non_empirical(tmp_path: Path):
    t_rows = build_mock_ds005620_level_t_rows()
    assert all(r.metric_kind == _MOCK_T_METRIC_KIND for r in t_rows)
    assert all(r.evidence_class == "synthetic_circular_demonstration" for r in t_rows)
    assert all(r.run_mode == "mock" for r in t_rows)

    m_rows = build_mock_ds005620_level_m_rows()
    joined = join_level_m_and_t_rows(m_rows, t_rows)
    assert all(r.metric_kind == _MOCK_T_METRIC_KIND for r in joined)
    result = evaluate_mt_residual(joined, task="awake_vs_sedated")
    assert result.metrics_are_empirical is False
    assert result.evidence_class == "synthetic_circular_demonstration"
    assert result.run_mode == "mock"
    outs = write_mt_outputs(result, str(tmp_path / "mt"))
    metrics = json.loads(Path(outs["metrics_mt.json"]).read_text())
    assert metrics["metrics_are_empirical"] is False
    assert metrics["evidence_class"] == "synthetic_circular_demonstration"
    report = Path(outs["report.md"]).read_text().lower()
    assert "evidence_class" in report
    assert "metric_kind" in report


def test_mock_empirical_claim_scanner_flags_violation(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "run_mode": "mock",
                "evidence_class": "empirical",
                "metrics_are_empirical": True,
            }
        ),
        encoding="utf-8",
    )
    violations = scan_file(bad)
    assert violations
    assert scan_main([str(tmp_path)]) == 1

    good = tmp_path / "good.json"
    good.write_text(
        json.dumps(
            {
                "run_mode": "mock",
                "evidence_class": "synthetic_circular_demonstration",
                "metrics_are_empirical": False,
                "scientific_pass": False,
            }
        ),
        encoding="utf-8",
    )
    # Only scan the good file alone
    assert scan_main([str(good)]) == 0


def test_level_m_mock_outputs_still_non_empirical(tmp_path: Path):
    rows = build_mock_ds005620_level_m_rows()
    res = evaluate_level_m_baseline(rows, task="awake_vs_sedated")
    outs = write_level_m_outputs(res, str(tmp_path))
    metrics_path = Path(outs["metrics_m.json"])
    metrics = json.loads(metrics_path.read_text())
    assert metrics["metrics_are_empirical"] is False
    assert metrics["run_mode"] == "mock"
    assert scan_main([metrics_path]) == 0
