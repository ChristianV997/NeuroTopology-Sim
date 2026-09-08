"""Tests for the bounded higher-order runtime benchmark layer.

Validates numerical equivalence, determinism, bounded memory, telemetry
robustness, process isolation, finite JSON, and offline operation. All fixtures
are synthetic performance scaffolding -- never scientific/biological evidence.
The higher-order feature implementations are NOT imported (protocol + fixtures).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from tools.higher_order_runtime.benchmark import (
    WorkloadConfig,
    compute_bounded,
    compute_bounded_checkpointed,
    compute_full,
    make_signal,
    run_benchmark,
    verify_equivalence,
)
from tools.higher_order_runtime.bounded import (
    IncrementalSummary,
    RollingCovariance,
    iter_triad_candidates,
    one_at_a_time_surrogates,
)
from tools.higher_order_runtime.planner import PlanRequest, PlanReason, plan_chunk
from tools.higher_order_runtime.protocols import fixture_surrogate_stat
from tools.higher_order_runtime.telemetry import (
    MemoryTelemetry,
    execute_child,
    json_safe,
)

SCRIPT = str(Path(__file__).resolve().parents[2] / "scripts" / "benchmark_higher_order_runtime.py")


def _cfg(**kw):
    base = dict(n_samples=12000, n_channels=10, seed=0, segment_len=512,
                candidate_limit=48, surrogate_limit=12)
    base.update(kw)
    return WorkloadConfig(**base)


# --------------------------------------------------------------------------- #
# Numerical equivalence + chunk-size invariance
# --------------------------------------------------------------------------- #
def test_rolling_covariance_matches_numpy():
    cfg = _cfg()
    X = make_signal(cfg)
    acc = RollingCovariance(cfg.n_channels)
    for start in range(0, X.shape[0], 1000):
        acc.update(X[start:start + 1000])
    assert np.allclose(acc.matrix(ddof=1), np.cov(X, rowvar=False, ddof=1), rtol=0, atol=1e-8)


def test_chunk_size_invariance():
    cfg = _cfg()
    X = make_signal(cfg)
    full = compute_full(X, cfg)
    for chunk in (128, 512, 3000, 12000):
        bounded = compute_bounded(X, cfg, chunk_size=chunk)
        rep = verify_equivalence(full, bounded, tolerance=1e-9)
        assert rep.equivalent, (chunk, rep.to_dict())
        assert bounded["triad_count"] == full["triad_count"]
        assert bounded["spectral_count"] == full["spectral_count"]


def test_checkpoint_resume_equivalent(tmp_path):
    cfg = _cfg()
    X = make_signal(cfg)
    full = compute_full(X, cfg)
    ckpt = compute_bounded_checkpointed(X, cfg, chunk_size=1024,
                                        checkpoint_path=str(tmp_path / "s.npz"))
    assert verify_equivalence(full, ckpt, 1e-9).equivalent


# --------------------------------------------------------------------------- #
# Deterministic seeds
# --------------------------------------------------------------------------- #
def test_deterministic_seeds():
    cfg = _cfg()
    assert np.array_equal(make_signal(cfg), make_signal(cfg))
    a = compute_bounded(make_signal(cfg), cfg, chunk_size=1000)
    b = compute_bounded(make_signal(cfg), cfg, chunk_size=1000)
    assert a == b
    # surrogates deterministic for a fixed seed, and change with the seed.
    X = make_signal(cfg)
    m1, s1 = one_at_a_time_surrogates(X, fixture_surrogate_stat, surrogate_limit=8, seed=7)
    m2, s2 = one_at_a_time_surrogates(X, fixture_surrogate_stat, surrogate_limit=8, seed=7)
    m3, s3 = one_at_a_time_surrogates(X, fixture_surrogate_stat, surrogate_limit=8, seed=8)
    assert s1 == s2 and m1 == m2
    assert s1 != s3


def test_run_benchmark_replay_identical():
    report = run_benchmark(_cfg(), chunk_size=2048)
    assert report["deterministic_replay_identical"] is True
    assert report["all_equivalent"] is True


# --------------------------------------------------------------------------- #
# Bounded memory
# --------------------------------------------------------------------------- #
def test_bounded_memory_peak_lower_than_full():
    cfg = _cfg(n_samples=60000, n_channels=16)
    X = make_signal(cfg)
    with MemoryTelemetry() as full_mem:
        compute_full(X, cfg)
    with MemoryTelemetry() as bounded_mem:
        compute_bounded(X, cfg, chunk_size=1024)
    assert isinstance(full_mem.peak_bytes, int) and isinstance(bounded_mem.peak_bytes, int)
    assert bounded_mem.peak_bytes < full_mem.peak_bytes


def test_planner_bounds_and_reasons():
    req = PlanRequest(n_samples=100000, n_channels=16, dtype_itemsize=8,
                      target_budget_bytes=4 * 1024 * 1024, min_chunk=256, max_chunk=65536)
    plan = plan_chunk(req)
    assert plan.feasible is True
    assert 256 <= plan.chunk_size <= 65536
    assert plan.estimated_working_set_bytes <= req.target_budget_bytes
    # Monotonic: bigger budget -> chunk does not shrink.
    sizes = [plan_chunk(PlanRequest(100000, 16, 8, b, 256, 65536)).chunk_size
             for b in (1 << 20, 1 << 21, 1 << 22, 1 << 24)]
    assert all(a <= b for a, b in zip(sizes, sizes[1:]))
    # Impossible budget -> infeasible, clamped to min, negative margin.
    tiny = plan_chunk(PlanRequest(100000, 16, 8, 1024, 256, 65536))
    assert tiny.feasible is False
    assert tiny.reason == PlanReason.INFEASIBLE_BUDGET_BELOW_MIN
    assert tiny.safety_margin_bytes < 0


def test_triad_candidate_limit():
    assert list(iter_triad_candidates(3)) == [(0, 1, 2)]
    assert len(list(iter_triad_candidates(6, candidate_limit=5))) == 5
    assert list(iter_triad_candidates(2)) == []


# --------------------------------------------------------------------------- #
# Telemetry: timeout, missing metric, optional dependency
# --------------------------------------------------------------------------- #
def test_child_timeout():
    result = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1)
    assert result.timed_out is True
    assert result.exit_code is None or result.exit_code != 0
    assert result.elapsed_s < 20


def test_missing_metric_is_null_not_zero():
    # With RSS sampling disabled the metric is None (never fabricated as 0).
    result = execute_child([sys.executable, "-c", "print('ok')"], timeout_s=30, sample_rss=False)
    assert result.peak_rss_bytes is None
    assert result.exit_code == 0
    # json_safe maps non-finite to None (unavailable), not a number.
    assert json_safe(float("nan")) is None and json_safe(float("inf")) is None


def test_optional_dependency_rss_is_optional():
    # Whether or not psutil is present, RSS is int-or-None and never raises.
    result = execute_child([sys.executable, "-c", "print('ok')"], timeout_s=30, sample_rss=True)
    assert result.peak_rss_bytes is None or isinstance(result.peak_rss_bytes, int)


# --------------------------------------------------------------------------- #
# Process isolation
# --------------------------------------------------------------------------- #
def test_process_isolation_child_report():
    child_cfg = {"samples": 8000, "channels": 8, "seed": 0, "segment_len": 256,
                 "candidate_limit": 20, "surrogate_limit": 6, "chunk_size": 1024,
                 "budget_bytes": 4 * 1024 * 1024, "tolerance": 1e-9}
    argv = [sys.executable, SCRIPT, "child", "--config-json", json.dumps(child_cfg)]
    result = execute_child(argv, timeout_s=120)
    assert result.timed_out is False
    assert result.exit_code == 0
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["all_equivalent"] is True
    # child RSS is int-or-None (never fabricated).
    assert result.peak_rss_bytes is None or isinstance(result.peak_rss_bytes, int)


# --------------------------------------------------------------------------- #
# Finite JSON + offline
# --------------------------------------------------------------------------- #
def test_report_is_finite_json():
    report = run_benchmark(_cfg(), chunk_size=2048)
    text = json.dumps(report, allow_nan=False)  # raises on NaN/Inf
    assert "NaN" not in text and "Infinity" not in text

    def _finite(o):
        if isinstance(o, float):
            assert math.isfinite(o)
        elif isinstance(o, dict):
            for v in o.values():
                _finite(v)
        elif isinstance(o, list):
            for v in o:
                _finite(v)

    _finite(json.loads(text))


def test_no_network_execution():
    # The repo conftest network guard is active in this process; a full benchmark
    # must complete entirely offline and reference no network dependency.
    report = run_benchmark(_cfg(), chunk_size=2048)
    assert report["all_equivalent"] is True
    assert "network" not in json.dumps(report).lower()


def test_evidence_labeling():
    report = run_benchmark(_cfg(), chunk_size=2048)
    assert report["evidence_class"] == "performance_only"
    assert report["synthetic"] is True
