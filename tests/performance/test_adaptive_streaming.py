"""Tests for the deterministic adaptive chunk planner and its bounded-stream helper.

Assert deterministic, reliable properties: monotonicity, dtype/overlap accounting,
infeasible handling, bound safety, JSON-safety, and compatibility with the
existing ``bounded_stream`` (unchanged). No wall-clock or process-RSS thresholds.
Synthetic inputs are performance scaffolding only, never scientific evidence.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from tools.streaming.adaptive import (
    adaptive_bounded_stream,
    itemsize_of,
    plan_chunk_size,
)
from tools.streaming.adaptive_types import ChunkPlan, ChunkPlanRequest, ReasonCode
from tools.streaming.bounded import StreamResult


def _req(**overrides) -> ChunkPlanRequest:
    base = dict(
        channels=32, samples=200_000, dtype_itemsize=8,
        target_budget_bytes=8 * 1024 * 1024, min_chunk=256, max_chunk=65536,
        overlap=0, op_multiplier=3,
    )
    base.update(overrides)
    return ChunkPlanRequest(**base)


# --------------------------------------------------------------------------- #
# Core estimate + bounds
# --------------------------------------------------------------------------- #
def test_estimate_within_budget_and_bounds_when_feasible():
    plan = plan_chunk_size(_req())
    assert plan.feasible is True
    assert plan.estimated_working_set_bytes <= _req().target_budget_bytes
    assert 256 <= plan.chunk_size <= 65536
    # Estimate matches the documented conservative formula exactly.
    expected = 32 * 8 * (plan.chunk_size + 0) * 3
    assert plan.estimated_working_set_bytes == expected


def test_never_exceeds_configured_max_even_with_huge_budget():
    plan = plan_chunk_size(_req(target_budget_bytes=10**15, max_chunk=4096))
    assert plan.chunk_size <= 4096
    assert plan.reason == ReasonCode.AT_MAX_CHUNK


def test_limited_by_samples():
    plan = plan_chunk_size(_req(samples=1000, max_chunk=65536, target_budget_bytes=10**15))
    assert plan.chunk_size == 1000
    assert plan.reason == ReasonCode.LIMITED_BY_SAMPLES


# --------------------------------------------------------------------------- #
# Monotonicity
# --------------------------------------------------------------------------- #
def test_monotonic_nondecreasing_in_budget():
    budgets = [1, 2, 4, 8, 16, 32, 64, 128, 512, 4096]
    sizes = [plan_chunk_size(_req(target_budget_bytes=b * 1024 * 1024)).chunk_size for b in budgets]
    assert all(a <= b for a, b in zip(sizes, sizes[1:])), sizes
    assert sizes[-1] <= 65536


def test_monotonic_nonincreasing_in_channels():
    # More channels -> each row costs more -> chunk should not grow.
    sizes = [plan_chunk_size(_req(channels=c)).chunk_size for c in (1, 4, 16, 64, 256)]
    assert all(a >= b for a, b in zip(sizes, sizes[1:])), sizes


# --------------------------------------------------------------------------- #
# dtype and overlap accounting
# --------------------------------------------------------------------------- #
def test_dtype_changes_affect_chunk_size():
    small = plan_chunk_size(_req(dtype_itemsize=4))  # float32
    large = plan_chunk_size(_req(dtype_itemsize=8))  # float64
    assert small.chunk_size >= large.chunk_size
    assert small.bytes_per_row == 32 * 4
    assert large.bytes_per_row == 32 * 8


def test_overlap_reduces_available_chunk_and_is_accounted():
    without = plan_chunk_size(_req(overlap=0))
    withov = plan_chunk_size(_req(overlap=200))
    assert withov.chunk_size <= without.chunk_size
    # Working set explicitly includes the overlap rows.
    r = _req(overlap=200)
    expected = r.channels * r.dtype_itemsize * (withov.chunk_size + 200) * r.op_multiplier
    assert withov.estimated_working_set_bytes == expected


def test_op_multiplier_scales_working_set():
    one = plan_chunk_size(_req(op_multiplier=1))
    three = plan_chunk_size(_req(op_multiplier=3))
    assert three.chunk_size <= one.chunk_size


# --------------------------------------------------------------------------- #
# Impossible budgets
# --------------------------------------------------------------------------- #
def test_impossible_budget_is_infeasible_but_respects_min():
    plan = plan_chunk_size(_req(target_budget_bytes=1024, min_chunk=256))
    assert plan.feasible is False
    assert plan.reason == ReasonCode.INFEASIBLE_BUDGET_BELOW_MIN
    assert plan.chunk_size == 256          # clamped to min, never below
    assert plan.safety_margin_bytes < 0    # estimate exceeds budget (honest)


def test_budget_exactly_at_min_chunk_is_feasible():
    # Budget exactly covers one min-chunk working set: chunk == min_chunk, feasible.
    r = _req(min_chunk=256, op_multiplier=1, channels=1, dtype_itemsize=8, overlap=0,
             target_budget_bytes=256 * 8)  # exactly one min-chunk cost
    plan = plan_chunk_size(r)
    assert plan.chunk_size == 256
    assert plan.feasible is True
    assert plan.reason == ReasonCode.BUDGET_LIMITED
    assert plan.safety_margin_bytes == 0


def test_just_below_min_chunk_cost_is_infeasible():
    r = _req(min_chunk=256, op_multiplier=1, channels=1, dtype_itemsize=8, overlap=0,
             target_budget_bytes=256 * 8 - 1)  # one byte short of a min chunk
    plan = plan_chunk_size(r)
    assert plan.chunk_size == 256           # clamped up to min, never below
    assert plan.feasible is False
    assert plan.reason == ReasonCode.INFEASIBLE_BUDGET_BELOW_MIN
    assert plan.safety_margin_bytes < 0


# --------------------------------------------------------------------------- #
# Large channel counts
# --------------------------------------------------------------------------- #
def test_large_channel_count_still_bounded_and_finite():
    plan = plan_chunk_size(_req(channels=100_000, target_budget_bytes=64 * 1024 * 1024))
    assert plan.chunk_size >= 256  # never below min (clamps up, reports feasibility)
    assert math.isfinite(plan.safety_margin_ratio)
    assert isinstance(plan.estimated_working_set_bytes, int)


# --------------------------------------------------------------------------- #
# Determinism + JSON safety
# --------------------------------------------------------------------------- #
def test_deterministic_output():
    a = plan_chunk_size(_req())
    b = plan_chunk_size(_req())
    assert a == b


def test_plan_to_dict_is_json_safe():
    import json
    for kw in ({}, dict(target_budget_bytes=1024), dict(overlap=100), dict(channels=99999)):
        plan = plan_chunk_size(_req(**kw))
        d = plan.to_dict()
        text = json.dumps(d)  # raises on NaN/Inf-incompatible or non-serializable
        assert "NaN" not in text and "Infinity" not in text
        for value in d.values():
            if isinstance(value, float):
                assert math.isfinite(value)
        assert d["reason"] in {rc.value for rc in ReasonCode}


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    dict(channels=0), dict(samples=0), dict(dtype_itemsize=0),
    dict(target_budget_bytes=0), dict(min_chunk=0),
    dict(min_chunk=10, max_chunk=5), dict(overlap=-1),
    dict(overlap=256, min_chunk=256), dict(op_multiplier=0),
])
def test_invalid_inputs_raise(bad):
    with pytest.raises(ValueError):
        plan_chunk_size(_req(**bad))


def test_itemsize_of_resolves_and_rejects():
    assert itemsize_of("float64") == 8
    assert itemsize_of(np.float32) == 4
    assert itemsize_of(np.dtype("int16")) == 2
    with pytest.raises(ValueError):
        itemsize_of("not-a-dtype")


# --------------------------------------------------------------------------- #
# Compatibility with existing bounded streaming
# --------------------------------------------------------------------------- #
def test_adaptive_bounded_stream_runs_and_matches_reference():
    rng = np.random.default_rng(0)
    sig = rng.standard_normal((40000, 16)).astype(np.float64)
    result, plan = adaptive_bounded_stream(
        sig, 2 * 1024 * 1024, min_chunk=256, max_chunk=65536,
        op_multiplier=3, track_memory=True,
    )
    assert isinstance(result, StreamResult)
    assert isinstance(plan, ChunkPlan)
    assert result.chunk_size == plan.chunk_size
    # Aggregates match the full-array reference within tolerance (bounded_stream
    # behavior is unchanged; the planner only picks the chunk size).
    assert np.allclose(result.mean, sig.mean(axis=0), atol=1e-12)
    assert np.allclose(result.variance, sig.var(axis=0), atol=1e-9)
    # Deterministic: same inputs -> same plan.
    _, plan2 = adaptive_bounded_stream(sig, 2 * 1024 * 1024, min_chunk=256, max_chunk=65536, op_multiplier=3)
    assert plan == plan2


def test_adaptive_bounded_stream_one_d_signal():
    sig = np.linspace(0.0, 1.0, 10000, dtype=np.float64)
    result, plan = adaptive_bounded_stream(sig, 1 * 1024 * 1024, min_chunk=128, max_chunk=4096)
    assert plan.chunk_size <= 4096
    assert result.n_channels == 1


def test_adaptive_bounded_stream_rejects_3d():
    with pytest.raises(ValueError):
        adaptive_bounded_stream(np.zeros((2, 2, 2)), 1024, min_chunk=1, max_chunk=2)
