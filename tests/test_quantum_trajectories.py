import numpy as np
from sim.pitnn.quantum_trajectories import MCWFConfig, MCWFTrajectoryEngine


def test_mcwf_streaming_is_seeded_and_bounded():
    engine = MCWFTrajectoryEngine(np.zeros((4, 4), complex), np.full(4, 1e9))
    psi = np.array([1, 0, 0, 0], complex); times = np.linspace(0, 1e-12, 8)
    a = engine.evolve(psi, times, MCWFConfig(trajectories=16, seed=4, store_density=True))
    b = engine.evolve(psi, times, MCWFConfig(trajectories=16, seed=4, store_density=True))
    assert np.array_equal(a["survival_probability"], b["survival_probability"])
    assert a["density_estimate"].shape == (8, 4, 4)
    assert np.all(np.isfinite(a["density_estimate"]))
