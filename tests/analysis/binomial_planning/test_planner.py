"""Tests for sample size planning, precision targets, zero-event bounds, and binary search."""

import math
import pytest

from analysis.binomial_planning.planner import (
    calculate_wilson_width_at_p,
    plan_sample_size,
    plan_zero_event_sample_size,
    zero_event_upper_bound,
)


def test_zero_event_upper_bound_formula() -> None:
    """zero_event_upper_bound must match exact analytical formula z^2 / (n + z^2)."""
    z = 1.96
    z2 = z * z
    for n in [1, 5, 16, 50, 100, 500]:
        val = zero_event_upper_bound(n, z=z)
        expected = z2 / (float(n) + z2)
        assert math.isclose(val, expected, abs_tol=1e-12)

    # Validation errors
    with pytest.raises(ValueError, match="n must be >= 1"):
        zero_event_upper_bound(0)
    with pytest.raises(ValueError, match="n must be >= 1"):
        zero_event_upper_bound(-5)
    with pytest.raises(TypeError, match="n must be an integer"):
        zero_event_upper_bound(16.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="n must be an integer"):
        zero_event_upper_bound(True)  # type: ignore[arg-type]


def test_plan_zero_event_sample_size_analytical_cases() -> None:
    """Test sample size planning for zero false positives against analytical targets."""
    # Using z = 1.9599639845400536 (95% confidence)
    # Target 0.20 -> ceil(3.8415 * (5 - 1)) = ceil(15.3658) = 16
    plan_20 = plan_zero_event_sample_size(0.20)
    assert plan_20.required_n == 16
    assert plan_20.status == "found"
    assert plan_20.achieved_metric_value is not None
    assert plan_20.achieved_metric_value <= 0.20
    assert zero_event_upper_bound(15) > 0.20

    # Target 0.10 -> ceil(3.8415 * (10 - 1)) = ceil(34.573) = 35
    plan_10 = plan_zero_event_sample_size(0.10)
    assert plan_10.required_n == 35
    assert plan_10.achieved_metric_value <= 0.10
    assert zero_event_upper_bound(34) > 0.10

    # Target 0.05 -> ceil(3.8415 * (20 - 1)) = ceil(72.9877) = 73
    plan_05 = plan_zero_event_sample_size(0.05)
    assert plan_05.required_n == 73
    assert plan_05.achieved_metric_value <= 0.05
    assert zero_event_upper_bound(72) > 0.05

    # Target 0.01 -> ceil(3.8415 * (100 - 1)) = ceil(380.304) = 381
    plan_01 = plan_zero_event_sample_size(0.01)
    assert plan_01.required_n == 381
    assert plan_01.achieved_metric_value <= 0.01
    assert zero_event_upper_bound(380) > 0.01


def test_calculate_wilson_width_at_p() -> None:
    """Theoretical width must satisfy symmetry, maximum at p=0.5, and analytical identities."""
    z = 1.96
    z2 = z * z
    n = 100

    # Fast path at p = 0.5: W = z / sqrt(n + z^2)
    w_half = calculate_wilson_width_at_p(0.5, n, z=z)
    expected_w_half = z / math.sqrt(float(n) + z2)
    assert math.isclose(w_half, expected_w_half, abs_tol=1e-12)

    # Symmetry: W(p, n) == W(1 - p, n)
    for p in [0.05, 0.1, 0.2, 0.35, 0.49]:
        w_p = calculate_wilson_width_at_p(p, n, z=z)
        w_comp = calculate_wilson_width_at_p(1.0 - p, n, z=z)
        assert math.isclose(w_p, w_comp, abs_tol=1e-12)
        # Maximum is strictly at p = 0.5
        assert w_p < w_half


def test_plan_sample_size_uniform_worst_case() -> None:
    """Uniform worst-case planning (design_p=None) plans for p=0.5 to guarantee width across all p."""
    # Target full width W = 0.10 at 95% confidence
    # n >= z^2 * (1 / W^2 - 1) = 3.841459 * (100 - 1) = 380.304 -> n = 381
    plan = plan_sample_size(target_width=0.10, design_p=None, is_half_width=False)

    assert plan.status == "found"
    assert plan.guarantee_type == "uniform_worst_case"
    assert plan.design_proportion == 0.5
    assert plan.required_n == 381
    assert plan.achieved_metric_value is not None
    assert plan.achieved_metric_value <= 0.10

    # Ensure width is <= 0.10 across the entire grid of p in [0, 1]
    for p_test in [0.0, 0.01, 0.05, 0.1, 0.2, 0.5, 0.8, 0.95, 1.0]:
        w_at_p = calculate_wilson_width_at_p(p_test, plan.required_n)
        assert w_at_p <= 0.10


def test_plan_sample_size_pointwise_vs_uniform() -> None:
    """Pointwise planning at low FPR (p=0.05) requires substantially fewer trials than uniform planning."""
    target_w = 0.06

    # Pointwise plan at p = 0.05 (e.g. designing around a targeted 5% FPR)
    plan_pointwise = plan_sample_size(target_width=target_w, design_p=0.05)
    # Uniform plan at p = 0.5
    plan_uniform = plan_sample_size(target_width=target_w, design_p=None)

    assert plan_pointwise.guarantee_type == "pointwise_at_p"
    assert plan_uniform.guarantee_type == "uniform_worst_case"
    assert plan_pointwise.required_n is not None and plan_uniform.required_n is not None

    # Pointwise required_n should be less than half of uniform required_n
    assert plan_pointwise.required_n < plan_uniform.required_n
    assert plan_pointwise.required_n < 0.5 * plan_uniform.required_n

    # Achieved width at design point meets target
    assert plan_pointwise.achieved_metric_value <= target_w


def test_half_width_mode() -> None:
    """Half-width mode sets target full width to 2 * target_half_width."""
    # Half-width E = 0.05 <=> Full-width W = 0.10
    plan_half = plan_sample_size(target_width=0.05, is_half_width=True, design_p=None)
    plan_full = plan_sample_size(target_width=0.10, is_half_width=False, design_p=None)

    assert plan_half.target_metric == "half_width"
    assert plan_full.target_metric == "full_width"
    assert plan_half.required_n == plan_full.required_n
    assert math.isclose(plan_half.achieved_metric_value * 2.0, plan_full.achieved_metric_value, abs_tol=1e-12)


def test_binary_search_matches_linear_scan() -> None:
    """Deterministic binary search must find the exact same minimal n as a brute-force linear scan."""
    design_p = 0.15
    target_w = 0.08

    plan = plan_sample_size(target_width=target_w, design_p=design_p, min_n=10, max_n=2000)
    assert plan.status == "found"
    n_found = plan.required_n

    # Brute-force linear scan:
    linear_n = None
    for n_candidate in range(10, 2000):
        if calculate_wilson_width_at_p(design_p, n_candidate) <= target_w:
            linear_n = n_candidate
            break

    assert n_found == linear_n


def test_bounded_search_exceeded_and_edge_cases() -> None:
    """Planner properly signals exceeded_max_n when target cannot be met within search bound."""
    # Target requires very large n, but max_n is small
    plan = plan_sample_size(target_width=0.001, max_n=100)
    assert plan.status == "exceeded_max_n"
    assert plan.required_n is None
    assert plan.achieved_metric_value is None

    # Target already satisfied at min_n
    plan_min = plan_sample_size(target_width=0.99, min_n=5)
    assert plan_min.status == "found"
    assert plan_min.required_n == 5


def test_input_validation_errors() -> None:
    """Invalid parameter values must be rejected with informative exceptions."""
    with pytest.raises(ValueError, match="target_width must be positive"):
        plan_sample_size(target_width=0.0)
    with pytest.raises(ValueError, match="target_width must be positive"):
        plan_sample_size(target_width=-0.05)
    with pytest.raises(ValueError, match="target full-width must be < 1.0"):
        plan_sample_size(target_width=1.0, is_half_width=False)
    with pytest.raises(ValueError, match="target half-width must be < 0.5"):
        plan_sample_size(target_width=0.5, is_half_width=True)

    with pytest.raises(ValueError, match="design_p must be in"):
        plan_sample_size(target_width=0.1, design_p=-0.1)
    with pytest.raises(ValueError, match="design_p must be in"):
        plan_sample_size(target_width=0.1, design_p=1.1)

    with pytest.raises(ValueError, match="min_n must be >= 1"):
        plan_sample_size(target_width=0.1, min_n=0)
    with pytest.raises(ValueError, match="max_n .* must be >= min_n"):
        plan_sample_size(target_width=0.1, min_n=100, max_n=50)


def test_cli_execution() -> None:
    """Test CLI commands: interval, plan-zero, plan-width, and errors."""
    from analysis.binomial_planning.cli import main
    import io
    from contextlib import redirect_stdout, redirect_stderr

    # 1. interval command
    out = io.StringIO()
    with redirect_stdout(out):
        ret = main(["interval", "-k", "0", "-n", "16", "-z", "1.96"])
    assert ret == 0
    assert "0.193613" in out.getvalue()

    # 2. plan-zero command
    out = io.StringIO()
    with redirect_stdout(out):
        ret = main(["plan-zero", "-t", "0.05", "-z", "1.96"])
    assert ret == 0
    assert '"required_n": 73' in out.getvalue()

    # 3. plan-width command
    out = io.StringIO()
    with redirect_stdout(out):
        ret = main(["plan-width", "-w", "0.10"])
    assert ret == 0
    assert '"required_n": 381' in out.getvalue()

    # 4. error command
    err = io.StringIO()
    with redirect_stderr(err):
        ret = main(["interval", "-k", "10", "-n", "5"])
    assert ret == 2
    assert "cannot exceed total trials" in err.getvalue()

    # 5. no command
    out = io.StringIO()
    with redirect_stdout(out):
        ret = main([])
    assert ret == 1
