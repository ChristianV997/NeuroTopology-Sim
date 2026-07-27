import numpy as np
from sim.pitnn.kernels_fast import active_cell_indices, exchange_dmi_field, heun_step
from sim.pitnn.vampire_os_llg import LLGConfig, simulate_os_llg


def test_fast_kernel_preserves_spin_norms_and_active_indices():
    spins = np.zeros((16, 3)); spins[:, 2] = 1
    result = heun_step(spins, np.zeros_like(spins), np.zeros_like(spins), dt=1e-5,
                       exchange=.8, dmi=.1, damping=.05, ciss_torque=.02)
    assert np.max(np.abs(np.linalg.norm(result, axis=1) - 1)) < 1e-12
    assert np.array_equal(active_cell_indices(np.array([True, False, True])), np.array([0, 2]))
    assert exchange_dmi_field(result, .8, .1).shape == (16, 3)


def test_fast_llg_backend_is_deterministic():
    config = LLGConfig(n_spins=8, steps=20, seed=3)
    a = simulate_os_llg(config, backend="fast")
    b = simulate_os_llg(config, backend="fast")
    assert a == b
