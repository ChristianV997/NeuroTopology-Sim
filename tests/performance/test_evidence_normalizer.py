"""Tests for pure benchmark evidence normalization.

Performance scaffolding only — never scientific evidence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools.performance.evidence_normalizer import (
    NORMALIZATION_SCHEMA_VERSION,
    Decision,
    commensurability,
    compare_evidence,
    dumps,
    normalize_record,
    normalize_reports,
)


def _base(**overrides):
    rec = {
        "benchmark_id": "stream-bounded",
        "source_commit": "abc123def456",
        "branch": "main",
        "host": "host-a",
        "platform": "linux",
        "python_version": "3.12.3",
        "backend": "numpy",
        "input_shape": {"channels": 32, "samples": 200000, "dtype": "float64"},
        "chunk_size": 16384,
        "repetitions": 3,
        "checksum": 1.777827,
        "correctness_ok": True,
        "runtime_s": 0.045,
        "tracemalloc_peak_bytes": 8_000_000,
        "child_rss_bytes": 210_000_000,
        "parent_sampled_rss_bytes": 212_000_000,
        "timed_out": False,
        "exit_code": 0,
        "outcome": "pass",
        "synthetic": True,
    }
    rec.update(overrides)
    return rec


def test_valid_benchmark_pair():
    base = _base()
    cand = _base(runtime_s=0.046, tracemalloc_peak_bytes=8_100_000, child_rss_bytes=211_000_000)
    decision = compare_evidence(base, cand)
    assert decision.comparable is True
    assert decision.decision == Decision.PASS
    assert decision.checksum_match is True
    assert decision.evidence_class == "performance_only"
    assert decision.synthetic is True
    assert commensurability(normalize_record(base), normalize_record(cand)) == Decision.COMPARABLE


def test_shape_mismatch():
    base = _base()
    cand = _base(input_shape={"channels": 16, "samples": 200000, "dtype": "float64"})
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.NOT_COMPARABLE
    assert decision.comparable is False
    assert decision.shape_match is False


def test_checksum_mismatch():
    base = _base()
    cand = _base(checksum=9.999)
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.CORRECTNESS_FAILURE
    assert decision.checksum_match is False
    assert decision.comparable is False


def test_host_mismatch_runtime_advisory():
    base = _base(host="host-a", tracemalloc_peak_bytes=8_000_000)
    cand = _base(host="host-b", runtime_s=0.20, tracemalloc_peak_bytes=8_050_000)
    decision = compare_evidence(base, cand)
    assert decision.host_match is False
    assert decision.runtime_advisory is True
    # Checksums match + tracemalloc ok → pass (runtime advisory does not alone fail).
    assert decision.decision == Decision.PASS
    assert any("advisory" in r for r in decision.reasons)


def test_missing_rss_is_null_never_zero():
    base = _base()
    del base["child_rss_bytes"]
    del base["parent_sampled_rss_bytes"]
    norm = normalize_record(base)
    assert norm.child_rss_bytes is None
    assert norm.parent_sampled_rss_bytes is None
    # Explicit zero must not be treated as a real measurement.
    norm0 = normalize_record(_base(child_rss_bytes=0, parent_sampled_rss_bytes=0))
    assert norm0.child_rss_bytes is None
    assert norm0.parent_sampled_rss_bytes is None
    d = norm.to_dict()
    assert d["child_rss_bytes"] is None
    assert "0" != str(d["child_rss_bytes"])


def test_missing_tracemalloc_is_null_never_zero():
    base = _base()
    del base["tracemalloc_peak_bytes"]
    norm = normalize_record(base)
    assert norm.tracemalloc_peak_bytes is None
    norm0 = normalize_record(_base(tracemalloc_peak_bytes=0))
    assert norm0.tracemalloc_peak_bytes is None


def test_timeout_never_pass():
    base = _base()
    cand = _base(timed_out=True, outcome="timeout", exit_code=124, correctness_ok=None)
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.TIMEOUT
    assert decision.decision != Decision.PASS
    assert decision.comparable is False
    assert normalize_record(cand).timeout_status is True


def test_child_crash():
    base = _base()
    cand = _base(outcome="child_crash", exit_code=139, correctness_ok=False)
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.CHILD_CRASH
    assert decision.comparable is False


def test_missing_source_commit():
    base = _base()
    cand = _base()
    del cand["source_commit"]
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.NOT_COMPARABLE
    assert "source_commit" in decision.reasons[0]
    assert normalize_record(cand).source_commit is None


def test_deterministic_normalization():
    raw = _base()
    a = normalize_record(raw)
    b = normalize_record(raw)
    assert a.to_dict() == b.to_dict()
    assert a.fingerprint() == b.fingerprint()
    assert a.schema_version == NORMALIZATION_SCHEMA_VERSION
    # Order of keys in dumps is sorted → stable text.
    assert dumps(a.to_dict()) == dumps(b.to_dict())


def test_finite_json(tmp_path):
    raw = _base(runtime_s=float("nan"), tracemalloc_peak_bytes=8_000_000)
    norm = normalize_record(raw)
    text = dumps(norm.to_dict())
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    json.dumps(data, allow_nan=False)
    assert data["runtime_s"] is None  # non-finite → null
    assert math.isfinite(data["checksum"])


def test_performance_only_evidence_labeling():
    norm = normalize_record(_base())
    assert norm.evidence_class == "performance_only"
    assert norm.synthetic is True
    decision = compare_evidence(_base(), _base(runtime_s=0.044))
    assert decision.evidence_class == "performance_only"
    assert decision.synthetic is True
    # Ensure scientific claim language is not emitted.
    blob = dumps(decision.to_dict()).lower()
    assert "scientific proof" not in blob
    assert "consciousness" not in blob


def test_normalize_reports_list_and_wrapper():
    payload = {"results": [_base(benchmark_id="a"), _base(benchmark_id="b", checksum=1.1)]}
    norms = normalize_reports(payload)
    assert [n.benchmark_id for n in norms] == ["a", "b"]
    norms2 = normalize_reports([_base(benchmark_id="c")])
    assert norms2[0].benchmark_id == "c"


def test_missing_metric_decision():
    base = _base()
    cand = _base(host="other-host")
    del base["tracemalloc_peak_bytes"]
    del base["child_rss_bytes"]
    del cand["tracemalloc_peak_bytes"]
    del cand["child_rss_bytes"]
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.MISSING_METRIC


def test_infrastructure_blocked():
    base = _base()
    cand = _base(outcome="infrastructure_failure", exit_code=127)
    decision = compare_evidence(base, cand)
    assert decision.decision == Decision.INFRASTRUCTURE_BLOCKED


def test_process_runner_shaped_record():
    """Accept PR #241 ChildResult-like dicts without importing that module."""
    child = {
        "config": {
            "id": "cfg-1",
            "channels": 8,
            "samples": 20000,
            "chunk_size": 4096,
            "backend": "numpy",
        },
        "outcome": "pass",
        "exit_code": 0,
        "timed_out": False,
        "elapsed_s": 1.2,
        "checksum": 42.0,
        "tracemalloc_peak_bytes": 10000,
        "peak_rss_bytes": 50_000_000,
        "parent_sampled_peak_rss_bytes": 55_000_000,
        "correctness_ok": True,
        "source_commit": "deadbeef",
        "host": "host-a",
        "platform": "linux",
    }
    norm = normalize_record(child)
    assert norm.benchmark_id == "cfg-1"
    assert norm.child_rss_bytes == 50_000_000
    assert norm.parent_sampled_rss_bytes == 55_000_000
    assert norm.input_shape["channels"] == 8


def test_orchestration_shaped_record():
    """Accept PR #244 CaseResult-like dicts without importing that package."""
    case = {
        "case_id": "orchestration-self-test",
        "command": ["python", "-c", "print(1)"],
        "input_configuration": {"channels": 4, "samples": 1000, "dtype": "float64"},
        "status": "TIMEOUT",
        "duration_s": 1.0,
        "exit_code": 124,
        "timed_out": True,
        "checksum": "abc",
        "source_commit": "cafebabe",
        "host": "host-a",
    }
    # Flatten input_configuration into shape via config merge path:
    case["config"] = case["input_configuration"]
    norm = normalize_record(case)
    assert norm.timeout_status is True
    assert norm.benchmark_id == "orchestration-self-test"
    decision = compare_evidence(_base(source_commit="cafebabe", host="host-a"), case)
    assert decision.decision == Decision.TIMEOUT
