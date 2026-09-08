"""Unit tests for TDA backend runners and canonical interval normalization."""
from __future__ import annotations

import numpy as np
import pytest

from tools.tda_reproducibility.fixtures import (
    make_circle_fixture,
    make_line_segment_fixture,
    make_triangle_fixture,
    make_two_clusters_fixture,
)
from tools.tda_reproducibility.runners import (
    FallbackRunner,
    GudhiRunner,
    RipserRunner,
    get_all_runners,
    get_runner,
)
from tools.tda_reproducibility.types import OutputNature


def test_get_all_runners_contains_expected_keys():
    runners = get_all_runners()
    assert "ripser" in runners
    assert "gudhi" in runners
    assert "gtda" in runners
    assert "ripserplusplus" in runners
    assert "fallback" in runners


def test_get_runner_invalid_raises():
    with pytest.raises(ValueError):
        get_runner("non_existent_engine")


def test_ripser_runner_on_triangle():
    t = make_triangle_fixture()
    runner = RipserRunner()
    res = runner.run(t.distance_matrix, max_dimension=1)
    assert res.success is True
    assert res.nature == OutputNature.EXACT.value
    assert 0 in res.diagrams
    assert len(res.diagrams[0]) == 3
    # Exactly one infinite interval in H0
    inf_count = sum(1 for iv in res.diagrams[0] if iv.death is None)
    assert inf_count == 1
    assert res.deterministic_checksum != ""
    assert res.telemetry.runtime_seconds >= 0.0


def test_gudhi_runner_on_circle():
    c = make_circle_fixture(n_points=12)
    runner = GudhiRunner()
    res = runner.run(c.distance_matrix, max_dimension=1)
    assert res.success is True
    assert 1 in res.diagrams
    # Prominent circle loop in H1
    assert len(res.diagrams[1]) == 1
    h1_iv = res.diagrams[1][0]
    assert h1_iv.death is not None
    assert h1_iv.death > h1_iv.birth


def test_fallback_runner_on_circle_and_clusters():
    c = make_circle_fixture(n_points=12)
    fb = FallbackRunner()
    res_c = fb.run(c.distance_matrix, max_dimension=1)
    assert res_c.success is True
    assert 1 in res_c.diagrams
    assert len(res_c.diagrams[1]) == 1

    cl = make_two_clusters_fixture(points_per_cluster=4)
    res_cl = fb.run(cl.distance_matrix, max_dimension=1)
    assert res_cl.success is True
    assert len(res_cl.diagrams.get(1, [])) == 0


def test_unavailable_runner_behavior():
    runner = get_runner("gtda")
    # gtda is not installed in the current environment
    if not runner.is_available():
        D = np.zeros((3, 3))
        res = runner.run(D)
        assert res.success is False
        assert "not installed" in res.error_message
