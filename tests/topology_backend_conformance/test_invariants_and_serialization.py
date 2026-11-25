"""Tests for mathematical invariants and JSON serialization compliance.

Validates:
1. Vertex reordering invariance (permutation invariance)
2. Finite intervals invariant (0 <= birth <= death)
3. Infinity handling (death=None for persistent features)
4. Strict finite JSON serialization (no NaN, no Inf, allow_nan=False)
"""
from __future__ import annotations

import json
import math
import numpy as np
import pytest

from tools.topology_backend_conformance import (
    ReferenceSimplicialAdapter,
    compare_conformance_runs,
    compute_bottleneck_distance_exact,
    make_known_loop_fixture,
    make_reordered_fixture,
)


def test_vertex_reordering_permutation_invariance() -> None:
    """Permuting distance matrix rows and columns must leave persistence diagrams invariant."""
    adapter = ReferenceSimplicialAdapter()
    base_fix = make_known_loop_fixture()
    cfg = base_fix.get_config(max_dimension=1)

    # Permutation: reverse order
    reord_fix = make_reordered_fixture(base_fix, [3, 2, 1, 0])

    run_orig = adapter.compute(base_fix.data, cfg)
    run_perm = adapter.compute(reord_fix.data, cfg)

    assert run_orig.success is True
    assert run_perm.success is True

    # Compare H0
    cmp_h0 = compare_conformance_runs(run_orig, run_perm, dimension=0, tolerance=1e-5)
    assert cmp_h0.passed_tolerance is True
    assert cmp_h0.bottleneck_distance == pytest.approx(0.0, abs=1e-5)

    # Compare H1
    cmp_h1 = compare_conformance_runs(run_orig, run_perm, dimension=1, tolerance=1e-5)
    assert cmp_h1.passed_tolerance is True
    assert cmp_h1.bottleneck_distance == pytest.approx(0.0, abs=1e-5)


def test_arbitrary_random_permutation_invariance() -> None:
    """Random permutation on 6-point circular cloud preserves H1 loop."""
    adapter = ReferenceSimplicialAdapter()
    theta = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    pts = np.column_stack([np.cos(theta), np.sin(theta)])
    from tools.topology_backend_conformance import compute_euclidean_distance_matrix
    dm = compute_euclidean_distance_matrix(pts)

    from tools.topology_backend_conformance import ConformanceExecutionConfig, FiltrationType, MetricConvention
    cfg = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        max_dimension=1,
    )

    rng = np.random.default_rng(123)
    perm = rng.permutation(6)
    dm_perm = dm[np.ix_(perm, perm)]

    run_orig = adapter.compute(dm, cfg)
    run_perm = adapter.compute(dm_perm, cfg)

    assert run_orig.success is True
    assert run_perm.success is True

    cmp_h1 = compare_conformance_runs(run_orig, run_perm, dimension=1, tolerance=1e-5)
    assert cmp_h1.passed_tolerance is True
    assert cmp_h1.bottleneck_distance == pytest.approx(0.0, abs=1e-5)


def test_finite_intervals_invariant() -> None:
    """All finite persistence bars must satisfy birth >= 0 and birth <= death."""
    adapter = ReferenceSimplicialAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = adapter.compute(fix.data, cfg)

    for dim in (0, 1):
        for bar in res.get_bars(dim):
            assert bar.birth >= -1e-9
            if not bar.is_infinite and bar.death is not None:
                assert bar.death >= bar.birth - 1e-9
                assert bar.lifetime is not None and bar.lifetime >= 0.0


def test_strict_json_serialization_finite_nulls() -> None:
    """Execution results must serialize cleanly with allow_nan=False (null for Inf/NaN)."""
    adapter = ReferenceSimplicialAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = adapter.compute(fix.data, cfg)

    res_dict = res.to_dict()
    # Must not raise ValueError: Out of range float values are not JSON compliant
    json_str = json.dumps(res_dict, allow_nan=False)
    assert isinstance(json_str, str)

    parsed = json.loads(json_str)
    # Verify that infinite bar serialized to death: null
    h0_bars = parsed["diagrams"]["0"]
    infinite_bars = [b for b in h0_bars if b["is_infinite"] is True]
    assert len(infinite_bars) == 1
    assert infinite_bars[0]["death"] is None
    assert infinite_bars[0]["lifetime"] is None
