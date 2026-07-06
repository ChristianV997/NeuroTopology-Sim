"""Tests for analysis/itct/variational_action and analysis/itct/longitudinal_cessation."""
from __future__ import annotations

import numpy as np
import pytest

from analysis.itct.variational_action.action_tracker import (
    VariationalActionConfig,
    VariationalActionTracker,
    compare_against_baselines,
)
from analysis.itct.longitudinal_cessation.sliding_window_topology import (
    SlidingWindowConfig,
    SlidingWindowTopologyTracker,
)


def test_action_tracker_shape_mismatch_raises():
    tracker = VariationalActionTracker()
    with pytest.raises(ValueError):
        tracker.track(np.zeros(5), np.zeros(6))


def test_action_tracker_stationary_for_constant_series():
    """A perfectly constant energy/information series should be exactly stationary
    everywhere except numerical edge effects -- a basic sanity check independent of
    any hoped-for research result."""
    tracker = VariationalActionTracker(VariationalActionConfig(stationarity_eps=1e-6))
    n = 20
    result = tracker.track(np.ones(n), np.ones(n))
    assert result["frac_time_stationary"] > 0.9


def test_compare_against_baselines_reports_all_three_without_verdict():
    rng = np.random.default_rng(1)
    n = 50
    energy = np.linspace(1, 0, n) + 0.02 * rng.standard_normal(n)
    information = 1.0 - energy
    result = compare_against_baselines(energy, information, seed=7)
    assert set(result.keys()) >= {"itct", "gnw_baseline", "iit_baseline", "note"}
    for key in ("itct", "gnw_baseline", "iit_baseline"):
        assert "frac_time_stationary" in result[key]
        assert "mean_abs_dS_dt" in result[key]


def test_sliding_window_requires_enough_timesteps():
    tracker = SlidingWindowTopologyTracker(SlidingWindowConfig(window_size=10))
    with pytest.raises(ValueError):
        tracker.run([np.eye(4) for _ in range(3)])


def test_sliding_window_runs_on_stable_signal_with_no_transitions():
    """A distance-matrix series with NO real structural change should produce zero
    or very few flagged transitions -- regression guard for the bug found during
    development, where comparing against the all-time historical peak caused a single
    early value to keep re-triggering 'transitions' for every later, merely-lower
    window (17/32 windows flagged on a series with exactly one genuine change)."""
    rng = np.random.default_rng(3)
    n_t, C = 30, 8
    dmats = []
    for _ in range(n_t):
        M = np.clip(0.5 + 0.05 * rng.standard_normal((C, C)), 0, 1)
        M = (M + M.T) / 2
        np.fill_diagonal(M, 0)
        dmats.append(M)
    tracker = SlidingWindowTopologyTracker(SlidingWindowConfig(window_size=5, step=1))
    result = tracker.run(dmats)
    # a stable-noise signal should not produce a cascade of "transitions"
    assert len(result["transitions"]) <= 3


def test_sliding_window_signal_reflects_a_genuine_structural_change():
    """Validates the underlying signal, not the single-index step-detector.

    Direct testing showed the step-by-step z-score detector (_detect_transitions) is
    NOT reliably sensitive to a transition that's smeared across ~window_size steps by
    the window-averaging itself -- a real, current limitation, not something papered
    over by re-tuning parameters until an assertion happened to pass. What IS true and
    checked here: the raw total_persistence signal shows a clear, large plateau
    difference between the pre- and post-change regimes (a ~2.5x drop in this
    configuration), which is what the sliding-window computation is actually for.
    Detecting the exact transition index reliably under window-smoothing is flagged as
    follow-up work, not claimed as solved.
    """
    rng = np.random.default_rng(0)
    n_t, C = 40, 10
    dmats = []
    for t in range(n_t):
        if t < 20:
            M = np.clip(0.5 + 0.05 * rng.standard_normal((C, C)), 0, 1)
        else:
            M = np.full((C, C), 0.9)
            M[: C // 2, : C // 2] = 0.1
            M[C // 2:, C // 2:] = 0.1
            M = np.clip(M + 0.02 * rng.standard_normal((C, C)), 0, 1)
        M = (M + M.T) / 2
        np.fill_diagonal(M, 0)
        dmats.append(M)
    tracker = SlidingWindowTopologyTracker(SlidingWindowConfig(window_size=5, step=1))
    result = tracker.run(dmats)
    tp = np.array(result["total_persistence"])
    early_mean = tp[:16].mean()
    late_mean = tp[20:].mean()
    assert early_mean > 2.0 * late_mean  # genuine, large regime difference
