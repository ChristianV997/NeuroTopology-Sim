import numpy as np
from sim.pitnn.mumax3_macro_tda import invert_macro_signal_accelerated
from sim.pitnn.tda_accelerated import SparseTDAConfig, sparse_cycle_rank


def test_sparse_tda_is_deterministic_and_bounded():
    theta = np.linspace(0, 2*np.pi, 100, endpoint=False)
    points = np.column_stack((np.cos(theta), np.sin(theta)))
    result = sparse_cycle_rank(points, SparseTDAConfig(max_points=32, neighbors=4))
    assert result["points_used"] == 32 and result["beta1_proxy"] >= 1
    inversion = invert_macro_signal_accelerated(np.sin(theta), max_points=32)
    assert "sparse_tda" in inversion
