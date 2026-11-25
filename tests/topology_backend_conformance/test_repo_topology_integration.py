"""Tests verifying semantic conformance and compatibility with repository topology modules.

Integrates with:
- core.persistence_export (JSON serialization and deserialization)
- core.topology (betti_curve, persistence_landscape)
- analysis.connectivity_topology (topology_metric_record separation of graph beta_1 and spatial charge)
- dual_engine.spectral_tda (_first_landscape)
"""
from __future__ import annotations

import numpy as np
import pytest

from core.persistence_export import (
    deserialize_diagram,
    persistence_json_roundtrip,
    persistence_statistics,
    persistence_to_dict,
    serialize_diagram,
)
from core.topology import betti_curve, persistence_landscape
from analysis.connectivity_topology import topology_metric_record
from dual_engine.spectral_tda import _first_landscape
from tools.topology_backend_conformance import (
    ReferenceSimplicialAdapter,
    make_known_loop_fixture,
)


def test_core_persistence_export_roundtrip() -> None:
    """Diagrams from the reference engine serialize and roundtrip cleanly through persistence_export."""
    adapter = ReferenceSimplicialAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)
    res = adapter.compute(fix.data, cfg)

    # Convert to (n, 2) arrays for core.persistence_export
    raw_diagrams = {}
    for dim in (0, 1):
        bars = res.get_bars(dim)
        rows = [
            [b.birth, np.inf if b.death is None else b.death]
            for b in bars
        ]
        raw_diagrams[dim] = np.asarray(rows, dtype=float) if rows else np.empty((0, 2))

    betti_nums = [len(res.get_bars(0)), len(res.get_bars(1))]
    exported = persistence_to_dict(raw_diagrams, betti_numbers=betti_nums)

    assert "diagrams" in exported
    assert "statistics" in exported
    assert "betti_numbers" in exported

    # Roundtrip through JSON encoder
    roundtripped = persistence_json_roundtrip(exported)
    assert roundtripped["betti_numbers"] == betti_nums
    assert len(roundtripped["diagrams"]["0"]) == 4
    assert len(roundtripped["diagrams"]["1"]) == 1

    # Verify statistics on H1 loop
    stats_h1 = exported["statistics"]["1"]
    assert stats_h1["count"] == 1
    assert stats_h1["finite_pairs"] == 1
    assert stats_h1["max_lifetime"] == pytest.approx(np.sqrt(2.0) - 1.0, abs=1e-5)


def test_betti_curve_conformance_on_known_loop() -> None:
    """Betti curve on unit square H1 diagram shows feature born at 1.0 and dead at sqrt(2)."""
    # Unit square H1 bar is [1.0, sqrt(2)]
    dgm_h1 = np.array([[1.0, np.sqrt(2.0)]])
    grid = np.array([0.5, 1.0, 1.2, np.sqrt(2.0), 1.5])

    bc = betti_curve(dgm_h1, grid)
    # At 0.5: not born -> 0
    # At 1.0: alive [1.0 <= t < sqrt(2)] -> 1
    # At 1.2: alive -> 1
    # At sqrt(2): dead (t < d is strict) -> 0
    # At 1.5: dead -> 0
    np.testing.assert_array_equal(bc, [0.0, 1.0, 1.0, 0.0, 0.0])


def test_persistence_landscape_conformance_on_known_loop() -> None:
    """Persistence landscape on unit square H1 bar has maximum at midpoint (1.0 + sqrt(2))/2."""
    dgm_h1 = np.array([[1.0, np.sqrt(2.0)]])
    midpoint = (1.0 + np.sqrt(2.0)) / 2.0
    half_life = (np.sqrt(2.0) - 1.0) / 2.0

    grid = np.array([1.0, midpoint, np.sqrt(2.0)])
    land = persistence_landscape(dgm_h1, grid, n_layers=2)

    # Layer 0 is the tent function
    # At 1.0: 0.0
    # At midpoint: half_life
    # At sqrt(2): 0.0
    assert land[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert land[0, 1] == pytest.approx(half_life, abs=1e-5)
    assert land[0, 2] == pytest.approx(0.0, abs=1e-6)

    # Cross-check with dual_engine.spectral_tda._first_landscape
    first_land = _first_landscape(dgm_h1, grid)
    np.testing.assert_allclose(land[0], first_land, atol=1e-7)


def test_topology_metric_record_isolation() -> None:
    """Confirms analysis.connectivity_topology strictly isolates graph beta_1 from spatial charge."""
    rec = topology_metric_record(
        graph_beta1=1,
        spatial_winding_q=None,
    )
    assert rec["metrics"]["graph_beta1"] == 1
    assert rec["metrics"]["spatial_winding_q"] is None
    assert rec["separation"]["graph_beta1_is_spatial_charge"] is False
    assert rec["separation"]["spatial_winding_requires_coordinates"] is True

    # Negative beta_1 must be rejected
    with pytest.raises(ValueError):
        topology_metric_record(graph_beta1=-1)
