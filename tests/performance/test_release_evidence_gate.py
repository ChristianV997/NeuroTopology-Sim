"""Tests for the performance release-evidence gate.

Performance scaffolding only — never scientific evidence.
"""
from __future__ import annotations

import json
import math

from tools.performance.release_evidence_gate import (
    GATE_SCHEMA_VERSION,
    GateThresholds,
    ReleaseDecision,
    dumps,
    evaluate_release_evidence,
    render_markdown,
)


def _norm(**overrides):
    rec = {
        "schema_version": "1.0",
        "benchmark_id": "stream-bounded",
        "source_commit": "abc123",
        "branch": "main",
        "host": "host-a",
        "platform": "linux",
        "python_version": "3.12.3",
        "backend": "numpy",
        "input_shape": {"channels": 32, "samples": 200000, "dtype": "float64"},
        "chunk_size": 16384,
        "repetitions": 5,
        "checksum": 1.777827,
        "correctness_status": "ok",
        "runtime_s": 0.050,
        "wall_best_s": 0.048,
        "wall_mean_s": 0.050,
        "tracemalloc_peak_bytes": 8_000_000,
        "child_rss_bytes": 210_000_000,
        "parent_sampled_rss_bytes": 212_000_000,
        "timeout_status": False,
        "process_exit_status": 0,
        "optional_dependency_state": None,
        "evidence_class": "performance_only",
        "synthetic": True,
        "raw_outcome": "pass",
    }
    rec.update(overrides)
    return rec


def test_valid_same_host_comparison():
    report = evaluate_release_evidence(
        _norm(),
        _norm(runtime_s=0.051, tracemalloc_peak_bytes=8_100_000, child_rss_bytes=211_000_000),
    )
    assert report.decision == ReleaseDecision.EVIDENCE_READY
    assert report.comparable is True
    assert report.evidence_class == "performance_only"
    assert report.synthetic is True
    assert report.baseline_checksum == 1.777827
    assert report.candidate_checksum == 1.777827
    assert "tracemalloc_peak_bytes" in report.authoritative_metrics
    assert "child_rss_bytes" in report.authoritative_metrics
    assert report.authoritative_metrics["checksum_match"] is True


def test_cross_host_advisory_comparison():
    report = evaluate_release_evidence(
        _norm(host="host-a"),
        _norm(host="host-b", runtime_s=0.20, tracemalloc_peak_bytes=8_050_000),
    )
    assert report.comparable_fields["host_match"] is False
    assert "cross_host_advisory" in report.reason_codes
    assert "runtime_s" in report.advisory_metrics
    assert "runtime_s" not in report.authoritative_metrics
    # Tracemalloc still authoritative; small bump → ready (not regression).
    assert report.decision == ReleaseDecision.EVIDENCE_READY
    assert report.advisory_metrics.get("tracemalloc_is_not_process_rss") is True


def test_checksum_mismatch():
    report = evaluate_release_evidence(_norm(), _norm(checksum=9.999))
    assert report.decision == ReleaseDecision.CORRECTNESS_FAILURE
    assert report.comparable is False
    assert "checksum_mismatch" in report.reason_codes


def test_shape_mismatch():
    report = evaluate_release_evidence(
        _norm(),
        _norm(input_shape={"channels": 16, "samples": 200000, "dtype": "float64"}),
    )
    assert report.decision == ReleaseDecision.NOT_COMPARABLE
    assert "shape_mismatch" in report.reason_codes


def test_backend_mismatch():
    report = evaluate_release_evidence(_norm(backend="numpy"), _norm(backend="numba"))
    assert report.decision == ReleaseDecision.NOT_COMPARABLE
    assert "backend_mismatch" in report.reason_codes


def test_timeout_never_ready():
    report = evaluate_release_evidence(
        _norm(),
        _norm(timeout_status=True, raw_outcome="timeout", process_exit_status=124),
    )
    assert report.decision == ReleaseDecision.TIMEOUT_FAILURE
    assert report.decision != ReleaseDecision.EVIDENCE_READY
    assert "timeout" in report.reason_codes


def test_child_crash():
    report = evaluate_release_evidence(
        _norm(),
        _norm(raw_outcome="child_crash", process_exit_status=139, correctness_status="fail"),
    )
    assert report.decision == ReleaseDecision.INFRASTRUCTURE_BLOCKED
    assert "child_crash" in report.reason_codes


def test_missing_metric_null_never_zero():
    base = _norm()
    cand = _norm(host="other")
    del base["tracemalloc_peak_bytes"]
    del base["child_rss_bytes"]
    del cand["tracemalloc_peak_bytes"]
    del cand["child_rss_bytes"]
    report = evaluate_release_evidence(base, cand)
    assert report.decision == ReleaseDecision.MISSING_METRIC
    # Ensure zeros were not fabricated in authoritative block.
    tm = report.authoritative_metrics.get("tracemalloc_peak_bytes", {})
    assert tm.get("baseline") is None
    assert tm.get("candidate") is None
    assert tm.get("ratio") is None


def test_insufficient_repetitions():
    report = evaluate_release_evidence(
        _norm(repetitions=1),
        _norm(repetitions=1),
        GateThresholds(min_repetitions=3),
    )
    assert report.decision == ReleaseDecision.EVIDENCE_INCONCLUSIVE
    assert "insufficient_repetitions" in report.reason_codes


def test_high_runtime_spread():
    report = evaluate_release_evidence(
        _norm(wall_best_s=0.04, wall_mean_s=0.10),  # spread = 1.5
        _norm(wall_best_s=0.04, wall_mean_s=0.05),
        GateThresholds(max_runtime_rel_spread=0.50),
    )
    assert report.decision == ReleaseDecision.EVIDENCE_INCONCLUSIVE
    assert "high_runtime_spread" in report.reason_codes


def test_deterministic_serialization():
    a = evaluate_release_evidence(_norm(), _norm(runtime_s=0.049))
    b = evaluate_release_evidence(_norm(), _norm(runtime_s=0.049))
    assert dumps(a.to_dict()) == dumps(b.to_dict())
    assert a.schema_version == GATE_SCHEMA_VERSION
    md_a = render_markdown(a)
    md_b = render_markdown(b)
    assert md_a == md_b
    assert "Performance Release Evidence Gate" in md_a


def test_finite_json():
    report = evaluate_release_evidence(
        _norm(runtime_s=float("nan")),
        _norm(runtime_s=0.05),
    )
    text = dumps(report.to_dict())
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    json.dumps(data, allow_nan=False)
    # Non-finite runtime sanitized in embedded records.
    assert data["baseline"]["runtime_s"] is None or math.isfinite(
        data["baseline"]["runtime_s"] or 0.0
    )


def test_synthetic_labeling():
    report = evaluate_release_evidence(_norm(), _norm())
    assert report.synthetic is True
    assert report.evidence_class == "performance_only"
    blob = dumps(report.to_dict()).lower()
    assert "bayes" not in blob
    assert "consciousness" not in blob
    assert "topology_gain" not in blob


def test_optional_dependency_not_success():
    report = evaluate_release_evidence(
        _norm(),
        _norm(optional_dependency_state="missing", raw_outcome="optional_dependency_missing"),
    )
    assert report.decision == ReleaseDecision.INFRASTRUCTURE_BLOCKED
    assert "optional_dependency_missing" in report.reason_codes


def test_regression_detected_same_host():
    report = evaluate_release_evidence(
        _norm(tracemalloc_peak_bytes=1_000_000),
        _norm(tracemalloc_peak_bytes=2_000_000),
        GateThresholds(max_tracemalloc_regression_ratio=1.10),
    )
    assert report.decision == ReleaseDecision.REGRESSION_DETECTED
    assert "tracemalloc_regression" in report.reason_codes


def test_missing_rss_field_stays_null_in_report():
    base = _norm()
    cand = _norm()
    del base["parent_sampled_rss_bytes"]
    report = evaluate_release_evidence(base, cand)
    parent = report.advisory_metrics["parent_sampled_rss_bytes"]
    assert parent["baseline"] is None
    assert parent["baseline"] != 0
