"""Additive, semantics-preserving bounded-runtime benchmark layer for the
higher-order signal pipeline.

This package does NOT implement or import the higher-order feature code
(``topo_monitor/higher_order/*`` and ``analysis/transition_forecasting/*`` from
other agents' PRs). It defines *protocol-compatible* interfaces plus deterministic
local fixtures, and provides bounded-memory wrappers, a memory planner, telemetry,
and a benchmark harness so runtime/memory behavior can be measured and shown to be
numerically equivalent to full materialization -- without changing any scientific
semantics.

Nothing here creates biological or scientific evidence; fixtures are synthetic and
labeled as performance evidence only.
"""
from __future__ import annotations

from .planner import MemoryPlan, PlanRequest, plan_chunk
from .protocols import (
    SpectralSegmentFn,
    SurrogateFn,
    TriadStatFn,
    fixture_spectral_power,
    fixture_surrogate_stat,
    fixture_triad_stat,
)
from .telemetry import ChildResult, MemoryTelemetry, execute_child, json_safe
from .bounded import (
    IncrementalSummary,
    RollingCovariance,
    iter_signal_windows,
    iter_spectral_segments,
    iter_triad_candidates,
    one_at_a_time_surrogates,
)
from .benchmark import (
    EquivalenceReport,
    compute_full,
    compute_bounded,
    run_benchmark,
    verify_equivalence,
)

__all__ = [
    "MemoryPlan", "PlanRequest", "plan_chunk",
    "SpectralSegmentFn", "SurrogateFn", "TriadStatFn",
    "fixture_spectral_power", "fixture_surrogate_stat", "fixture_triad_stat",
    "ChildResult", "MemoryTelemetry", "execute_child", "json_safe",
    "IncrementalSummary", "RollingCovariance", "iter_signal_windows",
    "iter_spectral_segments", "iter_triad_candidates", "one_at_a_time_surrogates",
    "EquivalenceReport", "compute_full", "compute_bounded", "run_benchmark",
    "verify_equivalence",
]
