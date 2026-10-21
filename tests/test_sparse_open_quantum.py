"""Unit and integration tests for sparse open-quantum solvers and state cache."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from physics.open_quantum import (
    LatticeConfig,
    LindbladLattice,
    OperatorCache,
    build_sparse_liouvillian,
    make_matrix_free_liouvillian,
    solve_liouvillian_spectrum,
    stream_lindblad_propagation,
)


@pytest.fixture
def small_model():
    """Small 1-layer lattice (13 sites, Hilbert dim 14, superoperator 196 x 196)."""
    config = LatticeConfig(n_protofilaments=13, n_layers=1)
    return LindbladLattice.from_pbc(config)


class TestSparseOperatorAssembly:
    def test_sparse_matches_dense_liouvillian(self, small_model):
        """Sparse Kronecker Liouvillian must numerically match dense reference."""
        dense_l = small_model.liouvillian()
        sparse_l = build_sparse_liouvillian(small_model)

        assert isinstance(sparse_l, sparse.csc_matrix)
        assert sparse_l.shape == dense_l.shape

        sparse_dense = sparse_l.toarray()
        diff = np.max(np.abs(sparse_dense - dense_l))
        assert diff < 1e-10, f"Sparse and dense Liouvillian mismatch: {diff}"

    def test_matrix_free_operator_action(self, small_model):
        """Matrix-free LinearOperator matvec must match RHS evaluation on arbitrary state."""
        linop = make_matrix_free_liouvillian(small_model)
        d = small_model.dimension
        size = d * d

        rng = np.random.default_rng(123)
        raw = rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d))
        rho = (raw + raw.conj().T) / 2.0
        rho /= np.trace(rho)

        v_in = rho.ravel(order="F")
        v_out = linop.matvec(v_in)
        expected_out = small_model.rhs(rho).ravel(order="F")

        diff = np.max(np.abs(v_out - expected_out))
        assert diff < 1e-12, f"Matrix-free matvec mismatch: {diff}"


class TestSolverSuite:
    @pytest.mark.parametrize("method", ["exact_dense", "sparse_shift_invert"])
    def test_solver_methods_convergence(self, small_model, method):
        """Solvers must converge with small residual norm on stationary mode."""
        res = solve_liouvillian_spectrum(small_model, method=method, k=4)
        assert res.converged is True
        assert res.stationary_residual_s < 1e-3
        assert res.stationary_state is not None
        assert res.stationary_state.shape == (small_model.dimension, small_model.dimension)

        # Hermiticity and trace preservation of stationary state
        rho_ss = res.stationary_state
        herm_diff = np.max(np.abs(rho_ss - rho_ss.conj().T))
        assert herm_diff < 1e-10
        assert np.isclose(np.trace(rho_ss).real, 1.0, atol=1e-8)

    def test_streaming_propagation(self, small_model):
        """Streaming propagation must yield valid normalized states at each time point."""
        d = small_model.dimension
        rho0 = np.eye(d, dtype=np.complex128) / float(d)
        times = np.linspace(0.0, 1e-11, 5)

        states = list(stream_lindblad_propagation(small_model, rho0, times))
        assert len(states) == 5

        for t, rho_t in states:
            assert rho_t.shape == (d, d)
            assert np.isclose(np.trace(rho_t).real, 1.0, atol=1e-7)
            herm_err = np.max(np.abs(rho_t - rho_t.conj().T))
            assert herm_err < 1e-10


class TestOperatorCache:
    def test_lru_eviction(self):
        cache = OperatorCache(max_entries=3)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")
        assert len(cache) == 3

        # Access k1 so it becomes recently used
        _ = cache.get("k1")

        # Insert k4, which should evict oldest (k2)
        cache.set("k4", "v4")
        assert len(cache) == 3
        assert cache.get("k2") is None
        assert cache.get("k1") == "v1"
        assert cache.get("k4") == "v4"

        stats = cache.stats()
        assert stats["hits"] >= 2
        assert stats["misses"] >= 1
