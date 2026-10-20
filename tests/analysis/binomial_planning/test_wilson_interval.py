"""Tests for Wilson score confidence intervals, boundary cases, and input validation."""

import math
import numpy as np
import pytest

from analysis.binomial_planning.wilson import (
    get_z_score,
    wilson_score_interval,
)


def test_get_z_score_declared_and_levels() -> None:
    """Declared z values must be returned directly; confidence levels match standard quantiles."""
    assert get_z_score(z=1.96) == 1.96
    assert get_z_score(z=2.576) == 2.576

    # Standard confidence levels
    assert math.isclose(get_z_score(confidence_level=0.95), 1.9599639845400536, abs_tol=1e-12)
    assert math.isclose(get_z_score(confidence_level=0.90), 1.6448536269514722, abs_tol=1e-12)
    assert math.isclose(get_z_score(confidence_level=0.99), 2.5758293035489004, abs_tol=1e-12)

    # Invalid inputs
    with pytest.raises(ValueError, match="confidence_level must be strictly between 0 and 1"):
        get_z_score(confidence_level=0.0)
    with pytest.raises(ValueError, match="confidence_level must be strictly between 0 and 1"):
        get_z_score(confidence_level=1.0)
    with pytest.raises(ValueError, match="confidence_level must be strictly between 0 and 1"):
        get_z_score(confidence_level=-0.5)
    with pytest.raises(ValueError, match="must be finite and positive"):
        get_z_score(z=-1.96)
    with pytest.raises(ValueError, match="must be finite and positive"):
        get_z_score(z=0.0)


def test_zero_trials_explicitly_unavailable() -> None:
    """When n = 0, the interval MUST return an explicit non-estimate state with None bounds."""
    res = wilson_score_interval(0, 0, confidence_level=0.95)

    assert not res.is_available
    assert res.status == "unavailable_zero_trials"
    assert res.k == 0
    assert res.n == 0
    assert res.proportion is None
    assert res.lower is None
    assert res.upper is None
    assert res.half_width is None
    assert res.full_width is None


def test_boundary_counts() -> None:
    """Test boundary counts: k = 0, k = 1, k = n - 1, and k = n."""
    n = 20
    z = 1.96
    z2 = z * z

    # 1. k = 0
    res_0 = wilson_score_interval(0, n, z=z)
    assert res_0.is_available
    assert res_0.lower == 0.0
    expected_upper_0 = z2 / (float(n) + z2)
    assert math.isclose(res_0.upper, expected_upper_0, abs_tol=1e-12)
    assert math.isclose(res_0.full_width, expected_upper_0, abs_tol=1e-12)

    # 2. k = 1
    res_1 = wilson_score_interval(1, n, z=z)
    assert 0.0 < res_1.lower < res_1.upper < 1.0

    # 3. k = n - 1
    res_n_minus_1 = wilson_score_interval(n - 1, n, z=z)
    assert 0.0 < res_n_minus_1.lower < res_n_minus_1.upper < 1.0
    # Reflection symmetry between k=1 and k=n-1
    assert math.isclose(res_1.lower, 1.0 - res_n_minus_1.upper, abs_tol=1e-12)
    assert math.isclose(res_1.upper, 1.0 - res_n_minus_1.lower, abs_tol=1e-12)
    assert math.isclose(res_1.full_width, res_n_minus_1.full_width, abs_tol=1e-12)

    # 4. k = n
    res_n = wilson_score_interval(n, n, z=z)
    expected_lower_n = 1.0 - z2 / (float(n) + z2)
    assert math.isclose(res_n.lower, expected_lower_n, abs_tol=1e-12)
    assert res_n.upper == 1.0
    assert math.isclose(res_n.full_width, expected_upper_0, abs_tol=1e-12)


def test_invalid_counts_and_types() -> None:
    """Invalid event/trial counts must be rejected with informative exceptions."""
    # Negative counts
    with pytest.raises(ValueError, match="Event count k must be non-negative"):
        wilson_score_interval(-1, 10)
    with pytest.raises(ValueError, match="Total trials n must be non-negative"):
        wilson_score_interval(0, -5)

    # Count k exceeding n
    with pytest.raises(ValueError, match="Observed count k .* cannot exceed total trials n"):
        wilson_score_interval(11, 10)
    with pytest.raises(ValueError, match="Observed count k .* cannot exceed total trials n"):
        wilson_score_interval(1, 0)

    # Non-integer types
    with pytest.raises(TypeError, match="must be integers"):
        wilson_score_interval(2.5, 10)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be integers"):
        wilson_score_interval(2, 10.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not booleans"):
        wilson_score_interval(True, 10)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not booleans"):
        wilson_score_interval(0, False)  # type: ignore[arg-type]


def test_known_analytical_cases() -> None:
    """Verify known analytical cases including the n=16 evaluation case from Round 6."""
    # 1. Round 6 context: n = 16, k = 0, z = 1.96
    # p_upper = 1.96^2 / (16 + 1.96^2) = 3.8416 / 19.8416 = 0.19361341827271994 (~19.36%)
    res_16 = wilson_score_interval(0, 16, z=1.96)
    expected_16_upper = 3.8416 / (16.0 + 3.8416)
    assert math.isclose(res_16.lower, 0.0)
    assert math.isclose(res_16.upper, expected_16_upper, abs_tol=1e-12)
    assert math.isclose(res_16.upper, 0.19361341827271994, abs_tol=1e-12)

    # With default confidence_level=0.95 (z = 1.9599639845400536)
    res_16_default = wilson_score_interval(0, 16)
    expected_16_default = (res_16_default.z ** 2) / (16.0 + res_16_default.z ** 2)
    assert math.isclose(res_16_default.upper, expected_16_default, abs_tol=1e-12)
    assert math.isclose(res_16_default.upper, 0.19360768053443644, abs_tol=1e-12)

    # 2. n = 100, k = 50, z = 1.96 (p_hat = 0.5)
    # p_tilde = (50 + 1.9208) / (100 + 3.8416) = 51.9208 / 103.8416 = 0.5
    # margin = 1.96 / 103.8416 * sqrt(25.9604) = 0.09617017140985284
    # lower = 0.5 - 0.09617017140985284 = 0.40382982859014716
    # upper = 0.5 + 0.09617017140985284 = 0.5961701714098528
    res_100_50 = wilson_score_interval(50, 100, z=1.96)
    assert math.isclose(res_100_50.proportion, 0.5)
    assert math.isclose(res_100_50.lower, 0.40382982859014716, abs_tol=1e-12)
    assert math.isclose(res_100_50.upper, 0.5961701714098528, abs_tol=1e-12)
    assert math.isclose(res_100_50.half_width, 0.09617017140985284, abs_tol=1e-12)


def test_monotonicity_in_n_for_fixed_proportion() -> None:
    """Interval width strictly decreases as n increases for a fixed observed proportion."""
    # Proportion p_hat = 0.2 across increasing sample sizes
    ns = [10, 50, 200, 1000, 5000]
    widths = []
    for n in ns:
        k = int(0.2 * n)
        res = wilson_score_interval(k, n, z=1.96)
        widths.append(res.full_width)

    for i in range(len(widths) - 1):
        assert widths[i] > widths[i + 1], f"Width not decreasing from n={ns[i]} to n={ns[i+1]}"


def test_monotonicity_in_k_for_fixed_n() -> None:
    """Both lower and upper bounds strictly increase as k increases from 0 to n."""
    n = 30
    lowers = []
    uppers = []
    for k in range(n + 1):
        res = wilson_score_interval(k, n, z=1.96)
        lowers.append(res.lower)
        uppers.append(res.upper)

    for i in range(len(lowers) - 1):
        assert lowers[i] < lowers[i + 1], f"Lower bound not increasing at k={i}"
        assert uppers[i] < uppers[i + 1], f"Upper bound not increasing at k={i}"


def test_continuity_correction_widens_interval() -> None:
    """Continuity-corrected Wilson interval is wider than standard Wilson for 0 < k < n."""
    n = 40
    for k in [5, 10, 20, 35]:
        res_std = wilson_score_interval(k, n, z=1.96, continuity_correction=False)
        res_cc = wilson_score_interval(k, n, z=1.96, continuity_correction=True)

        assert res_cc.full_width >= res_std.full_width
        assert res_cc.lower <= res_std.lower
        assert res_cc.upper >= res_std.upper
