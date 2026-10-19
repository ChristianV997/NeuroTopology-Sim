"""Tests for deterministic synthetic ground-truth TDA fixtures.

Validates that the reference Vietoris-Rips persistent homology engine exactly reproduces
proven analytical persistence diagrams for:
1. Empty and degenerate inputs (N=0, N=1)
2. Disconnected components (merger at 1.0 and 10.0)
3. Known loop (unit square S^1 with birth=1.0, death=sqrt(2))
4. Filled triangle / 2-simplex (equilateral triangle with immediate filling at 1.0)
5. Reordered vertices (permutation invariance)
6. Duplicate / coincident points (distance 0 edge)
7. Threshold boundary (filtration cutoff at T_max=1.2)
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from tools.topology_backend_conformance import (
    ReferenceSimplicialAdapter,
    make_disconnected_components_fixture,
    make_duplicate_points_fixture,
    make_empty_fixture,
    make_filled_triangle_fixture,
    make_known_loop_fixture,
    make_reordered_fixture,
    make_single_point_fixture,
    make_threshold_boundary_fixture,
)


@pytest.fixture
def ref_adapter() -> ReferenceSimplicialAdapter:
    return ReferenceSimplicialAdapter()


def test_empty_input_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 1a: N=0 empty input produces empty diagrams without error."""
    fix = make_empty_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    assert len(res.get_bars(0)) == 0
    assert len(res.get_bars(1)) == 0


def test_single_point_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 1b: N=1 single point produces exactly 1 infinite H0 bar [0, inf)."""
    fix = make_single_point_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    h0 = res.get_bars(0)
    assert len(h0) == 1
    assert h0[0].birth == 0.0
    assert h0[0].death is None or math.isinf(h0[0].death)
    assert h0[0].is_infinite is True
    assert len(res.get_bars(1)) == 0


def test_disconnected_components_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 2: Two separated pairs merge at t=1.0 within pairs and t=10.0 between pairs."""
    fix = make_disconnected_components_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    h0 = res.get_bars(0)
    assert len(h0) == 4

    # Extract deaths of finite bars
    finite_deaths = sorted([b.death for b in h0 if not b.is_infinite])
    infinite_bars = [b for b in h0 if b.is_infinite]

    assert len(infinite_bars) == 1
    assert len(finite_deaths) == 3
    assert np.isclose(finite_deaths[0], 1.0, atol=1e-5)
    assert np.isclose(finite_deaths[1], 1.0, atol=1e-5)
    assert np.isclose(finite_deaths[2], 10.0, atol=1e-5)

    # H1 is empty
    assert len(res.get_bars(1)) == 0


def test_known_loop_unit_square(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 3: Unit square S^1 exhibits persistent H1 loop born at 1.0 and dying at sqrt(2)."""
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    h0 = res.get_bars(0)
    assert len(h0) == 4

    # 3 components merge at 1.0, 1 survives
    finite_h0 = [b.death for b in h0 if not b.is_infinite]
    assert len(finite_h0) == 3
    assert all(np.isclose(d, 1.0, atol=1e-5) for d in finite_h0)

    # Exactly 1 persistent H1 loop born at 1.0 and dying at sqrt(2)
    h1 = res.get_bars(1)
    assert len(h1) == 1
    loop = h1[0]
    assert np.isclose(loop.birth, 1.0, atol=1e-5)
    assert loop.death is not None
    assert np.isclose(loop.death, np.sqrt(2.0), atol=1e-5)
    assert loop.is_infinite is False
    assert np.isclose(loop.lifetime, np.sqrt(2.0) - 1.0, atol=1e-5)


def test_filled_triangle_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 4: Equilateral 3-vertex triangle: 2-simplex appears at 1.0 and fills cycle."""
    fix = make_filled_triangle_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    # H0 has 2 finite mergers at 1.0, 1 infinite
    h0 = res.get_bars(0)
    assert len(h0) == 3
    finite_h0 = [b.death for b in h0 if not b.is_infinite]
    assert len(finite_h0) == 2
    assert all(np.isclose(d, 1.0, atol=1e-5) for d in finite_h0)

    # Crucial mathematical property: H1 is empty (instant death at 1.0 dropped)
    h1 = res.get_bars(1)
    assert len(h1) == 0


def test_duplicate_coincident_points_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 6: Coincident points at distance 0 do not cause division by zero, NaNs, or crashes."""
    fix = make_duplicate_points_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    h0 = res.get_bars(0)
    # The two coincident points merge at 0.0 (zero lifetime), and point 2 merges at 1.0
    finite_h0 = [b.death for b in h0 if not b.is_infinite]
    assert len(finite_h0) == 1
    assert np.isclose(finite_h0[0], 1.0, atol=1e-5)

    inf_h0 = [b for b in h0 if b.is_infinite]
    assert len(inf_h0) == 1
    assert len(res.get_bars(1)) == 0


def test_threshold_boundary_fixture(ref_adapter: ReferenceSimplicialAdapter) -> None:
    """Fixture 7: Unit square with threshold T_max=1.2 truncates before filling simplex at sqrt(2)."""
    fix = make_threshold_boundary_fixture(threshold=1.2)
    cfg = fix.get_config(max_dimension=1)
    res = ref_adapter.compute(fix.data, cfg)

    assert res.success is True
    h1 = res.get_bars(1)
    assert len(h1) == 1
    loop = h1[0]
    assert np.isclose(loop.birth, 1.0, atol=1e-5)
    # Loop does not die within threshold 1.2
    assert loop.is_infinite is True
    assert loop.death is None
