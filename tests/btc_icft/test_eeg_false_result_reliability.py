"""NER-1 reliability guards: no circular-empirical claims, no zero-filled skips."""

from __future__ import annotations

from pathlib import Path

from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    build_mock_ds005620_level_m_rows,
    evaluate_level_m_baseline,
    write_level_m_outputs,
)
from sciencer_d.btc_icft.level_t.eeg_signal_topology import (
    _METRIC_KIND,
    compute_signal_topology_for_window,
    compute_topology_from_channels,
)
from pipelines.run_eeg import _infer_metadata


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
