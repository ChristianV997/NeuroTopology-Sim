"""Tests for minimal sheaf → scalar readout benchmark."""

from __future__ import annotations

import numpy as np
import pytest

from tools.sheaf_scalar_readout.hodge import (
    closedness_needs_degree_two_map,
    readout_breaks_hodge_demo,
)
from tools.sheaf_scalar_readout.sheaf import (
    LinearReadout,
    exactness_preserved,
    is_endpoint_compatible,
    random_vertex_cochain,
    reverse_edge_orientation,
    sheaf_coboundary,
    scalarize_edge_cochain,
)
from tools.sheaf_scalar_readout.triangle_example import (
    R90,
    build_canonical_triangle,
    compatible_readout_all_identity_sheaf,
    first_coordinate_readout,
    run_canonical_triangle,
)


def test_canonical_triangle_B0F_and_cycle_sum():
    report = run_canonical_triangle()
    assert report["B0F_matches_expected"]
    assert report["B0F_z"]["e12"] == [-1.0, -1.0]
    assert report["B0F_z"]["e23"] == [0.0, 0.0]
    assert report["B0F_z"]["e31"] == [-1.0, 1.0]
    assert report["scalar_edges"] == {"e12": -1.0, "e23": 0.0, "e31": -1.0}
    assert report["cycle_sum_1231"] == pytest.approx(-2.0)
    assert report["sheaf_cochain_exact"] is True
    assert report["scalar_cycle_sum_nonzero"] is True
    assert report["endpoint_compatible"] is False


def test_R90_action():
    assert np.allclose(R90 @ np.array([1.0, 1.0]), np.array([-1.0, 1.0]))


def test_incompatible_vs_compatible_readout():
    sheaf = build_canonical_triangle()
    bad = first_coordinate_readout(sheaf)
    ok, _, diag = is_endpoint_compatible(sheaf, bad)
    assert ok is False
    assert "incompatibility" in diag

    sheaf_I, good = compatible_readout_all_identity_sheaf()
    ok2, vmaps, _ = is_endpoint_compatible(sheaf_I, good)
    assert ok2 is True
    assert vmaps is not None
    for v in sheaf_I.vertices:
        assert np.allclose(vmaps[v], np.array([1.0, 0.0]))


def test_compatible_preserves_exactness_random_cochains():
    sheaf_I, good = compatible_readout_all_identity_sheaf()
    rng = np.random.default_rng(0)
    for _ in range(20):
        z = random_vertex_cochain(sheaf_I, rng)
        exact, _, csum = exactness_preserved(sheaf_I, good, z)
        assert exact is True
        assert abs(csum) < 1e-9


def test_incompatible_can_break_exactness():
    sheaf = build_canonical_triangle()
    bad = first_coordinate_readout(sheaf)
    z = {"1": np.array([1.0, 1.0]), "2": np.zeros(2), "3": np.zeros(2)}
    exact, _, csum = exactness_preserved(sheaf, bad, z)
    assert exact is False
    assert abs(csum - (-2.0)) < 1e-12


def test_orientation_reversal_negates_edge_coboundary():
    sheaf = build_canonical_triangle()
    z = {"1": np.array([1.0, 1.0]), "2": np.zeros(2), "3": np.zeros(2)}
    omega = sheaf_coboundary(sheaf, z)
    sheaf_r = reverse_edge_orientation(sheaf, "e12")
    omega_r = sheaf_coboundary(sheaf_r, z)
    assert np.allclose(omega_r["e12"], -omega["e12"])
    assert np.allclose(omega_r["e23"], omega["e23"])
    assert np.allclose(omega_r["e31"], omega["e31"])


def test_zero_readout_kernel_compatible_and_exact():
    sheaf = build_canonical_triangle()
    zero = LinearReadout({e.name: np.zeros(2) for e in sheaf.edges})
    ok, vmaps, _ = is_endpoint_compatible(sheaf, zero)
    assert ok is True
    assert vmaps is not None
    z = {"1": np.array([3.0, -2.0]), "2": np.array([0.5, 0.5]), "3": np.zeros(2)}
    exact, sc, csum = exactness_preserved(sheaf, zero, z)
    assert exact is True
    assert all(abs(v) < 1e-15 for v in sc.values())
    assert abs(csum) < 1e-15


def test_nonzero_kernel_first_coord_on_rotated_restriction_incompatible():
    """Nonzero Λ with nontrivial ker on stalks still fails endpoint compatibility here."""
    sheaf = build_canonical_triangle()
    # Λ_e = (1,0) has ker span{(0,1)}; still incompatible because of R90 at vertex 1
    lam = first_coordinate_readout(sheaf)
    ok, _, _ = is_endpoint_compatible(sheaf, lam)
    assert ok is False
    omega = sheaf_coboundary(
        sheaf, {"1": np.array([0.0, 1.0]), "2": np.zeros(2), "3": np.zeros(2)}
    )
    # ρ R90 (0,1)=(-1,0); first coord readout on e31 is -1; on e12: -(0,1)→0
    sc = scalarize_edge_cochain(lam, omega)
    assert sc["e12"] == pytest.approx(0.0)
    assert sc["e31"] == pytest.approx(-1.0)


def test_hodge_not_preserved_after_incompatible_readout():
    demo = readout_breaks_hodge_demo()
    assert abs(demo["cycle_sum"]) > 1e-8
    assert demo["filled_2_complex"]["curl_nonzero"] is True
    assert demo["cycle_graph_1_skeleton"]["harmonic_nonzero"] is True
    assert demo["hodge_not_preserved"] is True


def test_closedness_doc_keys_present():
    doc = closedness_needs_degree_two_map()
    for k in (
        "exactness_preservation",
        "closedness_on_2_complex",
        "cohomology_map",
        "distinction",
    ):
        assert k in doc and len(doc[k]) > 20
