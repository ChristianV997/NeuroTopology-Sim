"""Streaming baseline comparison and correctness-vs-performance split."""
from __future__ import annotations

from tools.benchmarking.post_merge_pipeline.harness import run_all
from tools.benchmarking.post_merge_pipeline.streaming_compare import (
    compare_streaming_baseline,
    load_recorded_streaming_baseline,
)


def test_recorded_streaming_baseline_is_readable():
    recorded = load_recorded_streaming_baseline()
    assert recorded is not None
    assert recorded["phase"] == "baseline"
    assert recorded["save_manifest"]["elapsed_s"] is not None


def test_comparison_uses_nulls_not_zeros_for_incompatible_probes():
    report = run_all(seed=0, size=8, repetitions=1)
    cmp_ = compare_streaming_baseline(report)
    assert cmp_["evidence_class"] == "performance_only"
    assert cmp_["synthetic"] is True
    assert cmp_["recorded_present"] is True
    probes = cmp_["probes"]
    assert "bids.preprocess_read_s" not in probes
    assert probes["recorded_save_manifest_200_writes_s"] > 0
    assert "manifest_recovery" in cmp_["compatible_targets"]


def test_correctness_separated_from_telemetry():
    report = run_all(seed=0, size=8, repetitions=1)
    for rec in report["results"]:
        det = rec["deterministic"]
        tel = rec["telemetry"]
        assert "checksum_match" in det
        assert "runtime_best_s" not in det
        assert "runtime_best_s" in tel["candidate"]
        assert rec["measurement_quality"]["missing_metrics_are_null"] is True
