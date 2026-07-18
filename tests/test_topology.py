from __future__ import annotations
import numpy as np
import pytest
from core.topology import (
    wrap_phase,
    plaquette_charge,
    compute_Q_slice,
    compute_Qabs_slice,
    compute_Qz,
    compute_f_dress,
    compute_cubical_persistence,
    betti_curve,
    persistence_landscape,
    diagram_bottleneck_distance,
)


# ---------------------------------------------------------------------------
# wrap_phase
# ---------------------------------------------------------------------------

def test_wrap_phase_identity():
    x = np.array([0.0, 0.5, -0.5, 1.0, -1.0])
    np.testing.assert_allclose(wrap_phase(x), x)


def test_wrap_phase_large_positive():
    # 2π wraps to ~0
    assert abs(wrap_phase(2 * np.pi)) < 1e-10


def test_wrap_phase_minus_pi():
    # -π and +π represent the same angle; the formula maps -π → -π which is
    # still a valid boundary value with |result| == π.
    result = wrap_phase(-np.pi)
    assert abs(result) == pytest.approx(np.pi)


def test_wrap_phase_array():
    x = np.array([-np.pi - 0.1, np.pi + 0.1])
    result = wrap_phase(x)
    assert np.all(result > -np.pi)
    assert np.all(result <= np.pi)


# ---------------------------------------------------------------------------
# plaquette_charge
# ---------------------------------------------------------------------------

def test_plaquette_charge_uniform():
    theta = np.zeros((8, 8))
    q = plaquette_charge(theta)
    assert q.shape == (7, 7)
    np.testing.assert_allclose(q, 0.0, atol=1e-12)


def test_plaquette_charge_shape():
    theta = np.random.default_rng(0).normal(size=(10, 12))
    q = plaquette_charge(theta)
    assert q.shape == (9, 11)


def test_plaquette_charge_wrong_dim():
    with pytest.raises(ValueError):
        plaquette_charge(np.zeros((4, 4, 4)))


# ---------------------------------------------------------------------------
# compute_Q_slice / compute_Qabs_slice
# ---------------------------------------------------------------------------

def test_compute_Q_slice_uniform():
    assert compute_Q_slice(np.zeros((8, 8))) == 0


def test_compute_Qabs_slice_uniform():
    assert compute_Qabs_slice(np.zeros((8, 8))) == 0.0


def test_compute_Qabs_slice_nonnegative():
    rng = np.random.default_rng(1)
    theta = rng.uniform(-np.pi, np.pi, (16, 16))
    assert compute_Qabs_slice(theta) >= 0.0


# ---------------------------------------------------------------------------
# compute_Qz
# ---------------------------------------------------------------------------

def test_compute_Qz_wrong_dim():
    with pytest.raises(ValueError):
        compute_Qz(np.zeros((4, 4)))


def test_compute_Qz_shape():
    psi = np.ones((4, 4, 5), dtype=complex)
    Qz, Qabs = compute_Qz(psi)
    assert Qz.shape == (5,)
    assert Qabs.shape == (5,)


def test_compute_Qz_axis0():
    psi = np.ones((5, 4, 4), dtype=complex)
    Qz, Qabs = compute_Qz(psi, axis=0)
    assert Qz.shape == (5,)
    assert Qabs.shape == (5,)


def test_compute_Qz_uniform_zero():
    psi = np.ones((8, 8, 4), dtype=complex)
    Qz, Qabs = compute_Qz(psi)
    np.testing.assert_array_equal(Qz, 0)
    np.testing.assert_allclose(Qabs, 0.0, atol=1e-12)


def test_compute_Qz_single_vortex():
    from validation.synthetic import single_vortex
    psi = single_vortex(N=32)
    Qz, Qabs = compute_Qz(psi)
    assert Qz.shape == (32,)
    assert float(np.mean(Qz)) == pytest.approx(1.0, abs=0.1)


def test_compute_Qz_double_vortex():
    from validation.synthetic import double_vortex
    psi = double_vortex(N=32)
    Qz, Qabs = compute_Qz(psi)
    assert float(np.mean(Qz)) == pytest.approx(2.0, abs=0.25)


# ---------------------------------------------------------------------------
# compute_f_dress
# ---------------------------------------------------------------------------

def test_compute_f_dress_coherent():
    """Coherent case: |mean(Qz)| == mean(Qabs) → f_dress ≈ 0."""
    Qz = np.array([1, 1, 1])
    Qabs = np.array([1.0, 1.0, 1.0])
    assert compute_f_dress(Qz, Qabs) == pytest.approx(0.0, abs=1e-6)


def test_compute_f_dress_incoherent():
    """If Qabs dominates over net charge, f_dress > 0."""
    Qz = np.array([0, 0, 0])
    Qabs = np.array([2.0, 2.0, 2.0])
    assert compute_f_dress(Qz, Qabs) > 0


def test_compute_f_dress_nonnegative():
    rng = np.random.default_rng(0)
    Qz = rng.integers(-3, 4, size=20)
    Qabs = np.abs(Qz.astype(float)) + rng.uniform(0, 0.5, size=20)
    assert compute_f_dress(Qz, Qabs) >= 0


# ---------------------------------------------------------------------------
# compute_cubical_persistence / betti_curve / persistence_landscape /
# diagram_bottleneck_distance
# ---------------------------------------------------------------------------

def test_compute_cubical_persistence_shape_and_keys():
    rng = np.random.default_rng(0)
    field = rng.standard_normal((16, 16))
    result = compute_cubical_persistence(field, max_dimension=1)
    assert set(result.keys()) == {"diagrams", "betti_numbers", "metric_kind"}
    assert result["metric_kind"] == "cubical_persistence"
    assert set(result["diagrams"].keys()) == {0, 1}
    for dim, diag in result["diagrams"].items():
        assert diag.ndim == 2 and diag.shape[1] == 2


def test_compute_cubical_persistence_rejects_bad_shape():
    with pytest.raises(ValueError):
        compute_cubical_persistence(np.zeros(10))


def test_compute_cubical_persistence_rejects_non_finite():
    field = np.zeros((8, 8))
    field[0, 0] = np.nan
    with pytest.raises(ValueError):
        compute_cubical_persistence(field)


def test_compute_cubical_persistence_single_connected_component():
    """A perfectly flat field has one H0 component (the whole grid, born at
    the flat value) and, per GUDHI's convention, zero H1 features."""
    field = np.zeros((8, 8))
    result = compute_cubical_persistence(field, max_dimension=1)
    assert result["diagrams"][0].shape[0] == 1
    assert result["diagrams"][1].shape[0] == 0


def test_compute_cubical_persistence_detects_known_amplitude_dip():
    """Two well-separated deep minima must register as two distinct H0
    components that merge (one finite-death pair) into the field's single
    surviving component (one infinite-death pair) once the sub-level
    threshold rises enough to connect them -- a single minimum (see the
    flat-field test above) can never yield more than one H0 pair."""
    field = np.ones((16, 16))
    field[2, 2] = 0.0
    field[13, 13] = 0.0
    result = compute_cubical_persistence(field, max_dimension=0)
    assert result["diagrams"][0].shape[0] == 2
    n_infinite = int(np.sum(~np.isfinite(result["diagrams"][0][:, 1])))
    assert n_infinite == 1


def test_betti_curve_matches_manual_count_at_grid_points():
    diagram = np.array([[0.0, 1.0], [0.5, 2.0]])
    grid = np.array([0.25, 0.75, 1.5, 2.5])
    bc = betti_curve(diagram, grid)
    # at t=0.25: only pair 1 alive (0<=0.25<1) -> 1
    # at t=0.75: both alive (0<=0.75<1 is False for pair1 since 0.75<1 True; pair2: 0.5<=0.75<2 True) -> pair1 alive(0<=.75<1 True), pair2 alive -> 2
    # at t=1.5: pair1 dead (1.5>=1), pair2 alive (0.5<=1.5<2) -> 1
    # at t=2.5: both dead -> 0
    np.testing.assert_array_equal(bc, [1.0, 2.0, 1.0, 0.0])


def test_betti_curve_empty_diagram():
    grid = np.linspace(0, 1, 10)
    bc = betti_curve(np.empty((0, 2)), grid)
    np.testing.assert_array_equal(bc, np.zeros(10))


def test_betti_curve_handles_infinite_death():
    diagram = np.array([[0.0, np.inf]])
    grid = np.linspace(0, 5, 6)
    bc = betti_curve(diagram, grid)
    assert np.all(bc == 1.0)  # alive at every sampled grid point


def test_persistence_landscape_shape():
    diagram = np.array([[0.0, 1.0], [0.2, 0.8], [0.1, 0.5]])
    grid = np.linspace(0, 1, 20)
    land = persistence_landscape(diagram, grid, n_layers=5)
    assert land.shape == (5, 20)


def test_persistence_landscape_layers_are_ordered():
    """Layer k (the k-th largest tent per grid point) must be <= layer k-1
    everywhere, by construction (descending sort)."""
    rng = np.random.default_rng(0)
    b = np.sort(rng.uniform(0, 0.5, size=8))
    d = b + rng.uniform(0.1, 0.5, size=8)
    diagram = np.column_stack([b, d])
    grid = np.linspace(0, 1, 30)
    land = persistence_landscape(diagram, grid, n_layers=4)
    for k in range(1, 4):
        assert np.all(land[k] <= land[k - 1] + 1e-12)


def test_persistence_landscape_excludes_infinite_pairs():
    diagram = np.array([[0.0, np.inf], [0.1, 0.6]])
    grid = np.linspace(0, 1, 10)
    land = persistence_landscape(diagram, grid, n_layers=3)
    assert np.all(np.isfinite(land))


def test_persistence_landscape_empty_diagram():
    grid = np.linspace(0, 1, 10)
    land = persistence_landscape(np.empty((0, 2)), grid, n_layers=3)
    np.testing.assert_array_equal(land, np.zeros((3, 10)))


def test_diagram_bottleneck_distance_self_is_near_zero():
    diagram = np.array([[0.0, 1.0], [0.2, 0.9]])
    d = diagram_bottleneck_distance(diagram, diagram)
    assert d == pytest.approx(0.0, abs=1e-6)


def test_diagram_bottleneck_distance_differs_for_different_diagrams():
    diagram_a = np.array([[0.0, 1.0]])
    diagram_b = np.array([[0.0, 5.0]])
    d = diagram_bottleneck_distance(diagram_a, diagram_b)
    assert d > 1.0


def test_cubical_persistence_on_cgl_field_finds_real_structure():
    """Integration check: a genuine dynamical field (not hand-written) yields
    a nontrivial H1 diagram and a betti curve with real structure -- this is
    the actual enrichment target (see validation/synthetic.cgl_defect_field)."""
    from validation.synthetic import cgl_defect_field
    psi = cgl_defect_field(N=32, n_steps=60, seed=0)
    amp = np.abs(psi)
    result = compute_cubical_persistence(amp, max_dimension=1)
    assert result["diagrams"][1].shape[0] > 0
    grid = np.linspace(amp.min(), amp.max(), 30)
    bc = betti_curve(result["diagrams"][1], grid)
    assert bc.max() > 0
